# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Every judge provider `eval score` offers is one Judge accepts."""

from __future__ import annotations

import pytest

from agent_benchmarks.cli import build_parser
from agent_benchmarks.eval.judge import Judge


def _score_choices() -> list[str]:
    eval_p = build_parser()._subparsers._group_actions[0].choices["eval"]
    score_p = eval_p._subparsers._group_actions[0].choices["score"]
    return next(a.choices for a in score_p._actions if a.dest == "judge_provider")


@pytest.mark.parametrize("provider", _score_choices())
def test_every_eval_score_judge_provider_is_accepted_by_judge(provider):
    Judge(model="m", provider=provider, api_key="k")
