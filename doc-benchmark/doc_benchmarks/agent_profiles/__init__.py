"""Agent persona prompts: load system prompts that shape the answering agent.

These are deliberately *not* called "personas" — in this codebase ``persona``
means a synthetic user who asks questions (``doc_benchmarks/personas``). An
agent profile is a property of the *answering* agent (its system prompt).
"""

from .loader import AgentProfile, load_agent_profile, discover_agent_profiles

__all__ = ["AgentProfile", "load_agent_profile", "discover_agent_profiles"]
