#!/usr/bin/env python
"""Regenerate a channel-control agent profile from the skill it mirrors.

`data/agent_profiles/dpnp-skilltext.md` exists to hold *content* constant while changing
the *channel*: the same bytes the `skill:` arm injects as context, sent instead as the
answering agent's system prompt. That only isolates the channel while the two are
byte-identical, and nothing about editing a skill makes anyone remember the profile —
`tests/test_agent_profiles.py::test_channel_control_is_the_skill_text_verbatim` is what
notices, and this script is what it points at.

    python scripts/sync_skilltext_profile.py --check   # exit 1 if out of sync
    python scripts/sync_skilltext_profile.py           # rewrite the profile body

The profile's YAML frontmatter is preserved verbatim; only the body is replaced.

Re-syncing changes the prompt text, so it changes `profile_prompt_sha256`. Every cell
already measured with the old text becomes a different treatment under the same arm name
(`profile:dpnp-skilltext`) — `scripts/check_treatment_batch.py --profile` reports those as
STALE ARTIFACT, and `report model-compare` refuses to pool them. Re-run the affected cells
or keep the batches apart; do not average them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent_benchmarks.skills import load_skill  # noqa: E402
from agent_benchmarks.utils import parse_frontmatter  # noqa: E402

DEFAULT_SKILL = REPO_ROOT / "data" / "skills" / "dpnp-quickstart"
DEFAULT_PROFILE = REPO_ROOT / "data" / "agent_profiles" / "dpnp-skilltext.md"
# Must match the cap the skill arm renders with, in `treatments/arms.py`. A different cap
# here would make the control differ from the skill arm by content as well as channel.
MAX_CHARS = 12_000


def frontmatter_block(text: str) -> str:
    """The leading ``---`` block of *text*, or '' when it has none.

    Taken from the raw text rather than re-serialized from the parsed mapping: round-tripping
    YAML reorders keys and reflows the long `description`, which would show up as a diff on
    every run and make a real drift indistinguishable from formatting churn.

    The fence rules deliberately mirror :func:`parse_frontmatter` — BOM tolerated, closing
    fence is a line that is exactly ``---`` — because that function is what reads the file
    back. Where the two disagreed, this one could copy a "header" the loader treats as body
    (a substring search matched any line merely *starting* with ``---``) or refuse a BOM'd
    file the loader parses fine, and the frontmatter `id` is the arm name every artifact is
    keyed by.
    """
    stripped = text.lstrip("﻿")
    if not stripped.startswith("---"):
        return ""
    lines = stripped.splitlines(keepends=True)
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            block = "".join(lines[: idx + 1])
            # A file that ends at the closing fence with no newline would otherwise splice
            # the body onto the fence line and stop being frontmatter at all.
            return block if block.endswith(("\n", "\r")) else block + "\n"
    return ""


def render(skill_dir: Path, profile_path: Path) -> str:
    """The profile file as it should be: existing frontmatter + the skill's rendered text."""
    body = load_skill(skill_dir).as_context(MAX_CHARS).strip()
    if not body:
        raise SystemExit(f"Error: skill {skill_dir} rendered an empty body")
    # The profile must already exist: its frontmatter `id` is the arm name every artifact is
    # keyed by, and choosing one is a decision, not a derivation. Rendering a bare body here
    # would silently rename the arm to the filename stem on the next run.
    if not profile_path.is_file():
        raise SystemExit(
            f"Error: no such profile: {profile_path}. This script replaces the body of an "
            "existing control profile; create the file with `id`/`name`/`description` "
            "frontmatter first."
        )
    header = frontmatter_block(profile_path.read_text(encoding="utf-8"))
    if not header:
        raise SystemExit(
            f"Error: {profile_path} has no YAML frontmatter, so its id cannot be preserved. "
            "The arm name comes from the frontmatter id — add one before syncing."
        )
    return f"{header}{body}\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--skill", type=Path, default=DEFAULT_SKILL, help="skill directory to mirror")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE, help="profile .md to rewrite")
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 when the profile does not match the skill",
    )
    args = parser.parse_args()

    if not args.skill.is_dir():
        raise SystemExit(f"Error: no such skill directory: {args.skill}")
    wanted = render(args.skill, args.profile)  # errors if the profile is absent or bare
    current = args.profile.read_text(encoding="utf-8")

    if current == wanted:
        print(f"in sync: {args.profile.name} matches {args.skill.name}")
        return 0
    if args.check:
        # Echo only the flags that were actually needed: printing the two absolute default
        # paths turns a one-word fix into a line nobody copies.
        flags = "".join(
            f" {flag} {value}"
            for flag, value, default in (
                ("--skill", args.skill, DEFAULT_SKILL),
                ("--profile", args.profile, DEFAULT_PROFILE),
            )
            if value != default
        )
        print(
            f"OUT OF SYNC: {args.profile.name} does not match {args.skill.name}.\n"
            f"Run: python scripts/sync_skilltext_profile.py{flags}",
            file=sys.stderr,
        )
        return 1

    args.profile.write_text(wanted, encoding="utf-8")
    print(f"updated: {args.profile.name} ({len(wanted)} chars) from {args.skill.name}")
    # State the consequence at the point of the change, not in a doc nobody reads next.
    arm = parse_frontmatter(current)[0].get("id") or args.profile.stem
    print(
        "The prompt text changed, so profile_prompt_sha256 changes: cells already scored on "
        f"arm 'profile:{arm}' measured the old text and cannot be pooled with new ones. "
        "Re-run them."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
