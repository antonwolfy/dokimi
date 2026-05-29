"""Agent skills: load ``SKILL.md`` packages for skill-augmented evaluation."""

from .loader import Skill, load_skill, discover_skills

__all__ = ["Skill", "load_skill", "discover_skills"]
