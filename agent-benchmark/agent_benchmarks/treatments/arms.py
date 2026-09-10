"""Concrete treatment arms for each evaluation scenario."""

import logging
from typing import Any, Dict, List, Optional

from agent_benchmarks.agent_profiles import AgentProfile
from agent_benchmarks.skills import Skill
from agent_benchmarks.utils import digest_text

from .base import AgentConfig, Treatment

logger = logging.getLogger(__name__)


class BaselineTreatment(Treatment):
    """No augmentation — the control arm (equivalent to ``without_docs``)."""

    def __init__(self, name: str = "baseline"):
        self.name = name

    def prepare(self, question_text, library_name, library_id=None) -> AgentConfig:
        return AgentConfig(metadata={"arm_kind": "baseline"})


class DocTreatment(Treatment):
    """Documentation injection via an ``MCPClient`` (the original ``with_docs``).

    Retrieves chunks for the question, reranks them, and injects the top
    survivors as context. Works for any doc source — local files, a URL, the
    Context7 HTTP API, or a real MCP server — since they all implement the same
    ``MCPClient`` retrieval contract.
    """

    def __init__(
        self,
        mcp_client,
        name: str = "docs",
        top_k: int = 5,
        rerank_threshold: float = 0.3,
        keep: int = 3,
        reranker=None,
        arm_kind: str = "docs",
    ):
        self.name = name
        self.mcp_client = mcp_client
        self.top_k = top_k
        self.keep = keep
        self.arm_kind = arm_kind
        self.reranker = reranker or self._default_reranker(rerank_threshold)

    @staticmethod
    def _default_reranker(threshold: float):
        from agent_benchmarks.eval.reranker import (
            SimpleReranker,
            SentenceTransformerReranker,
            SENTENCE_TRANSFORMERS_AVAILABLE,
        )

        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                return SentenceTransformerReranker(threshold=threshold)
            except Exception as exc:  # pragma: no cover - env dependent
                logger.warning("Semantic reranker unavailable (%s); using lexical", exc)
        return SimpleReranker(threshold=threshold)

    def prepare(self, question_text, library_name, library_id=None) -> AgentConfig:
        lib_id = library_id or library_name
        metadata: Dict[str, Any] = {
            "arm_kind": self.arm_kind,
            "raw_count": 0,
            "after_rerank": 0,
            "top_score": None,
        }
        try:
            raw_docs = self.mcp_client.get_library_docs(
                library_id=lib_id, query=question_text, max_results=self.top_k
            )
        except Exception:
            logger.exception("Context retrieval failed for arm %s", self.name)
            metadata["error"] = "retrieval_failed"
            return AgentConfig(metadata=metadata)

        metadata["raw_count"] = len(raw_docs)
        if not raw_docs:
            return AgentConfig(metadata=metadata)

        try:
            reranked = self.reranker.rerank(question_text, raw_docs)
        except Exception:
            logger.exception("Rerank failed for arm %s; using raw docs", self.name)
            metadata["error"] = "rerank_failed"
            reranked = raw_docs
        metadata["after_rerank"] = len(reranked)
        if not reranked:
            return AgentConfig(metadata=metadata)

        scores = [d.get("relevance_score", 0) for d in reranked]
        metadata["top_score"] = round(max(scores), 3) if scores else None
        return AgentConfig(injected_context=reranked[: self.keep], metadata=metadata)


class MCPAgentTreatment(Treatment):
    """Agentic MCP doc use — offer a doc-search tool; the model decides to call it.

    This is the faithful test of whether a doc source is *usable by an agent*,
    not just whether its text is relevant: the model must choose good queries
    and integrate the results. Contrast with :class:`DocTreatment`, which
    pre-injects retrieved chunks.
    """

    def __init__(
        self,
        mcp_client,
        name: str = "mcp_agent",
        max_results: int = 5,
        keep: int = 3,
        arm_kind: str = "mcp_agent",
    ):
        self.name = name
        self.mcp_client = mcp_client
        self.max_results = max_results
        self.keep = keep
        self.arm_kind = arm_kind

    def prepare(self, question_text, library_name, library_id=None) -> AgentConfig:
        from .tools import DocQueryTool

        lib_id = library_id or library_name
        tool = DocQueryTool(
            self.mcp_client, lib_id, max_results=self.max_results, keep=self.keep
        )
        return AgentConfig(
            tools=[tool],
            metadata={"arm_kind": self.arm_kind, "library_id": lib_id},
        )


class SkillAgentTreatment(Treatment):
    """Agentic skill use — offer the skill via progressive disclosure.

    The model sees only the skill's name + one-line description (in the tool
    schema) and must *decide* to load the full instructions, mirroring how
    skills are actually consumed. Running the skill's bundled scripts needs a
    sandbox and stays on the terminal-bench task track.
    """

    def __init__(self, skill: Skill, name: Optional[str] = None, max_chars: int = 12_000):
        self.skill = skill
        self.max_chars = max_chars
        self.name = name or f"skill_agent:{skill.name}"

    def prepare(self, question_text, library_name, library_id=None) -> AgentConfig:
        from .tools import ViewSkillTool

        return AgentConfig(
            tools=[ViewSkillTool(self.skill, self.max_chars)],
            metadata={
                "arm_kind": "skill_agent",
                "skill_name": self.skill.name,
                "skill_path": str(self.skill.path),
            },
        )


class AgentProfileTreatment(Treatment):
    """Agent persona prompt — swaps the answering agent's system prompt."""

    def __init__(
        self,
        profile: AgentProfile,
        name: Optional[str] = None,
        max_chars: int = 12_000,
    ):
        self.profile = profile
        self.max_chars = max_chars
        self.name = name or f"profile:{profile.id}"

    def prepare(self, question_text, library_name, library_id=None) -> AgentConfig:
        prompt = self.profile.as_prompt(self.max_chars)
        source_chars = len(self.profile.system_prompt.strip())
        # Mirror the loader's condition rather than comparing lengths: the cap appends an
        # ellipsis, so a prompt one char over the cap comes back *longer* than the source
        # and a length comparison would report it as untruncated.
        truncated = source_chars > self.max_chars
        if truncated:
            logger.warning(
                "Agent profile '%s' is %d chars and was truncated to the %d-char cap; "
                "the arm measures the truncated prompt.",
                self.profile.path, source_chars, self.max_chars,
            )
        return AgentConfig(
            system_prompt=prompt,
            metadata={
                "arm_kind": "agent_profile",
                "profile_id": self.profile.id,
                "profile_name": self.profile.name,
                "profile_path": str(self.profile.path),
                # Digest the rendered text, not the file: an edit that leaves the file
                # the same length still moves the digest, and capping moves it too, which
                # is how a batch gate notices that two cells measured different prompts.
                # This is the profile's *contribution*, not necessarily the whole prompt
                # sent — a prompt-middleware plugin appends to it afterwards, and
                # ``PluginWrappedTreatment`` records ``system_prompt_sha256`` for that.
                "profile_prompt_sha256": digest_text(prompt),
                "profile_prompt_chars": len(prompt),
                "profile_prompt_chars_source": source_chars,
                "profile_prompt_truncated": truncated,
            },
        )


class SkillTreatment(Treatment):
    """Agent skill injected as context (skill-as-context evaluation mode).

    This is the cheap, single-shot mode: the skill body is injected like a doc
    chunk. The faithful agentic mode (the agent decides to invoke the skill and
    run its bundled scripts) belongs on the terminal-bench task track.
    """

    def __init__(self, skill: Skill, name: Optional[str] = None, max_chars: int = 12_000):
        self.skill = skill
        self.max_chars = max_chars
        self.name = name or f"skill:{skill.name}"

    def prepare(self, question_text, library_name, library_id=None) -> AgentConfig:
        content = self.skill.as_context(self.max_chars)
        # `as_context` truncates silently. An unrecorded truncation is how a skill arm
        # ends up measuring three quarters of a skill while the artifact reads as if it
        # measured all of it, so record it on the same terms as the profile arm.
        source_chars = len(self.skill.body.strip())
        truncated = source_chars > self.max_chars
        if truncated:
            logger.warning(
                "Skill '%s' body is %d chars and was truncated to the %d-char cap; "
                "the arm measures the truncated skill.",
                self.skill.path, source_chars, self.max_chars,
            )
        chunk = {
            "content": content,
            "source": f"skill:{self.skill.name}",
            "relevance_score": 1.0,
        }
        return AgentConfig(
            injected_context=[chunk],
            # The skill body is the same for every question, so it is a genuine
            # cacheable prefix — unlike DocTreatment's query-driven chunks.
            context_is_static=True,
            metadata={
                "arm_kind": "skill",
                "skill_name": self.skill.name,
                "skill_path": str(self.skill.path),
                # Three sizes, because two of them are easy to confuse. `skill_chars` is
                # the body after the cap, so it pairs with `skill_chars_source` the way
                # `profile_prompt_chars` pairs with its source and the difference is what
                # the cap cut. `skill_chars_injected` is the whole rendered block, header
                # and description included — which is why it exceeds the source for a
                # skill that was never truncated, and why it is not the number to compare
                # against the cap.
                "skill_chars": min(source_chars, self.max_chars),
                "skill_chars_source": source_chars,
                "skill_chars_injected": len(content),
                "skill_truncated": truncated,
            },
        )


class CombinedTreatment(Treatment):
    """Combine multiple treatments into a single arm (e.g., docs + skill).

    This treatment merges the contexts, tools, and metadata from multiple
    sub-treatments, allowing evaluation of combined approaches (e.g., "does
    docs + skill together outperform skill alone?").

    The sub-treatments are prepared independently, then their outputs are merged:
    - injected_context: concatenated in the order the arm spec lists them
    - tools: concatenated (for agentic arms)
    - system_prompt: first non-None value wins
    - metadata: tracks all sub-treatment metadata

    Example spec: ``docs+skill:data/skills/fastcontext``
    """

    def __init__(self, treatments: List[Treatment], name: Optional[str] = None):
        self.treatments = treatments
        self.name = name or "+".join(t.name for t in treatments)

    def prepare(self, question_text, library_name, library_id=None) -> AgentConfig:
        # Prepare all sub-treatments independently
        configs = [
            t.prepare(question_text, library_name, library_id) for t in self.treatments
        ]

        # Merge injected contexts in spec order — `docs+skill:x` and `skill:x+docs`
        # therefore send the same blocks in a different order, which is the caller's choice.
        merged_context = []
        for cfg in configs:
            merged_context.extend(cfg.injected_context)

        # Merge tools (for agentic arms - rare, but supported)
        merged_tools = []
        for cfg in configs:
            merged_tools.extend(cfg.tools)

        # Merge metadata - track each sub-treatment's contribution
        merged_metadata = {
            "arm_kind": "combined",
            "combined_count": len(self.treatments),
            "treatments": [],
        }
        for t, cfg in zip(self.treatments, configs, strict=True):
            merged_metadata["treatments"].append(
                {"name": t.name, "arm_kind": cfg.metadata.get("arm_kind"), **cfg.metadata}
            )

        # System prompt: first non-None wins (profiles rarely combined with docs/skills).
        # More than one means the later ones never reach the model, which would make
        # the arm's metadata claim a treatment the answer never saw — warn loudly.
        with_prompt = [t.name for t, c in zip(self.treatments, configs, strict=True) if c.system_prompt]
        if len(with_prompt) > 1:
            logger.warning(
                "Combined arm '%s' supplies %d system prompts (%s); only '%s' is sent — "
                "the rest are dropped. Split them into separate arms to measure both.",
                self.name, len(with_prompt), ", ".join(with_prompt), with_prompt[0],
            )
            merged_metadata["dropped_system_prompts"] = with_prompt[1:]
        system_prompt = next((c.system_prompt for c in configs if c.system_prompt), None)

        # A prefix is only reusable if *everything* in it is; one query-driven
        # doc chunk anywhere in the merged context makes the whole block vary.
        context_is_static = all(
            c.context_is_static for c in configs if c.injected_context
        )

        return AgentConfig(
            system_prompt=system_prompt,
            injected_context=merged_context,
            tools=merged_tools,
            context_is_static=context_is_static,
            metadata=merged_metadata,
        )
