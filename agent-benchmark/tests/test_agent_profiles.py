"""Agent persona prompts: arm naming, provenance, and the committed dpnp fixtures."""

import logging
from pathlib import Path

import pytest

from agent_benchmarks.agent_profiles import load_agent_profile
from agent_benchmarks.treatments.arms import AgentProfileTreatment, BaselineTreatment, CombinedTreatment
from agent_benchmarks.treatments.factory import create_treatment, create_treatments
from agent_benchmarks.utils import digest_text

PROFILE_DIR = Path(__file__).resolve().parents[1] / "data" / "agent_profiles"
SKILL_DIR = Path(__file__).resolve().parents[1] / "data" / "skills"
# The dpnp persona ladder. Each rung changes only what the system prompt carries:
#   dpnp-expert        the deliverable persona -- identity and judgment, no API names
#   dpnp-expert-style  voice only, no dpnp facts (the first rung that was measured)
#   dpnp-skilltext     the skill's own text, sent as a prompt (channel control)
#   dpnp-briefing      a fact sheet (experimental rung, kept for comparison)
#   generic-expert     a persona with no dpnp in it at all (negative control)
DPNP_PROFILES = [
    "dpnp-expert",
    "dpnp-expert-style",
    "dpnp-skilltext",
    "dpnp-briefing",
    "generic-expert",
]


def write_profile(tmp_path, stem, frontmatter, body):
    p = tmp_path / f"{stem}.md"
    p.write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")
    return p


# --- arm naming -----------------------------------------------------------


def test_arm_name_comes_from_frontmatter_id_not_the_filename(tmp_path):
    p = write_profile(tmp_path, "some-file", "id: chosen-id\n", "You are an expert.\n")
    assert create_treatment(f"profile:{p.as_posix()}").name == "profile:chosen-id"


def test_arm_name_falls_back_to_filename_stem_when_frontmatter_is_malformed(tmp_path):
    """A YAML typo is silent: meta becomes {} and the id falls back to the stem.

    The committed fixtures are named so that stem == id, which makes them immune.
    """
    p = write_profile(tmp_path, "typo-profile", "id: broken\n  name: [unclosed\n", "You are an expert.\n")
    assert load_agent_profile(p).id == "typo-profile"
    assert create_treatment(f"profile:{p.as_posix()}").name == "profile:typo-profile"


@pytest.mark.parametrize("profile_id", DPNP_PROFILES)
def test_committed_fixture_stem_equals_id(profile_id):
    """Guards the arm name in every artifact against a frontmatter typo."""
    profile = load_agent_profile(PROFILE_DIR / f"{profile_id}.md")
    assert profile.id == profile_id == profile.path.stem


# --- the prompt actually reaches the model --------------------------------


@pytest.mark.parametrize("profile_id", DPNP_PROFILES)
def test_prompt_reaches_agent_config_verbatim(profile_id):
    profile = load_agent_profile(PROFILE_DIR / f"{profile_id}.md")
    cfg = AgentProfileTreatment(profile).prepare("some question", "dpnp")
    assert cfg.system_prompt == profile.system_prompt
    assert "description:" not in cfg.system_prompt  # no frontmatter leak


def test_empty_body_is_rejected(tmp_path):
    p = write_profile(tmp_path, "hollow", "id: hollow\n", "\n")
    with pytest.raises(ValueError, match="empty body"):
        load_agent_profile(p)


# --- provenance -----------------------------------------------------------


def test_metadata_stamps_path_and_prompt_digest(tmp_path):
    p = write_profile(tmp_path, "stamped", "id: stamped\n", "You are an expert.\n")
    meta = create_treatment(f"profile:{p.as_posix()}").prepare("q", "dpnp").metadata
    assert meta["arm_kind"] == "agent_profile"
    assert meta["profile_path"] == str(p)
    assert meta["profile_prompt_sha256"] == digest_text("You are an expert.")
    assert meta["profile_prompt_chars"] == len("You are an expert.")


def test_editing_the_prompt_changes_the_recorded_digest(tmp_path):
    """Without this, two different prompts are indistinguishable in an artifact."""
    p = write_profile(tmp_path, "mutable", "id: mutable\n", "You are an expert.\n")
    before = create_treatment(f"profile:{p.as_posix()}").prepare("q", "dpnp").metadata
    write_profile(tmp_path, "mutable", "id: mutable\n", "You are an expert!\n")
    after = create_treatment(f"profile:{p.as_posix()}").prepare("q", "dpnp").metadata
    assert before["profile_prompt_sha256"] != after["profile_prompt_sha256"]


def test_frontmatter_only_edits_do_not_change_the_prompt_digest(tmp_path):
    """The digest covers the prompt text, which is what the model actually sees."""
    p = write_profile(tmp_path, "renamed", "id: renamed\nname: First\n", "You are an expert.\n")
    before = create_treatment(f"profile:{p.as_posix()}").prepare("q", "dpnp").metadata
    write_profile(tmp_path, "renamed", "id: renamed\nname: Second\n", "You are an expert.\n")
    after = create_treatment(f"profile:{p.as_posix()}").prepare("q", "dpnp").metadata
    assert before["profile_prompt_sha256"] == after["profile_prompt_sha256"]
    assert before["profile_name"] != after["profile_name"]


# --- combined arms must not silently drop a persona -----------------------


def test_combined_arm_warns_and_records_dropped_system_prompts(tmp_path, caplog):
    a = write_profile(tmp_path, "first", "id: first\n", "Prompt A.\n")
    b = write_profile(tmp_path, "second", "id: second\n", "Prompt B.\n")
    combined = CombinedTreatment(
        [create_treatment(f"profile:{a.as_posix()}"), create_treatment(f"profile:{b.as_posix()}")]
    )
    with caplog.at_level(logging.WARNING):
        cfg = combined.prepare("q", "dpnp")
    assert cfg.system_prompt == "Prompt A."
    assert cfg.metadata["dropped_system_prompts"] == ["profile:second"]
    assert "only 'profile:first' is sent" in caplog.text


def test_combined_arm_stays_quiet_when_only_one_prompt_is_present(tmp_path, caplog):
    """docs+skill combos supply no system prompt — they must not start warning."""
    a = write_profile(tmp_path, "solo", "id: solo\n", "Prompt A.\n")
    combined = CombinedTreatment([BaselineTreatment(), create_treatment(f"profile:{a.as_posix()}")])
    with caplog.at_level(logging.WARNING):
        cfg = combined.prepare("q", "dpnp")
    assert cfg.system_prompt == "Prompt A."
    assert "dropped_system_prompts" not in cfg.metadata
    assert caplog.text == ""


# --- what each rung of the ladder is allowed to contain -------------------
#
# The three rungs are only interpretable as a comparison if they stay distinct. Nothing in
# the loader enforces that -- a well-meaning edit can turn the persona into a second copy
# of the skill, at which point `p:expert` and `p:skilltext` measure the same thing and the
# earlier cells are silently incomparable to the later ones. These tests pin the contrast.


def five_grams(text: str) -> set[tuple[str, ...]]:
    words = text.lower().split()
    return {tuple(words[i : i + 5]) for i in range(len(words) - 4)}


def skill_text(skill_id: str) -> str:
    from agent_benchmarks.skills import load_skill

    return load_skill(SKILL_DIR / skill_id).as_context(12_000)


# A persona that names an API is documentation, and it dates the way documentation dates.
# The denylist is deliberately wider than `dpnp.`: a keyword argument or a bare call is just
# as much an API name, and the first version of this test let all of them through.
API_SHAPES = (
    r"\b(?:dpnp|dpctl|numpy|np|sycl)\s*\.\s*\w+",  # dotted names, spaced or not
    r"\b(?:usm_type|sycl_queue|asnumpy|synchronize_array_data)\b",  # bare dpnp API names
    r"\b(?:device|dtype|usm_type|out|order)\s*=",  # keyword arguments
    r"\b[a-z_][a-z0-9_]*\(\s*\)",  # bare zero-arg calls, e.g. asnumpy()
)


def test_deliverable_persona_carries_no_api_names():
    """A persona states how to think. The moment it lists an API, it is documentation --
    and documentation in a system prompt also rots without a test noticing."""
    import re

    prompt = load_agent_profile(PROFILE_DIR / "dpnp-expert.md").system_prompt
    leaked = sorted({m for shape in API_SHAPES for m in re.findall(shape, prompt)})
    assert leaked == [], f"persona names concrete APIs: {leaked}"
    assert "```" not in prompt, "persona contains a code block"


def test_the_api_name_check_would_actually_fire():
    """The first version of this guard only matched the literal `dpnp.`, so a persona could
    grow keyword arguments and bare calls untouched. Pin that it no longer can."""
    import re

    contaminated = (
        "Call asnumpy() once at the edge, pass usm_type='device' and sycl_queue=q to "
        "dpctl.tensor.empty, and set dtype=float32."
    )
    leaked = {m for shape in API_SHAPES for m in re.findall(shape, contaminated)}
    assert leaked, "the API-name guard is vacuous"


def test_deliverable_persona_is_not_a_paraphrase_of_the_skill():
    persona = five_grams(load_agent_profile(PROFILE_DIR / "dpnp-expert.md").system_prompt)
    skill = five_grams(skill_text("dpnp-quickstart"))
    shared = persona & skill
    assert not shared, f"persona reuses skill wording: {sorted(shared)[:3]}"


def test_channel_control_is_the_skill_text_verbatim():
    """`dpnp-skilltext` exists to hold content constant while changing the channel: the same
    bytes the `skills` arm injects as context, sent as a system prompt instead. If the skill
    is edited and this fixture is not, the two arms differ in content *and* channel, and the
    comparison stops isolating anything."""
    profile = load_agent_profile(PROFILE_DIR / "dpnp-skilltext.md")
    assert profile.system_prompt == skill_text("dpnp-quickstart").strip()


def test_negative_control_persona_mentions_no_product():
    prompt = load_agent_profile(PROFILE_DIR / "generic-expert.md").system_prompt.lower()
    for product in ("dpnp", "dpctl", "sycl"):
        assert product not in prompt, f"the generic control mentions {product}"


# --- the measurement arms build together ---------------------------------


def test_the_three_measurement_arms_build_in_one_run():
    specs = [
        "baseline",
        f"profile:{(PROFILE_DIR / 'dpnp-expert.md').as_posix()}",
        f"profile:{(PROFILE_DIR / 'generic-expert.md').as_posix()}",
    ]
    assert [t.name for t in create_treatments(specs)] == [
        "baseline",
        "profile:dpnp-expert",
        "profile:generic-expert",
    ]


def test_two_profiles_sharing_an_id_are_refused(tmp_path):
    a = write_profile(tmp_path, "one", "id: same\n", "Prompt A.\n")
    b = write_profile(tmp_path, "two", "id: same\n", "Prompt B.\n")
    with pytest.raises(ValueError):
        create_treatments([f"profile:{a.as_posix()}", f"profile:{b.as_posix()}"])
