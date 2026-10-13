# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The environment a solver agent is launched in, and a probe that measures it.

A treatment comparison is only as good as the wall between the agent and the
answers. Three kinds of leak bias a with-skill vs without-skill run:

* **reaching the grader** — the task's ``solution/`` and ``tests/`` sit next to
  the agent's work tree, so reading them turns a solve into a copy;
* **reaching the treatment** — the content repo that holds the task also holds
  ``skills/``, so a *baseline* agent can find and read the very skill it is the
  control for, which understates the skill's lift;
* **inheriting the operator** — a ``claude`` launched with the operator's HOME
  loads their ``~/.claude`` (CLAUDE.md, skills, plugins, MCP servers, memory)
  and every CLAUDE.md above its cwd, into both arms alike.

:class:`AgentWorkspace` removes what can be removed on the host: the work tree
moves to a fresh temp dir outside any checkout, HOME and ``CLAUDE_CONFIG_DIR``
point at empty scratch dirs, the environment is an allowlist, and the CLI is
told to load no setting sources and no MCP servers. What the host cannot remove
— an absolute path still opens the task and content checkout, and the network
is open — is stated in :meth:`AgentWorkspace.isolation` and measured by
:func:`run_probe`, which runs a script in exactly the agent's cwd and env and
reports which of the leaks above it could reach.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from agent_benchmarks.repos.harness_profile import run_harness

_LOG = logging.getLogger(__name__)

# Tools the solver may use. ``--tools`` sets the available set; ``--allowedTools``
# alone only pre-approves, and under --dangerously-skip-permissions everything is
# approved anyway, so it would leave WebFetch/WebSearch/Task on.
SOLVER_TOOLS = ("Read", "Edit", "Write", "Bash", "Glob", "Grep")

# Environment variables passed through to the agent. Everything else is dropped:
# the operator's tokens for unrelated services, nested-session markers
# (CLAUDECODE, CLAUDE_CODE_SESSION_ID, ...) and hook toggles.
_ENV_EXACT = frozenset({
    "PATH", "LANG", "LANGUAGE", "TERM", "TZ", "SHELL", "USER", "LOGNAME",
    "http_proxy", "https_proxy", "no_proxy", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS", "NODE_OPTIONS",
    # LLM provider selection and credentials.
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_FABLE_MODEL", "ANTHROPIC_BEDROCK_BASE_URL",
    "ANTHROPIC_VERTEX_PROJECT_ID", "ANTHROPIC_VERTEX_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
    "CLAUDE_CODE_USE_ANTHROPIC_AWS", "CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD", "CLAUDE_CODE_USE_MANTLE",
    "CLAUDE_CODE_USE_GATEWAY", "ANTHROPIC_AWS_WORKSPACE_ID", "ANTHROPIC_GOOGLE_CLOUD_PROJECT",
    "ANTHROPIC_GOOGLE_CLOUD_LOCATION", "ANTHROPIC_GOOGLE_CLOUD_WORKSPACE_ID",
    "CLAUDE_CODE_CLIENT_CERT", "CLAUDE_CODE_CLIENT_KEY", "CLAUDE_CODE_CLIENT_KEY_PASSPHRASE",
    "CLAUDE_CODE_SKIP_BEDROCK_AUTH", "CLAUDE_CODE_SKIP_VERTEX_AUTH", "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_RESOURCE", "ANTHROPIC_FOUNDRY_BASE_URL",
    "ANTHROPIC_CUSTOM_HEADERS", "AWS_CA_BUNDLE",
    "CLAUDE_CODE_MAX_RETRIES", "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
    "CLOUD_ML_REGION", "GOOGLE_APPLICATION_CREDENTIALS",
    "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_PROFILE", "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE", "AWS_ENDPOINT_URL_BEDROCK_RUNTIME",
    "AWS_ROLE_ARN", "AWS_WEB_IDENTITY_TOKEN_FILE",
})
_ENV_PREFIXES = ("LC_", "AWS_CONTAINER_CREDENTIALS_", "VERTEX_REGION_")

# Leak classes the probe reports, in report order.
LEAK_CLASSES = ("task_files", "treatment", "operator_config", "checkout_walk", "network", "env")


def operator_source_env(environ: Optional[dict[str, str]] = None) -> dict[str, str]:
    """The operator's environment plus the ``env`` block of their Claude Code settings.

    With setting sources off, the agent no longer reads ``~/.claude/settings.json``.
    That block is often the only place provider selection and credentials live
    (``CLAUDE_CODE_USE_BEDROCK``, a bearer token). It is merged *over* the
    process environment, as Claude Code itself applies it, and filtered by the
    same allowlist as everything else. ``apiKeyHelper`` and OAuth logins are not
    carried over.
    """
    environ = dict(os.environ if environ is None else environ)
    config = Path(environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    path = config / "settings.json"
    try:
        block = json.loads(path.read_text(encoding="utf-8")).get("env") or {}
    except FileNotFoundError:
        block = {}
    except (OSError, ValueError, AttributeError) as exc:
        _LOG.warning("ignoring the env block of %s: %s", path, exc)
        block = {}
    settings = {str(k): str(v) for k, v in block.items()} if isinstance(block, dict) else {}
    return {**environ, **settings}


def agent_env(source: dict[str, str], extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    """Allowlisted copy of *source*; *extra* (the harness's own env) is added verbatim."""
    env = {k: v for k, v in source.items() if k in _ENV_EXACT or k.startswith(_ENV_PREFIXES)}
    env.update(extra or {})
    return env


def solver_cli_flags() -> list[str]:
    """``claude -p`` flags that keep the operator's configuration out of the run."""
    return [
        "--dangerously-skip-permissions",
        "--tools", ",".join(SOLVER_TOOLS),
        "--setting-sources", "",
        "--strict-mcp-config",
        "--no-session-persistence",
    ]


@dataclass
class AgentWorkspace:
    """A scratch root ``<tmp>/abrun-*/{work,home,config}`` for one solve.

    ``forbidden`` lists host paths the agent should not be able to read (the
    task's grader files, a skill the arm does not offer, the operator's
    ``~/.claude``); the probe tries each one.
    """

    root: Path
    forbidden: dict[str, list[Path]] = field(default_factory=dict)

    @classmethod
    def create(cls, *, forbidden: Optional[dict[str, list[Path]]] = None) -> "AgentWorkspace":
        root = Path(tempfile.mkdtemp(prefix="abrun-"))
        for sub in ("work", "home", "config"):
            (root / sub).mkdir()
        return cls(root=root, forbidden=forbidden or {})

    @property
    def work(self) -> Path:
        return self.root / "work"

    def env(self, source: dict[str, str], extra: Optional[dict[str, str]] = None) -> dict[str, str]:
        env = agent_env(source, extra)
        env["HOME"] = str(self.root / "home")
        env["CLAUDE_CONFIG_DIR"] = str(self.root / "config")
        env["TMPDIR"] = str(self.root / "home")
        return env

    def isolation(self) -> dict[str, str]:
        """What this launch does and does not seal, recorded with every run."""
        return {
            "agent_location": "host",
            "work_tree": "temp dir outside any checkout",
            "operator_config": ("settings not loaded (scratch HOME and CLAUDE_CONFIG_DIR, no setting"
                                " sources, no MCP); the settings.json env block is merged through the"
                                " env allowlist"),
            "env": ("allowlist; the harness's own env stays readable through /proc/<pid>/environ"
                    " of same-uid processes"),
            "tools": ",".join(SOLVER_TOOLS) + " (Bash can still start a nested claude with its defaults)",
            "host_filesystem": "readable by absolute path",
            "network": "open",
        }

    def state(self) -> frozenset[tuple[str, int, int]]:
        """``(path, size, mtime_ns)`` of every file in the work tree but the skill copy.

        Two states differ if the agent wrote, created or deleted a file between them.
        """
        out = set()
        for dirpath, dirnames, filenames in os.walk(self.work):
            if Path(dirpath) == self.work:
                dirnames[:] = [d for d in dirnames if d != ".skill"]
            for name in filenames:
                path = os.path.join(dirpath, name)
                try:
                    st = os.lstat(path)
                except OSError:
                    continue
                out.add((os.path.relpath(path, self.work), st.st_size, st.st_mtime_ns))
        return frozenset(out)

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def default_forbidden(task_path: Path, skill_dirs: Iterable[Path] = (),
                      output_dir: Optional[Path] = None) -> dict[str, list[Path]]:
    """Paths a solve of *task_path* must not read.

    ``treatment`` is every ``skills/`` tree on the way up from the task (a git
    checkout or not; an inner one must not hide the content repo's): the leak that matters is a *baseline* agent reading it. A with-skill arm gets
    its own copy under ``./.skill`` and has no reason to look there either.
    *skill_dirs* adds skills kept elsewhere (``docker-probe:<skill>``), so a
    baseline probe can check the treatment its with-skill arm is offered.
    ``task_files`` names the grader dirs of both layouts (Harbor ``solution/``
    and ``tests/``, BenchFlow ``task.md`` ``oracle/`` and ``verifier/``), so
    either is checked; a name the task does not ship cannot be read anyway.
    *output_dir*'s task directory (this task's cells of every arm: work trees,
    prompts, transcripts; one level further up for a ``run<k>`` repeat dir)
    joins ``task_files`` as an absolute path.
    """
    task_files = [task_path / name for name in ("solution", "tests", "oracle", "verifier")]
    if output_dir is not None:
        out = output_dir.absolute()
        task_files.append(out.parent.parent if re.fullmatch(r"run\d+", out.name) else out.parent)
    operator = [Path.home() / ".claude", Path.home() / ".claude.json"]
    if os.environ.get("CLAUDE_CONFIG_DIR"):  # Claude Code keeps .claude.json there too
        config = Path(os.environ["CLAUDE_CONFIG_DIR"])
        operator += [config, config / ".claude.json"]
    forbidden: dict[str, list[Path]] = {"task_files": task_files, "operator_config": operator}
    treatment = [Path(p) for p in skill_dirs]
    treatment += _skills_dirs_above(task_path)
    if treatment:
        forbidden["treatment"] = treatment
    return forbidden


def _skills_dirs_above(path: Path) -> list[Path]:
    """Every ``skills/`` dir on the way up, with or without a ``.git`` (tarball, submodule)."""
    return [p / "skills" for p in (path, *path.parents) if (p / "skills").is_dir()]


# The probe is plain sh so it runs in any task image, and prints one JSON line.
# Each check reports "open" (the agent could reach it) or "closed"; a class with
# nothing declared to protect reports "n/a" rather than a "closed" it never tested,
# and one the image has no tool for reports "untested" (which fails, like "open").
_PROBE_SH = r"""
set -u
emit() { printf '"%s":"%s"' "$1" "$2"; }
can_read() {  # any of the given paths readable -> open
  for p in "$@"; do
    if [ -d "$p" ] && ls "$p" >/dev/null 2>&1 && [ -n "$(ls -A "$p" 2>/dev/null)" ]; then return 0; fi
    if [ -f "$p" ] && head -c1 "$p" >/dev/null 2>&1; then return 0; fi
  done
  return 1
}
walk="closed"; d="$(pwd)"
while [ "$d" != "/" ]; do
  d="$(dirname "$d")"
  if [ -e "$d/.git" ] || [ -e "$d/task.toml" ] || [ -e "$d/CLAUDE.md" ]; then walk="open"; break; fi
done
# Any client that honours the proxy variables, the way an agent's own code would.
# -f: a proxy's 403 for a denied host is "closed", not a successful fetch.
net="closed"
if command -v curl >/dev/null 2>&1; then
  curl -fsS -m 5 -o /dev/null "$PROBE_URL" 2>/dev/null && net="open"
elif command -v wget >/dev/null 2>&1; then
  # Busybox wget has no retry flag, and GNU wget retries 20 times: bound it.
  if command -v timeout >/dev/null 2>&1; then
    timeout 10 wget -q -T 5 -O /dev/null "$PROBE_URL" 2>/dev/null && net="open"
  else
    wget -q -T 5 -O /dev/null "$PROBE_URL" 2>/dev/null && net="open"
  fi
elif command -v python3 >/dev/null 2>&1; then
  python3 -c "import sys,urllib.request; urllib.request.urlopen(sys.argv[1], timeout=5)" "$PROBE_URL" \
    >/dev/null 2>&1 && net="open"
else
  net="untested"
fi
# A dropped variable leaks if its host *value* is in the environ of this
# process, its parent chain or PID 1: the agent's own env, and on the host the
# harness and the operator's shell, which run as the agent's uid. Tokens are
# NAME:cksum:length of the value's first line, so no secret is passed in.
envleak="n/a"; leaked=""
if [ -n "$PROBE_ENV_DENY" ]; then
  if [ ! -r "/proc/$$/environ" ] || ! command -v cksum >/dev/null 2>&1; then
    envleak="untested"
  else
    envleak="closed"; pids="$$"; p="$$"
    while :; do
      p="$(sed -n 's/^PPid:[[:space:]]*//p' "/proc/$p/status" 2>/dev/null)"
      case "$p" in ''|0|1) break;; esac
      pids="$pids $p"
    done
    for p in $pids 1; do
      dump="$(tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null)" || continue
      present=" $(printf '%s\n' "$dump" | sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p' | tr '\n' ' ')"
      for tok in $PROBE_ENV_DENY; do
        v="${tok%%:*}"
        case "$present" in *" $v "*) ;; *) continue;; esac
        got="$(printf '%s\n' "$dump" | sed -n "s/^$v=//p" | head -n 1 | tr -d '\n' | cksum)"
        set -- $got 0 0
        if [ "$v:$1:$2" = "$tok" ]; then
          envleak="open"
          case " $leaked " in *" $v "*) ;; *) leaked="$leaked $v";; esac
        fi
      done
    done
  fi
fi
printf '{'
nl='
'
check_paths() {  # class, then a newline-separated path list (paths may contain spaces)
  c="$1"
  if [ -z "$2" ]; then emit "$c" n/a; return; fi
  old_ifs="$IFS"; IFS="$nl"; set -f; set -- $2; set +f; IFS="$old_ifs"
  if can_read "$@"; then emit "$c" open; else emit "$c" closed; fi
}
check_paths task_files "$PROBE_TASK_FILES"; printf ','
check_paths treatment "$PROBE_TREATMENT"; printf ','
check_paths operator_config "$PROBE_OPERATOR"; printf ','
emit checkout_walk "$walk"; printf ','
emit network "$net"; printf ','
emit env "$envleak"
printf '}\n'
"""

PROBE_URL = "https://example.com/"


def probe_script() -> str:
    return _PROBE_SH


def probe_env(forbidden: dict[str, list[Path]], deny_env: Iterable[str],
              url: str = PROBE_URL) -> dict[str, str]:
    """Variables the probe script reads (newline-separated path lists, space-separated
    :func:`env_fingerprints` tokens)."""

    def paths(key: str) -> str:
        return "\n".join(str(p) for p in forbidden.get(key, []))

    return {
        "PROBE_TASK_FILES": paths("task_files"),
        "PROBE_TREATMENT": paths("treatment"),
        "PROBE_OPERATOR": paths("operator_config"),
        "PROBE_ENV_DENY": " ".join(deny_env),
        "PROBE_URL": url,
    }


def denied_env_names(source: dict[str, str]) -> list[str]:
    """Names present in *source* that the allowlist drops (the probe checks every one)."""
    return sorted(k for k in source if k not in _ENV_EXACT and not k.startswith(_ENV_PREFIXES)
                  and k not in ("HOME", "PWD", "OLDPWD", "SHLVL", "_", "TMPDIR",
                                "CLAUDE_CONFIG_DIR"))


def env_fingerprints(source: dict[str, str], names: Iterable[str]) -> list[str]:
    """``NAME:cksum:length`` of each value's first line, for the probe to match.

    The probe looks for the host's *value*, not just the name, so an image that
    sets the same name itself is not a leak. POSIX ``cksum`` because every image
    has it; an empty value cannot be told apart and is skipped.
    """
    out = []
    for name in names:
        first = (source.get(name) or "").split("\n", 1)[0].encode("utf-8", "surrogateescape")
        if first:
            out.append(f"{name}:{_posix_cksum(first)}:{len(first)}")
    return out


def _posix_cksum(data: bytes) -> int:
    crc = 0

    def step(crc: int, byte: int) -> int:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) if crc & 0x80000000 else crc << 1
        return crc & 0xFFFFFFFF

    for byte in data:
        crc = step(crc, byte)
    n = len(data)
    while n:
        crc, n = step(crc, n & 0xFF), n >> 8
    return ~crc & 0xFFFFFFFF


def run_probe(workspace: AgentWorkspace, source_env: dict[str, str],
              extra_env: Optional[dict[str, str]] = None, timeout: float = 60.0,
              url: Optional[str] = None) -> dict[str, str]:
    """Run the probe on the host, in the agent's cwd and env. Returns ``{leak_class: state}``."""
    env = workspace.env(source_env, extra_env)
    deny = env_fingerprints(source_env, denied_env_names(source_env))
    env.update(probe_env(workspace.forbidden, deny, url or PROBE_URL))
    # run_harness kills the whole process group (job object on Windows) on a timeout, so a
    # hung fetch or ls does not outlive the probe in a deleted scratch dir.
    proc = run_harness(["sh", "-c", _PROBE_SH], cwd=str(workspace.work), env=env, timeout=timeout)
    return parse_probe_output(proc.stdout)


def parse_probe_output(stdout: str) -> dict[str, str]:
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            return {k: str(data.get(k, "untested")) for k in LEAK_CLASSES}
    return {k: "untested" for k in LEAK_CLASSES}


def probe_reward(result: dict[str, str]) -> float:
    """1.0 only when every leak class is ``closed`` or ``n/a``; ``open`` and ``untested`` fail.

    ``n/a`` (no path declared for the class, e.g. a task outside any checkout and no
    ``docker-probe:<skill>``) passes too; it stays visible in ``isolation_probe``.
    """
    return 1.0 if all(result.get(k) in ("closed", "n/a") for k in LEAK_CLASSES) else 0.0
