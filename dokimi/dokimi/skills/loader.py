# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Load agent skills from ``SKILL.md`` packages.

A skill follows the Claude Code / Agent Skills convention: a ``SKILL.md`` file
with YAML frontmatter (at least ``name`` and ``description``) followed by a
Markdown body of instructions. Optional bundled files (scripts, references),
beside ``SKILL.md`` or nested in subdirectories,
live alongside it and are recorded but not executed by the loader — executing
bundled scripts is the job of the agentic task track, not this loader.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dokimi.utils import parse_frontmatter


@dataclass
class Skill:
    """A loaded skill package.

    Attributes:
        name: Skill identifier from frontmatter (falls back to the directory name).
        description: One-line description (used as the trigger hint).
        body: Markdown instruction body with frontmatter stripped.
        path: Path to the ``SKILL.md`` file.
        resources: Sibling files bundled with the skill (scripts, references).
    """

    name: str
    description: str
    body: str
    path: Path
    resources: List[Path] = field(default_factory=list)

    def as_context(self, max_chars: int = 12_000) -> str:
        """Render the skill as an injectable context block, capped at *max_chars*.

        The 12,000-char default (≈3k tokens) is an inherited convention, not a tuned
        value: it arrived with this loader and no design note or commit justifies the figure.
        Treat it as a guardrail against a fixture that would dominate the prompt, and
        change it only deliberately — every channel must cap at the *same* number, or
        a ``profile:`` arm and a ``skill:`` arm stop being comparable.

        Three channels carry this cap, and only two of them are *injected*:
        ``SKILL.md`` bodies (here) and profile bodies (``AgentProfile.as_prompt``).
        ``tests/test_agent_profiles.py`` fails once either crosses 95%, so growth is
        caught before it truncates anything. The third is
        ``ViewSkillTool``, which serves bundled resource files at the same cap; there a
        committed resource is already over it, so the test allowlists what is known to be
        truncated rather than pretending the cap is unreached. Truncation is recorded in
        every channel — see ``SkillTreatment`` and ``ViewSkillTool.telemetry_metadata``.
        """
        body = self.body.strip()
        if len(body) > max_chars:
            body = body[:max_chars].rstrip() + "\n…"
        return f"# Skill: {self.name}\n{self.description}\n\n{body}"

    def resource_manifest(self, max_files: int = 200) -> str:
        """List the skill's bundled files, as paths relative to ``SKILL.md``.

        This is the skill's *inventory*, not its content: a judge shown only the
        answer cannot tell a real bundled path from an invented one, and scores a
        correctly-cited `patterns/simd.md` down as a fabrication. Measured on the
        81-question perf set: 17 of 81 skill-arm answers were marked
        "fabricated"/"non-existent" for citing files that all exist, costing the
        arm 22.5 aggregate points on those questions — enough to invert the
        arm comparison. Paths only; the bodies would not fit the judge's budget,
        and existence is what the judge cannot otherwise check.
        """
        root = self.path.parent
        rels = []
        for p in self.resources[:max_files]:
            try:
                rels.append(p.relative_to(root).as_posix())
            except ValueError:  # pragma: no cover - resources are collected under root
                rels.append(p.name)
        if not rels:
            return ""
        more = len(self.resources) - len(rels)
        lines = [f"Files bundled with skill '{self.name}' (these all exist):"]
        lines += [f"  {r}" for r in rels]
        if more > 0:
            lines.append(f"  … and {more} more")
        return "\n".join(lines)


def _resolve_skill_file(path: Path) -> Path:
    """Resolve a skill reference (file or directory) to its ``SKILL.md`` file."""
    if path.is_dir():
        candidate = path / "SKILL.md"
        if not candidate.exists():
            raise FileNotFoundError(f"No SKILL.md found in skill directory: {path}")
        return candidate
    if path.is_file():
        if path.name != "SKILL.md":
            raise ValueError(f"Expected a SKILL.md file, got: {path}")
        return path
    raise FileNotFoundError(f"Skill path does not exist: {path}")


def load_skill(path) -> Skill:
    """Load a single skill from a ``SKILL.md`` file or its containing directory.

    Args:
        path: Path to a ``SKILL.md`` file or a directory containing one.

    Returns:
        A :class:`Skill`.

    Raises:
        FileNotFoundError: If no ``SKILL.md`` can be located.
        ValueError: If required frontmatter fields are missing.
    """
    skill_file = _resolve_skill_file(Path(path))
    meta, body = parse_frontmatter(skill_file.read_text(encoding="utf-8"))

    name = str(meta.get("name") or skill_file.parent.name).strip()
    if not name:
        raise ValueError(f"Skill at '{skill_file}' has an empty 'name' after normalization.")
    description = str(meta.get("description") or "").strip()
    if not description:
        raise ValueError(
            f"Skill '{name}' ({skill_file}) is missing a 'description' in its "
            "frontmatter; the description is the skill's trigger hint."
        )

    # Recurse: skills commonly keep their detail in subdirectories
    # (``references/``, ``patterns/``, ``scripts/``) and load them on demand, so a
    # flat scan would report no resources and silently disable the file picker.
    root = skill_file.parent
    resources = sorted(
        p for p in root.rglob("*")
        if p.is_file() and p != skill_file and "__pycache__" not in p.parts
    )
    return Skill(
        name=name,
        description=description,
        body=body,
        path=skill_file,
        resources=resources,
    )


def discover_skills(root) -> List[Skill]:
    """Load every skill under *root* (each subdirectory with a ``SKILL.md``)."""
    root = Path(root)
    skills: List[Skill] = []
    for skill_file in sorted(root.rglob("SKILL.md")):
        skills.append(load_skill(skill_file))
    return skills
