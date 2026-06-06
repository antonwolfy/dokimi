"""Load agent persona prompts (answering-agent system prompts).

An agent profile is a Markdown file with optional YAML frontmatter::

    ---
    id: concise_expert
    name: Concise Expert
    description: Terse, code-first senior engineer.
    ---
    You are a senior systems engineer. Answer tersely, lead with code, …

The body (frontmatter stripped) is the system prompt. When no frontmatter is
present the whole file is the system prompt and the id is derived from the
filename.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List

from doc_benchmarks.utils import parse_frontmatter


@dataclass
class AgentProfile:
    """A loaded agent persona prompt.

    Attributes:
        id: Stable identifier (frontmatter ``id`` or the filename stem).
        name: Human-readable name.
        description: One-line summary of the profile.
        system_prompt: The system prompt sent to the answering agent.
        path: Source file path.
    """

    id: str
    name: str
    description: str
    system_prompt: str
    path: Path


def load_agent_profile(path) -> AgentProfile:
    """Load a single agent profile from a Markdown file.

    Args:
        path: Path to the profile ``.md`` file.

    Returns:
        An :class:`AgentProfile`.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the profile has no system-prompt body.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Agent profile not found: {p}")

    meta, body = parse_frontmatter(p.read_text(encoding="utf-8"))
    system_prompt = body.strip()
    if not system_prompt:
        raise ValueError(
            f"Agent profile '{p}' has an empty body; the body is the system prompt."
        )

    pid = str(meta.get("id") or p.stem).strip()
    if not pid:
        raise ValueError(f"Agent profile '{p}' has an empty 'id' after normalization.")
    return AgentProfile(
        id=pid,
        name=str(meta.get("name") or pid).strip(),
        description=str(meta.get("description") or "").strip(),
        system_prompt=system_prompt,
        path=p,
    )


def discover_agent_profiles(root) -> List[AgentProfile]:
    """Load every ``.md`` agent profile under *root*."""
    root = Path(root)
    return [load_agent_profile(p) for p in sorted(root.glob("*.md"))]
