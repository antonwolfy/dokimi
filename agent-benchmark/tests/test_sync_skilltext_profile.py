"""The channel-control sync script: `scripts/sync_skilltext_profile.py`.

`test_agent_profiles.py::test_channel_control_is_the_skill_text_verbatim` is what fails when
the skill and the profile drift apart, and it names this script as the fix. These tests are
what make that instruction true — a fix command that does not actually re-sync is worse than
no command, because the next person edits the fixture by hand and gets the frontmatter wrong.
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "sync_skilltext_profile.py"


def load_script():
    """Import the script by path — `scripts/` is not a package and must not become one."""
    spec = importlib.util.spec_from_file_location("sync_skilltext_profile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = load_script()


def write_skill(tmp_path, body, name="tmp-skill"):
    d = tmp_path / name
    d.mkdir()
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: A skill.\n---\n{body}", encoding="utf-8"
    )
    return d


FRONTMATTER = "---\nid: tmp-skilltext\nname: Text as Prompt\ndescription: Channel control.\n---\n"


# --- frontmatter handling -------------------------------------------------


def test_frontmatter_is_taken_verbatim_not_re_serialized():
    """Re-serializing YAML reorders keys and reflows the description, so every run
    would show a diff and real drift would be indistinguishable from formatting churn."""
    text = FRONTMATTER + "old body\n"
    assert sync.frontmatter_block(text) == FRONTMATTER


def test_no_frontmatter_reads_as_empty():
    assert sync.frontmatter_block("just a body\n") == ""


def test_unterminated_frontmatter_reads_as_empty():
    assert sync.frontmatter_block("---\nid: x\nno terminator\n") == ""


# --- render ---------------------------------------------------------------


def test_render_keeps_the_frontmatter_and_replaces_the_body(tmp_path):
    skill = write_skill(tmp_path, "New instructions.")
    profile = tmp_path / "tmp-skilltext.md"
    profile.write_text(FRONTMATTER + "stale body\n", encoding="utf-8")

    rendered = sync.render(skill, profile)
    assert rendered.startswith(FRONTMATTER)
    assert "New instructions." in rendered
    assert "stale body" not in rendered


def test_rendered_body_is_the_skill_arm_text_byte_for_byte(tmp_path):
    """The point of the control is that both channels carry identical bytes."""
    from agent_benchmarks.agent_profiles import load_agent_profile
    from agent_benchmarks.skills import load_skill

    skill = write_skill(tmp_path, "Do the thing.\n\n- and the other thing")
    profile = tmp_path / "tmp-skilltext.md"
    profile.write_text(FRONTMATTER + "stale\n", encoding="utf-8")
    profile.write_text(sync.render(skill, profile), encoding="utf-8")

    injected = load_skill(skill).as_context(sync.MAX_CHARS).strip()
    assert load_agent_profile(profile).system_prompt == injected


def test_render_refuses_a_profile_that_does_not_exist(tmp_path):
    """Deriving frontmatter would name the arm after the filename stem behind your back."""
    skill = write_skill(tmp_path, "body")
    with pytest.raises(SystemExit, match="no such profile"):
        sync.render(skill, tmp_path / "absent.md")


def test_render_refuses_a_profile_without_frontmatter(tmp_path):
    """The arm name comes from the frontmatter id; losing it silently renames the arm."""
    skill = write_skill(tmp_path, "body")
    profile = tmp_path / "bare.md"
    profile.write_text("no frontmatter here\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no YAML frontmatter"):
        sync.render(skill, profile)


# --- the CLI --------------------------------------------------------------


def run_main(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["sync_skilltext_profile.py", *argv])
    return sync.main()


def test_check_fails_when_the_skill_was_edited_and_the_profile_was_not(tmp_path, monkeypatch):
    skill = write_skill(tmp_path, "Original.")
    profile = tmp_path / "tmp-skilltext.md"
    profile.write_text(FRONTMATTER + "stale\n", encoding="utf-8")
    profile.write_text(sync.render(skill, profile), encoding="utf-8")
    assert run_main(monkeypatch, "--check", "--skill", str(skill), "--profile", str(profile)) == 0

    (skill / "SKILL.md").write_text(
        "---\nname: tmp-skill\ndescription: A skill.\n---\nEdited.", encoding="utf-8"
    )
    assert run_main(monkeypatch, "--check", "--skill", str(skill), "--profile", str(profile)) == 1


def test_check_does_not_write(tmp_path, monkeypatch):
    skill = write_skill(tmp_path, "Original.")
    profile = tmp_path / "tmp-skilltext.md"
    profile.write_text(FRONTMATTER + "stale\n", encoding="utf-8")
    before = profile.read_text(encoding="utf-8")
    assert run_main(monkeypatch, "--check", "--skill", str(skill), "--profile", str(profile)) == 1
    assert profile.read_text(encoding="utf-8") == before


def test_sync_then_check_is_clean(tmp_path, monkeypatch):
    skill = write_skill(tmp_path, "Original.")
    profile = tmp_path / "tmp-skilltext.md"
    profile.write_text(FRONTMATTER + "stale\n", encoding="utf-8")
    assert run_main(monkeypatch, "--skill", str(skill), "--profile", str(profile)) == 0
    assert run_main(monkeypatch, "--check", "--skill", str(skill), "--profile", str(profile)) == 0


def test_sync_is_idempotent(tmp_path, monkeypatch):
    skill = write_skill(tmp_path, "Original.")
    profile = tmp_path / "tmp-skilltext.md"
    profile.write_text(FRONTMATTER + "stale\n", encoding="utf-8")
    run_main(monkeypatch, "--skill", str(skill), "--profile", str(profile))
    once = profile.read_text(encoding="utf-8")
    run_main(monkeypatch, "--skill", str(skill), "--profile", str(profile))
    assert profile.read_text(encoding="utf-8") == once


def test_missing_skill_directory_is_an_error(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="no such skill directory"):
        run_main(monkeypatch, "--skill", str(tmp_path / "nope"), "--profile", str(tmp_path / "p.md"))


def test_the_committed_fixture_is_in_sync(monkeypatch):
    """Same guarantee as the verbatim test in test_agent_profiles.py, through the script
    that is advertised as the fix — so the instruction and the assertion cannot disagree."""
    assert run_main(monkeypatch, "--check") == 0
