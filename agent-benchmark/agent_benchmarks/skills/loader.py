"""Load agent skills from ``SKILL.md`` packages.

A skill follows the Claude Code / Agent Skills convention: a ``SKILL.md`` file
with YAML frontmatter (at least ``name`` and ``description``) followed by a
Markdown body of instructions. Optional sibling files (scripts, references)
live alongside it and are recorded but not executed by the loader — executing
bundled scripts is the job of the agentic task track, not this loader.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from agent_benchmarks.utils import parse_frontmatter


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
        """Render the skill as an injectable context block."""
        body = self.body.strip()
        if len(body) > max_chars:
            body = body[:max_chars].rstrip() + "\n…"
        return f"# Skill: {self.name}\n{self.description}\n\n{body}"


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

    resources = sorted(
        p for p in skill_file.parent.iterdir()
        if p.is_file() and p.name != skill_file.name
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
