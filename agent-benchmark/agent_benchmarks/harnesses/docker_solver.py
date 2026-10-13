# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Standalone Docker harness — solve a terminal-bench task and verify it.

It runs an executable task end to end against local Docker with **no Harbor
dependency**, and captures full LLM telemetry (cost, tokens, cache, latency,
turns) into the ``task_runs.v1`` artifact so task experiments are tracked the
same way the Q&A ``arms run`` path already is.

Three solver modes:

``oracle``
    Apply the task's own ``solution/solve.sh`` (no LLM). Validates that the task
    image + verifier work end to end. Free; no telemetry.
``claude``
    Run ``claude -p --output-format json`` to solve from ``instruction.md``.
    The JSON result carries ``total_cost_usd`` / ``usage`` / ``duration_ms`` /
    ``ttft_ms`` / ``num_turns``, which we parse into a :class:`UsageRecord` and
    fold into ``HarnessResult.metrics``. An optional skill directory is copied
    next to the work tree (the with-skill treatment arm).
``probe``
    No LLM: run the isolation probe from :mod:`.agent_sandbox` in exactly the
    cwd and env ``claude`` would get, and score 1.0 only when nothing the agent
    must not see (grader files, the content repo's skills, the operator's
    ``~/.claude``, the network, host env) is reachable. Free; run it before a
    paid sweep to know what the arms could have read.

The agent runs on the HOST (the ``claude`` CLI is a host tool); we snapshot
``/app`` into a scratch tree outside any checkout (see
:class:`~.agent_sandbox.AgentWorkspace`), let the agent edit it, copy it back,
and recompile inside the container so the binary matches the image's (older)
glibc. What the host cannot seal is recorded per run in ``metrics.isolation``.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from agent_benchmarks.metrics.usage import UsageRecord

from .agent_sandbox import (
    LEAK_CLASSES,
    AgentWorkspace,
    default_forbidden,
    operator_source_env,
    probe_reward,
    run_probe,
    solver_cli_flags,
)
from .claude_json import _last_json_object, _parse_claude_json, solver_error, terminal_reason  # noqa: F401
from .command import _parse_reward_text
from .models import HarnessResult, OperationRecord
from .tasks import TaskSpec

# Recompile commands embedded in instruction.md, e.g. `g++ -O3 ... -o /app/bench`.
# C tasks (missing-restrict) use gcc, C++ tasks use g++.
_RECOMPILE_RE = re.compile(r"(g\+\+|gcc) [^`\n]*-o /app/[^ `\n]*")
_PROXY_VARS = ("http_proxy", "https_proxy", "no_proxy", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY")
_DEFAULT_SOLVE_TIMEOUT = 600.0
_DEFAULT_BUILD_TIMEOUT = 600.0
_DEFAULT_VERIFY_TIMEOUT = 180.0


@dataclass(frozen=True)
class DockerSolverHarness:
    """Build → solve → verify a task with local Docker; emit reward + telemetry.

    ``mode`` is ``oracle``, ``claude`` or ``probe``. ``skill_path`` points at a
    skill directory or its ``SKILL.md``; in claude mode the whole skill tree is
    exposed to the agent as the with-skill treatment arm, in probe mode it is a
    path the probe must not reach.
    """

    harness_id: str
    mode: str = "claude"
    skill_path: Optional[str] = None
    model_default: Optional[str] = None
    kind: str = "docker"
    env: dict[str, str] = field(default_factory=dict)

    def run(
        self,
        task: TaskSpec,
        *,
        model: Optional[str] = None,
        output_dir: Optional[Path] = None,
        timeout_sec: Optional[float] = None,
        dry_run: bool = False,
    ) -> HarnessResult:
        output_dir = Path(output_dir) if output_dir else None
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
        model = model or self.model_default

        operations = [
            OperationRecord(
                type="harness",
                name=self.harness_id,
                metadata={"kind": self.kind, "task": task.name, "model": model, "mode": self.mode},
            )
        ]

        if dry_run:
            return HarnessResult(
                harness=self.harness_id,
                task=task.name,
                command=self._describe_command(task, model),
                returncode=0,
                elapsed_sec=0.0,
                reward=None,
                passed=False,
                output_dir=str(output_dir) if output_dir else None,
                operations=operations,
                metrics={"dry_run": True, "mode": self.mode},
            )

        if output_dir is None:
            raise ValueError("DockerSolverHarness requires an output_dir")

        log_path = output_dir / "run.log"
        log = log_path.open("w", encoding="utf-8")
        usage: Optional[UsageRecord] = None
        image = f"agent-bench/{task.name}:latest"
        container = f"abrun-{task.name}-{os.getpid()}"
        solve_timeout = timeout_sec or task.timeout_sec or _DEFAULT_SOLVE_TIMEOUT
        start = time.time()
        returncode = 0
        extra_metrics: dict[str, Any] = {}
        reward: Optional[float] = None
        try:
            try:
                self._build_image(task, image, log)
            except subprocess.TimeoutExpired as exc:
                # The image never got built, so no agent ran and there is no
                # verdict: raise so the cell is errored like a build that fails
                # fast. Only a solve or verify timeout below is a reward-0 failure.
                log.write(f"\nBUILD TIMEOUT: {exc}\n")
                raise RuntimeError(
                    f"docker build timed out after {exc.timeout}s; see run.log"
                ) from exc
            self._start_container(task, image, container, log)
            try:
                if self.mode == "oracle":
                    self._solve_oracle(task, container, log)
                elif self.mode == "claude":
                    usage = self._solve_claude(
                        task, container, output_dir, model, solve_timeout,
                        operations, log, extra_metrics,
                    )
                elif self.mode == "probe":
                    reward = self._solve_probe(task, container, output_dir, log, extra_metrics)
                else:
                    raise ValueError(f"unknown mode {self.mode!r}")
                if self.mode != "probe":  # the probe's reward is its own verdict
                    reward = self._verify(task, container, output_dir, log)
            finally:
                _docker(["rm", "-f", container], log, check=False)
        except subprocess.TimeoutExpired as exc:
            log.write(f"\nTIMEOUT: {exc}\n")
            returncode = 124
            reward = 0.0
        except Exception as exc:
            # Nothing recorded yet (a build failure): let the runner mark it errored.
            # After a solve (a failed copy back), keep its cost and isolation record.
            if not extra_metrics:
                raise
            log.write(f"\nERROR: {type(exc).__name__}: {exc}\n")
            extra_metrics["error"] = f"{type(exc).__name__}: {exc}"
            returncode = 1
            reward = None
        finally:
            log.close()

        elapsed = time.time() - start
        passed = reward is not None and reward >= 1.0
        metrics: dict[str, Any] = {"dry_run": False, "mode": self.mode}
        if usage is not None:
            metrics.update(usage.as_metrics_dict())
            if usage.model:
                metrics["model"] = usage.model
        metrics.update(extra_metrics)
        return HarnessResult(
            harness=self.harness_id,
            task=task.name,
            command=self._describe_command(task, model),
            returncode=returncode,
            elapsed_sec=elapsed,
            reward=reward,
            passed=passed,
            stdout_tail=_tail(log_path.read_text(encoding="utf-8", errors="replace")),
            output_dir=str(output_dir),
            operations=operations,
            metrics=metrics,
        )

    # ── pipeline steps ──────────────────────────────────────────────────────

    def _build_image(self, task: TaskSpec, image: str, log) -> None:
        """Build the task image; pass host proxy through (corporate networks)."""
        env_dir = task.path / "environment"
        build_args: list[str] = ["--network", "host"]
        for var in _PROXY_VARS:
            val = os.environ.get(var)
            if val:
                build_args += ["--build-arg", f"{var}={val}"]
        # Honor the task's own build_timeout_sec (some images need >10 min);
        # _DEFAULT_BUILD_TIMEOUT is only the fallback when the task omits it.
        timeout = _task_build_timeout(task)
        _docker(
            ["build", "-q", *build_args, "-t", image,
             "-f", str(env_dir / "Dockerfile"), str(env_dir)],
            log, timeout=timeout,
        )

    def _start_container(self, task: TaskSpec, image: str, container: str, log) -> None:
        # Our own tasks never set network_mode and never need network at
        # solve/verify time, so this defaults to the historical --network
        # none. External tasks (e.g. uxlfoundation/skills) can declare
        # environment.network_mode = "public" for solve/verify steps that
        # need it; build already gets host network via _build_image
        # regardless of this setting. Bridge (not host): "public" means
        # "needs outbound internet," not "may see the host's own network" --
        # bridge gets NAT'd internet access without exposing host-local
        # services (loopback ports, metadata endpoints) to untrusted task
        # code the way --network host would.
        network_mode = str(task.environment.get("network_mode") or "none")
        network = "bridge" if network_mode == "public" else "none"

        cpus_raw = task.environment.get("cpus")
        cpus = str(cpus_raw) if cpus_raw is not None else "4"

        # A malformed external task.toml (e.g. memory_mb as a string with a
        # unit already attached) must not crash the whole run -- fall back
        # to the historical default instead.
        memory_mb_raw = task.environment.get("memory_mb")
        try:
            memory = f"{int(memory_mb_raw)}m" if memory_mb_raw is not None else "2g"
        except (TypeError, ValueError):
            memory = "2g"

        _docker(["rm", "-f", container], log, check=False)
        _docker(
            ["run", "-d", "--name", container, "--network", network,
             "--cpus", cpus, "--memory", memory, image, "sleep", "1800"],
            log,
        )

    def _solve_oracle(self, task: TaskSpec, container: str, log) -> None:
        """Apply solution/solve.sh as root (some images set a non-root USER).

        Copies the whole ``solution/`` directory, not just ``solve.sh`` --
        our own tasks' solve.sh is always self-contained, but an external
        task's solve.sh can be a thin script that `cp`s a sibling source
        file into place (e.g. uxlfoundation/skills' oneTBB tasks).
        """
        _docker(["cp", str(task.path / "solution"), f"{container}:/solution"], log)
        _docker(
            ["exec", "-u", "root", container, "bash", "-lc",
             "chmod +x /solution/solve.sh && /solution/solve.sh"],
            log, check=False,
        )

    def _solve_claude(
        self, task: TaskSpec, container: str, output_dir: Path,
        model: Optional[str], timeout: float, operations: list[OperationRecord], log,
        extra_metrics: dict[str, Any],
    ) -> Optional[UsageRecord]:
        """Snapshot /app, solve on the host, copy back, recompile in-container.

        Returns a :class:`UsageRecord` parsed from ``claude --output-format json``
        (cost/tokens/cache/latency/turns), or ``None`` if the JSON was missing.
        """
        # A rerun must not find its own previous tree or verdict during the solve.
        _rmtree(output_dir / "work")
        (output_dir / "reward.txt").unlink(missing_ok=True)
        workspace, skill_note = self._prepare_workspace(task, container, log, output_dir)
        extra_metrics["isolation"] = workspace.isolation()
        try:
            return self._run_claude(task, container, output_dir, model, timeout,
                                    operations, log, extra_metrics, workspace, skill_note)
        finally:
            # Keep the agent's tree with the run (also after a timeout), without the skill.
            _rmtree(workspace.work / ".skill")
            _rmtree(output_dir / "work")
            try:
                shutil.copytree(workspace.work, output_dir / "work", symlinks=True)
            except OSError as exc:  # never mask the solve's own outcome
                log.write(f"\n[keep work tree] {exc}\n")
            workspace.cleanup()

    def _prepare_workspace(self, task: TaskSpec, container: str, log,
                           output_dir: Optional[Path] = None) -> tuple[AgentWorkspace, str]:
        """Snapshot ``/app`` into a fresh scratch work tree; expose the skill if this arm has one.

        In probe mode the skill is not offered: it joins the paths the probe must not reach.
        """
        skill_dir = self._resolve_skill_dir()
        probing = self.mode == "probe" and skill_dir is not None
        forbidden = default_forbidden(task.path, [skill_dir] if probing and skill_dir else [],
                                      output_dir=output_dir)
        workspace = AgentWorkspace.create(forbidden=forbidden)
        try:
            _docker(["cp", f"{container}:/app/.", str(workspace.work)], log)
            skill_note = ""
            if skill_dir is not None and not probing:
                _copytree(skill_dir, workspace.work / ".skill")
                entry = self._skill_entry(skill_dir)
                skill_note = (
                    f"A performance skill is available at ./.skill/ "
                    f"(start with ./.skill/{entry}). Read the files it references "
                    "before fixing.\n\n"
                )
        except BaseException:  # also Ctrl-C: don't leave the abrun-* snapshot behind
            workspace.cleanup()
            raise
        return workspace, skill_note

    def _solve_probe(self, task: TaskSpec, container: str, output_dir: Path, log,
                     extra_metrics: dict[str, Any]) -> float:
        """Run the isolation probe where the agent would run; reward 1.0 only if sealed."""
        workspace, _ = self._prepare_workspace(task, container, log, output_dir)
        try:
            result = run_probe(workspace, operator_source_env(), self.env)
        except subprocess.TimeoutExpired as exc:  # a hung check: nothing was shown closed
            log.write(f"\n[probe] TIMEOUT: {exc}\n")
            result = {k: "untested" for k in LEAK_CLASSES}
        finally:
            workspace.cleanup()
        log.write(f"\n[probe] {json.dumps(result)}\n")
        (output_dir / "isolation_probe.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        extra_metrics["isolation"] = workspace.isolation()
        extra_metrics["isolation_probe"] = result
        return probe_reward(result)

    def _run_claude(
        self, task: TaskSpec, container: str, output_dir: Path,
        model: Optional[str], timeout: float, operations: list[OperationRecord], log,
        extra_metrics: dict[str, Any], workspace: AgentWorkspace, skill_note: str,
    ) -> Optional[UsageRecord]:
        work = workspace.work
        prompt = (
            f"{skill_note}"
            "Solve this coding task. Edit files in the current directory only. "
            "When done, leave the optimized source and any required outputs in place.\n\n"
            f"{task.instruction}"
        )
        prompt_file = output_dir / "prompt.txt"
        prompt_file.write_text(prompt, encoding="utf-8")

        cmd = ["claude", "-p", prompt, "--output-format", "json", *solver_cli_flags()]
        if model:
            cmd += ["--model", model]
        before = workspace.state()
        t0 = time.time()
        proc = subprocess.run(
            cmd, cwd=str(work), text=True, capture_output=True,
            timeout=timeout, check=False, env=workspace.env(operator_source_env(), self.env),
        )
        latency = time.time() - t0
        log.write(proc.stdout or "")
        log.write(proc.stderr or "")
        error = solver_error(proc.stdout, edited=workspace.state() != before)
        if error:  # no attempt was made: the runner leaves the cell out, like metrics.error
            extra_metrics["solver_error"] = error
        usage = _parse_claude_json(proc.stdout, task.name, model or "", latency)
        reason = terminal_reason(proc.stdout) or ("no_result" if usage is None else None)
        if reason:
            extra_metrics["terminal_reason"] = reason
        (output_dir / "solver.json").write_text(proc.stdout or "", encoding="utf-8")
        if usage is not None:
            # Kept if the copy back below fails: the solve was paid for either way.
            extra_metrics.update(usage.as_metrics_dict())
            if usage.model:
                extra_metrics["model"] = usage.model
            operations.append(
                OperationRecord(type="loop", name="claude-turns", elapsed_sec=usage.latency_sec,
                                metadata={"n_calls": usage.n_calls})
            )

        _rmtree(work / ".skill")  # don't ship the skill files into /app for the verifier
        _docker(["cp", f"{str(work)}/.", f"{container}:/app/"], log)
        failed = self._recompile(task, container, log)
        if failed:
            extra_metrics["recompile_failed"] = failed
        return usage

    def _recompile(self, task: TaskSpec, container: str, log) -> list[str]:
        """Recompile inside the container so the binary matches the image glibc.

        The agent edits source on the host (newer glibc); a host-built binary may
        fail in the older task image, so re-run the compile command(s) documented
        in instruction.md in-container. Matches both ``g++`` and ``gcc``.

        Returns the compile commands that failed. A recompile failure is a
        *tooling* failure, not a solve failure: the caller records it in
        ``metrics`` so such cells can be told apart from genuine model misses.
        """
        failed: list[str] = []
        for match in _RECOMPILE_RE.finditer(task.instruction):
            cc = match.group(0).strip()
            log.write(f"\n[recompile] {cc}\n")
            proc = _docker(["exec", "-u", "root", container, "bash", "-lc", cc], log, check=False)
            if proc.returncode != 0:
                log.write(f"[recompile] FAILED (exit {proc.returncode}): {cc}\n")
                failed.append(cc)
        return failed

    def _verify(self, task: TaskSpec, container: str, output_dir: Path, log) -> Optional[float]:
        """Run tests/ in-container; pull /logs/verifier/reward.txt back out."""
        _docker(["cp", str(task.path / "tests"), f"{container}:/tests"], log)
        proc = _docker(
            ["exec", "-u", "root", container, "bash", "-lc",
             "mkdir -p /logs/verifier && chmod +x /tests/test.sh && /tests/test.sh"],
            log, check=False, timeout=_task_verify_timeout(task),
        )
        reward_file = output_dir / "reward.txt"
        pulled = _docker(
            ["cp", f"{container}:/logs/verifier/reward.txt", str(reward_file)],
            log, check=False,
        )
        if pulled.returncode == 0 and reward_file.is_file():
            return _parse_reward_text(reward_file.read_text(encoding="utf-8", errors="replace"))
        # No reward file written: fall back to verifier exit code.
        return 1.0 if proc.returncode == 0 else 0.0

    # ── helpers ─────────────────────────────────────────────────────────────

    def _resolve_skill_dir(self) -> Optional[Path]:
        if not self.skill_path:
            return None
        # Relative to the operator's cwd, not the agent's. absolute(), not resolve():
        # a symlinked SKILL.md must not swap in the link target's directory.
        p = Path(self.skill_path).absolute()
        return p.parent if p.is_file() else p

    def _skill_entry(self, skill_dir: Path) -> str:
        if self.skill_path and Path(self.skill_path).is_file():
            return Path(self.skill_path).name
        return "SKILL.md"

    def _describe_command(self, task: TaskSpec, model: Optional[str]) -> list[str]:
        parts = ["docker-solver", self.mode, task.name]
        if model:
            parts += ["--model", model]
        if self.skill_path:
            parts += ["--skill", self.skill_path]
        return parts


def _task_build_timeout(task: TaskSpec) -> float:
    """Image build timeout: the task's ``environment.build_timeout_sec`` if set,
    else :data:`_DEFAULT_BUILD_TIMEOUT`."""
    val = task.environment.get("build_timeout_sec")
    try:
        return float(val) if val is not None else _DEFAULT_BUILD_TIMEOUT
    except (TypeError, ValueError):
        return _DEFAULT_BUILD_TIMEOUT


def _task_verify_timeout(task: TaskSpec) -> float:
    """Verifier timeout: the task's ``verifier.timeout_sec`` if set, else
    :data:`_DEFAULT_VERIFY_TIMEOUT`."""
    val = task.verifier.get("timeout_sec")
    try:
        return float(val) if val is not None else _DEFAULT_VERIFY_TIMEOUT
    except (TypeError, ValueError):
        return _DEFAULT_VERIFY_TIMEOUT


def _docker(args: list[str], log, *, check: bool = True,
            timeout: Optional[float] = None) -> subprocess.CompletedProcess:
    """Run a ``docker`` subcommand, tee-ing output to the run log."""
    proc = subprocess.run(
        ["docker", *args], text=True, capture_output=True, timeout=timeout, check=False,
    )
    log.write(f"$ docker {' '.join(shlex.quote(a) for a in args)}\n")
    if proc.stdout:
        log.write(proc.stdout)
    if proc.stderr:
        log.write(proc.stderr)
    if check and proc.returncode != 0:
        raise RuntimeError(f"docker {args[0]} failed (exit {proc.returncode}); see run.log")
    return proc


def _copytree(src: Path, dest: Path) -> None:
    import shutil

    shutil.copytree(src, dest)


def _rmtree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)


def _tail(text: str, limit: int = 4000) -> str:
    return text[-limit:] if len(text) > limit else text
