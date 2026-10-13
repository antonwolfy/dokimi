# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Core treatment-arm abstraction."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


class Tool(ABC):
    """A callable the agent may invoke during an agentic arm.

    Tools turn a treatment from "inject this context" into "offer this
    capability and let the model decide whether to use it" — e.g. querying an
    MCP doc server or loading a skill on demand (progressive disclosure).
    """

    #: Tool name exposed to the model (must be a valid function name).
    name: str = "tool"
    #: One-line description the model uses to decide when to call it.
    description: str = ""
    #: JSON-schema ``parameters`` object for the tool's arguments.
    parameters: Dict[str, Any] = {"type": "object", "properties": {}}

    @abstractmethod
    def call(self, **kwargs) -> str:
        """Execute the tool and return a string result for the model."""
        raise NotImplementedError

    def schema(self) -> Dict[str, Any]:
        """Return the OpenAI/litellm tool schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def telemetry_metadata(self) -> Dict[str, Any]:
        """Return stable, non-secret metadata for usage/discoverability reports."""
        return {
            "name": self.name,
            "kind": getattr(self, "kind", "tool"),
        }


@dataclass
class AgentConfig:
    """The agent setup produced by a treatment for one question.

    Attributes:
        system_prompt: Optional system prompt (agent persona). ``None`` keeps
            the model's default behavior.
        injected_context: Retrieved/loaded chunks to prepend to the prompt.
            Each chunk is a dict with at least a ``content`` key, matching the
            shape returned by ``MCPClient.get_library_docs``.
        tools: Tools offered to the model. When non-empty, the arm is run
            through the agentic tool-calling loop instead of single-shot
            injection.
        metadata: Free-form provenance for the report (retrieval stats, profile
            id, skill name, …).
        context_is_static: True when ``injected_context`` does not depend on the
            question — a fixed skill body, not query-driven retrieval. Only then
            is the context a reusable prompt prefix worth a provider cache
            breakpoint (see :mod:`agent_benchmarks.caching`); marking volatile
            context static would pay the cache-write surcharge on every call and
            never hit.
        judge_reference: Material about the treatment that the *judge* needs but
            the answering model does not get in its prompt — currently a skill's
            bundled-file manifest. A judge shown only the answer cannot tell a
            real bundled path from an invented one and penalises correct
            citations as fabrications, which is an arm-comparison defect rather
            than a scoring preference (see ``Skill.resource_manifest``). This
            holds only what is *not* already in ``injected_context``; the runner
            concatenates the two. Empty for treatments whose material is
            query-driven and unknown until the agent asks for it.
    """

    system_prompt: Optional[str] = None
    injected_context: List[Dict[str, Any]] = field(default_factory=list)
    tools: List[Tool] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    context_is_static: bool = False
    judge_reference: str = ""
    #: For an agentic arm whose material is too large to show whole (a skill
    #: catalog): builds the reference from the skills the agent loaded, called
    #: after the loop. Replaces ``judge_reference`` when set.
    judge_reference_for_loaded: Optional[Callable[[List[str]], str]] = None

    @property
    def has_context(self) -> bool:
        return bool(self.injected_context)

    @property
    def is_agentic(self) -> bool:
        return bool(self.tools)


class Treatment(ABC):
    """One arm of an N-way evaluation.

    Subclasses implement :meth:`prepare`, returning the :class:`AgentConfig`
    used to answer a single question. Treatments must be safe to reuse across
    questions (any per-question state lives in the returned config).
    """

    #: Stable arm identifier used as the key in result/report tables.
    name: str = "treatment"

    @abstractmethod
    def prepare(
        self,
        question_text: str,
        library_name: str,
        library_id: Optional[str] = None,
    ) -> AgentConfig:
        """Build the agent config for *question_text*."""
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<{type(self).__name__} name={self.name!r}>"
