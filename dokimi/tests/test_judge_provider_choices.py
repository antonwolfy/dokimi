# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Every judge provider the CLI offers is one Judge accepts.

``benchmark run/preflight/batch`` (and the arms, subjects and orchestrate
commands) offered ``openai-codex`` as a judge provider, which ``Judge`` rejects
with ValueError -- on ``benchmark run`` only after every answer had been paid for.
"""

from __future__ import annotations

import argparse

import pytest

from dokimi.cli import build_parser
from dokimi.eval.judge import JUDGE_PROVIDERS, Judge


def _score_choices() -> list[str]:
    eval_p = build_parser()._subparsers._group_actions[0].choices["eval"]
    score_p = eval_p._subparsers._group_actions[0].choices["score"]
    return next(a.choices for a in score_p._actions if a.dest == "judge_provider")


@pytest.mark.parametrize("provider", _score_choices())
def test_every_eval_score_judge_provider_is_accepted_by_judge(provider):
    Judge(model="m", provider=provider, api_key="k")


def _judge_provider_actions(parser, path=()):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                yield from _judge_provider_actions(sub, path + (name,))
        elif action.dest in ("judge_provider", "escalate_provider") and action.choices:
            yield " ".join(path) + " " + action.option_strings[0], action.choices


#: Judge-role flags whose value never reaches ``Judge``: the novelty commands call
#: the model through ``novelty.client.LLMClient`` -> ``llm_call_with_usage``, which
#: does route ``openai-codex``.
NOT_THE_JUDGE_CLASS = {"novelty analyze --judge-provider", "novelty probe --judge-provider"}


def test_cli_offers_only_judge_providers_the_judge_accepts():
    actions = dict(_judge_provider_actions(build_parser()))
    for flag in ("benchmark run --judge-provider", "arms run --judge-provider",
                 "arms matrix-run --judge-provider", "subjects run --judge-provider",
                 "evaluate --judge-provider"):
        assert flag in actions
    assert NOT_THE_JUDGE_CLASS <= actions.keys()
    for flag in NOT_THE_JUDGE_CLASS:
        del actions[flag]
    offenders = {
        flag: sorted(set(choices) - set(JUDGE_PROVIDERS))
        for flag, choices in actions.items()
        if not set(choices) <= set(JUDGE_PROVIDERS)
    }
    assert not offenders


def test_benchmark_run_rejects_openai_codex_judge_at_parse_time(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(
            ["benchmark", "run", "--library", "x", "--judge-provider", "openai-codex"]
        )
    assert exc.value.code == 2
    assert "invalid choice: 'openai-codex'" in capsys.readouterr().err


@pytest.mark.parametrize("provider", JUDGE_PROVIDERS)
def test_every_listed_judge_provider_is_accepted_by_judge(provider):
    Judge(model="m", provider=provider, api_key="k")
