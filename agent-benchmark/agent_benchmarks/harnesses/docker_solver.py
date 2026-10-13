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
    Run ``claude -p --output-format stream-json`` to solve from ``instruction.md``.
    The final result event carries ``total_cost_usd`` / ``usage`` / ``duration_ms``
    / ``ttft_ms`` / ``num_turns``, which we parse into a :class:`UsageRecord` and
    fold into ``HarnessResult.metrics``, with tool calls counted by name. An
    optional skill is installed as a plugin (the with-skill treatment arm, see
    :mod:`.skill_treatment`).
``probe``
    No LLM: run the isolation probe from :mod:`.agent_sandbox` in exactly the
    cwd and env ``claude`` would get, and score 1.0 only when nothing the agent
    must not see (grader files, the content repo's skills, the operator's
    ``~/.claude``, the network, host env) is reachable. Free; run it before a
    paid sweep to know what the arms could have read.

By default the agent runs inside the task container (:mod:`.container_agent`):
it edits ``/app`` in place, behind an egress proxy that reaches only the LLM.
The ``-host`` variants run it on the host instead (:mod:`.agent_sandbox`): we
snapshot ``/app`` into a scratch tree outside any checkout, let the agent edit
it, and copy it back. Either way the documented compile commands are re-run in
the container before the verifier. What a launch seals is recorded per run in
``metrics.isolation``.
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
    credential_values,
    default_forbidden,
    operator_source_env,
    probe_reward,
    run_probe,
    solver_cli_flags,
)
from .claude_json import _last_json_object, _parse_claude_json  # noqa: F401
from .command import _parse_reward_text
from .container_agent import AGENT_BIN, FILES_DIR, ContainerSandbox
from .models import HarnessResult, OperationRecord
from .skill_treatment import Treatment, build_plugin, check_skill, treatment_notice
from .solver_stream import record_solver, run_solver
from .tasks import (  # noqa: F401  (timeouts re-exported)
    _DEFAULT_BUILD_TIMEOUT,
    _DEFAULT_VERIFY_TIMEOUT,
    TaskSpec,
    _is_public,
    _task_build_timeout,
    _task_verify_timeout,
)

# Recompile commands embedded in instruction.md, e.g. `g++ -O3 ... -o /app/bench`.
# C tasks (missing-restrict) use gcc, C++ tasks use g++.
_RECOMPILE_RE = re.compile(r"(g\+\+|gcc) [^`\n]*-o /app/[^ `\n]*")
_PROXY_VARS = ("http_proxy", "https_proxy", "no_proxy", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY")
_DEFAULT_SOLVE_TIMEOUT = 600.0
_CONTAINER_PLUGIN = "/opt/abskill"


@dataclass(frozen=True)
class DockerSolverHarness:
    """Build → solve → verify a task with local Docker; emit reward + telemetry.

    ``mode`` is ``oracle``, ``claude`` or ``probe``. ``skill_path`` points at a
    skill directory or its ``SKILL.md``; in claude mode the skill tree, less its
    top-level ``evals/``, is installed as a plugin for the with-skill treatment
    arm (see :mod:`.skill_treatment`), in probe mode it is a path the probe must
    not reach.
    ``agent_location`` is ``container`` (the agent runs in the task container,
    see :mod:`.container_agent`) or ``host`` (see :mod:`.agent_sandbox`).
    """

    harness_id: str
    mode: str = "claude"
    skill_path: Optional[str] = None
    model_default: Optional[str] = None
    kind: str = "docker"
    env: dict[str, str] = field(default_factory=dict)
    agent_location: str = "container"

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
        skill_dir = self._resolve_skill_dir()
        if self.mode == "claude" and skill_dir is not None:
            check_skill(skill_dir)  # a bad skill fails here, not after the image and network

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
        sandbox: Optional[ContainerSandbox] = None
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
            if self.mode in ("claude", "probe") and self.agent_location == "container":
                sandbox = ContainerSandbox.open(container, _docker, log, source_env=operator_source_env(),
                                                task_egress=task.environment.get("egress"),
                                                with_agent=self.mode == "claude")
            try:
                self._start_container(task, image, container, log, sandbox)
                try:
                    if self.mode == "oracle":
                        self._solve_oracle(task, container, log)
                    elif self.mode == "claude":
                        usage = self._solve_claude(
                            task, container, output_dir, model, solve_timeout,
                            operations, log, extra_metrics, sandbox,
                        )
                    elif self.mode == "probe":
                        reward = self._solve_probe(task, container, output_dir, log, extra_metrics,
                                                   sandbox)
                    else:
                        raise ValueError(f"unknown mode {self.mode!r}")
                    if sandbox is not None:
                        sandbox.stop_proxy(_docker, log)  # the verifier gets no route out either
                        if _is_public(task):  # "public" is the verifier's, after the agent exits
                            _docker(["network", "connect", "bridge", container], log)
                    if self.mode != "probe":  # the probe's reward is its own verdict
                        reward = self._verify(task, container, output_dir, log)
                finally:
                    _docker(["rm", "-f", container], log, check=False)
            finally:
                if sandbox is not None:  # also when the container never started
                    sandbox.close(_docker, log, output_dir)
                    extra_metrics["egress"] = sandbox.egress_summary()
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

    def _start_container(self, task: TaskSpec, image: str, container: str, log,
                         sandbox: Optional[ContainerSandbox] = None) -> None:
        # --network none unless the task declares environment.network_mode =
        # "public"; then bridge (NAT'd internet), not host, so host-local
        # services stay out of reach. Build always gets host network. An
        # in-container agent brings its own internal network + egress proxy,
        # and a "public" task joins bridge only for its verifier.
        net_args = (sandbox.run_args() if sandbox is not None
                    else ["--network", "bridge" if _is_public(task) else "none"])

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

        # PID 1 must outlive the solve and the verifier: when it exits, an
        # in-container agent dies mid-solve and the verifier finds no container.
        lifetime = int(max(1800.0, (task.timeout_sec or _DEFAULT_SOLVE_TIMEOUT)
                           + _task_verify_timeout(task) + 600))
        _docker(["rm", "-f", container], log, check=False)
        _docker(
            ["run", "-d", "--name", container, *net_args,
             "--cpus", cpus, "--memory", memory, image, "sleep", str(lifetime)],
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
        extra_metrics: dict[str, Any], sandbox: Optional[ContainerSandbox] = None,
    ) -> Optional[UsageRecord]:
        """Solve with ``claude -p`` in the task container (*sandbox*) or on the host.

        Returns a :class:`UsageRecord` parsed from the ``claude`` result event
        (cost/tokens/cache/latency/turns), or ``None`` if the JSON was missing.
        """
        # A rerun must not find its own previous tree or verdict during the solve.
        _rmtree(output_dir / "work")
        (output_dir / "reward.txt").unlink(missing_ok=True)
        if sandbox is not None:
            return self._solve_claude_in_container(task, container, output_dir, model, timeout,
                                                   operations, log, extra_metrics, sandbox)
        workspace, treatment = self._prepare_workspace(task, container, log, extra_metrics,
                                                       output_dir=output_dir)
        extra_metrics["isolation"] = workspace.isolation()
        try:
            work = workspace.work
            plugin = str(workspace.root / "plugin") if treatment else None
            cmd = ["claude", *self._claude_args(task, treatment, plugin, model, output_dir)]
            before = workspace.state()
            t0 = time.time()
            env = workspace.env(operator_source_env(), self.env)
            secrets = credential_values(env)
            proc = run_solver(cmd, output_dir, extra_metrics, treatment, secrets, cwd=str(work),
                              timeout=timeout, env=env)
            usage = record_solver(proc, task.name, model, time.time() - t0, output_dir,
                                  operations, log, extra_metrics, treatment, secrets,
                                  edited=workspace.state() != before)
            _docker(["cp", f"{str(work)}/.", f"{container}:/app/"], log)
        finally:
            # Keep the agent's tree with the run (also after a timeout); the plugin is
            # beside it, not in it.
            _rmtree(output_dir / "work")
            try:
                shutil.copytree(workspace.work, output_dir / "work", symlinks=True)
            except OSError as exc:  # never mask the solve's own outcome
                log.write(f"\n[keep work tree] {exc}\n")
            workspace.cleanup()
        failed = self._recompile(task, container, log)
        if failed:
            extra_metrics["recompile_failed"] = failed
        return usage

    def _solve_claude_in_container(
        self, task: TaskSpec, container: str, output_dir: Path,
        model: Optional[str], timeout: float, operations: list[OperationRecord], log,
        extra_metrics: dict[str, Any], sandbox: ContainerSandbox,
    ) -> Optional[UsageRecord]:
        """The agent edits ``/app`` in place; the grader files are not in the container yet."""
        extra_metrics["isolation"] = sandbox.isolation()
        treatment = self._install_plugin_in_container(container, output_dir, log, extra_metrics)
        sandbox.prepare(container, _docker, log)
        env = sandbox.env(operator_source_env(), self.env)
        secrets = credential_values(env)
        argv, client_env = sandbox.exec_argv(container, env, [AGENT_BIN, *self._claude_args(
            task, treatment, _CONTAINER_PLUGIN if treatment else None, model, output_dir)])
        t0 = time.time()
        try:
            proc = run_solver(argv, output_dir, extra_metrics, treatment, secrets, timeout=timeout,
                              env=client_env)
        finally:  # also on a timeout: stop the agent, keep its tree for debugging
            sandbox.reap(container, _docker, log)  # nothing the agent backgrounded sees /tests
            # Not on the verifier's side of the run.
            _docker(["exec", "-u", "root", container, "rm", "-rf", _CONTAINER_PLUGIN], log, check=False)
            _rmtree(output_dir / "work")
            (output_dir / "work").mkdir(parents=True)
            _docker(["cp", f"{container}:/app/.", str(output_dir / "work")], log, check=False)
            # The verifier runs the agent's /app code as root, on bridge for a public task.
            _docker(["exec", "-u", "root", container, "rm", "-rf", FILES_DIR], log, check=False)
        usage = record_solver(proc, task.name, model, time.time() - t0, output_dir,
                              operations, log, extra_metrics, treatment, secrets)
        failed = self._recompile(task, container, log)
        if failed:
            extra_metrics["recompile_failed"] = failed
        return usage

    def _prepare_workspace(self, task: TaskSpec, container: str, log,
                           extra_metrics: Optional[dict[str, Any]] = None,
                           output_dir: Optional[Path] = None,
                           ) -> tuple[AgentWorkspace, Optional[Treatment]]:
        """Snapshot ``/app`` into a scratch work tree; install the arm's skill beside it.

        In probe mode the skill is not offered: it joins the paths the probe must not reach.
        """
        skill_dir = self._resolve_skill_dir()
        probing = self.mode == "probe" and skill_dir is not None
        forbidden = default_forbidden(task.path, [skill_dir] if probing and skill_dir else [],
                                      output_dir=output_dir)
        workspace = AgentWorkspace.create(forbidden=forbidden)
        try:
            _docker(["cp", f"{container}:/app/.", str(workspace.work)], log)
            treatment = None
            if skill_dir is not None and not probing:
                treatment = build_plugin(skill_dir, workspace.root / "plugin")
                if extra_metrics is not None:
                    extra_metrics["treatment"] = treatment.as_metrics()
        except BaseException:  # also Ctrl-C: don't leave the abrun-* snapshot behind
            workspace.cleanup()
            raise
        return workspace, treatment

    def _install_plugin_in_container(self, container: str, output_dir: Path, log,
                                     extra_metrics: dict[str, Any]) -> Optional[Treatment]:
        """Copy the arm's skill, as a plugin, to ``/opt/abskill`` (outside ``/app``)."""
        skill_dir = self._resolve_skill_dir()
        if skill_dir is None:
            return None
        staged = output_dir / "plugin"
        _rmtree(staged)
        try:
            treatment = build_plugin(skill_dir, staged)
            extra_metrics["treatment"] = treatment.as_metrics()
            # Create the target first and copy its contents: `docker cp dir path` nests
            # dir inside an existing path, and fails where /opt does not exist.
            _docker(["exec", "-u", "root", container, "mkdir", "-p", _CONTAINER_PLUGIN], log)
            _docker(["cp", f"{staged}/.", f"{container}:{_CONTAINER_PLUGIN}"], log)
            # Root-owned, read-only to the agent. u=rwX,go=rX also clears setuid/setgid and
            # group/other write that copy2 and docker cp carry over (a+rX only adds bits).
            _docker(["exec", "-u", "root", container, "chmod", "-R", "u=rwX,go=rX",
                     _CONTAINER_PLUGIN], log)
        finally:  # also when a docker step fails: the copy is not kept with the run
            _rmtree(staged)
        return treatment

    def _claude_args(self, task: TaskSpec, treatment: Optional[Treatment],
                     plugin_dir: Optional[str], model: Optional[str],
                     output_dir: Path) -> list[str]:
        """``claude`` argv after the executable; the prompt is also saved as ``prompt.txt``."""
        prompt = (
            f"{treatment_notice(treatment)}"
            "Solve this coding task. Edit files in the current directory only. "
            "When done, leave the optimized source and any required outputs in place.\n\n"
            f"{task.instruction}"
        )
        (output_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        args = ["-p", prompt, "--output-format", "stream-json", "--verbose", *solver_cli_flags()]
        args += ["--plugin-dir", plugin_dir] if plugin_dir else []
        return args + (["--model", model] if model else [])

    def _solve_probe(self, task: TaskSpec, container: str, output_dir: Path, log,
                     extra_metrics: dict[str, Any],
                     sandbox: Optional[ContainerSandbox] = None) -> float:
        """Run the isolation probe where the agent would run; reward 1.0 only if sealed."""
        untested = {k: "untested" for k in LEAK_CLASSES}
        if sandbox is not None:
            sandbox.prepare(container, _docker, log)
            skill_dir = self._resolve_skill_dir()  # docker-probe:<skill>: forbidden, never offered
            try:
                result = sandbox.run_probe(container, task.path, operator_source_env(), self.env,
                                           _docker, log, [skill_dir] if skill_dir else [])
            except subprocess.TimeoutExpired as exc:  # a hung check: nothing was shown closed
                log.write(f"\n[probe] TIMEOUT: {exc}\n")
                result = untested
            isolation = sandbox.isolation()
        else:
            workspace, _ = self._prepare_workspace(task, container, log, output_dir=output_dir)
            try:
                result = run_probe(workspace, operator_source_env(), self.env)
            except subprocess.TimeoutExpired as exc:
                log.write(f"\n[probe] TIMEOUT: {exc}\n")
                result = untested
            finally:
                workspace.cleanup()
            isolation = workspace.isolation()
        log.write(f"\n[probe] {json.dumps(result)}\n")
        (output_dir / "isolation_probe.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        extra_metrics["isolation"] = isolation
        extra_metrics["isolation_probe"] = result
        return probe_reward(result)

    def _recompile(self, task: TaskSpec, container: str, log) -> list[str]:
        """Re-run the compile command(s) documented in instruction.md, in the container.

        A host-launched agent builds against the host's (newer) glibc, which may
        not run in the older task image; an in-container agent may simply not
        have built. Matches both ``g++`` and ``gcc``.

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
        if proc.returncode != 0:  # no verdict at all if the container is gone, not a 0
            running = _docker(["inspect", "-f", "{{.State.Running}}", container], log, check=False)
            if (getattr(running, "stdout", "") or "").strip() != "true":
                raise RuntimeError(f"task container {container} is not running at verify time; see run.log")
        # No reward file written: fall back to verifier exit code.
        return 1.0 if proc.returncode == 0 else 0.0

    # ── helpers ─────────────────────────────────────────────────────────────

    def _resolve_skill_dir(self) -> Optional[Path]:
        if not self.skill_path:
            return None
        # Relative to the operator's cwd, not the agent's. absolute(), not resolve():
        # a symlinked SKILL.md must not swap in the link target's directory.
        p = Path(self.skill_path).absolute()
        if p.is_file() and p.name != "SKILL.md":  # Claude Code loads SKILL.md only
            raise ValueError(f"skill path must be a skill directory or its SKILL.md: {p}")
        return p.parent if p.is_file() else p

    def _describe_command(self, task: TaskSpec, model: Optional[str]) -> list[str]:
        parts = ["docker-solver", self.mode, task.name]
        if model:
            parts += ["--model", model]
        if self.skill_path:
            parts += ["--skill", self.skill_path]
        return parts


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


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _tail(text: str, limit: int = 4000) -> str:
    return text[-limit:] if len(text) > limit else text
