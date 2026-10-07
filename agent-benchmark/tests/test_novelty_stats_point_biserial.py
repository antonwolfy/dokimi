# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""The shared point-biserial helper, and the cases where it refuses to return a number."""

from __future__ import annotations

import pytest

from agent_benchmarks.eval.stats import point_biserial


def test_an_item_the_strong_respondents_pass_discriminates_positively():
    result = point_biserial([True, True, False, False], [0.9, 0.8, 0.4, 0.3])
    assert result["r"] > 0.9
    assert (result["n"], result["n_pass"], result["reason"]) == (4, 2, None)


def test_the_sign_flips_when_the_weak_respondents_pass_it():
    assert point_biserial([False, False, True, True], [0.9, 0.8, 0.4, 0.3])["r"] < -0.9


@pytest.mark.parametrize(
    ("flags", "totals", "reason"),
    [
        ([True, False], [0.9, 0.2], "fewer than 3 respondents"),
        ([True, True, True], [0.9, 0.5, 0.2], "no variance in the item"),
        ([False, False, False], [0.9, 0.5, 0.2], "no variance in the item"),
        ([True, False, True], [0.5, 0.5, 0.5], "no variance in the totals"),
    ],
)
def test_an_undefined_correlation_names_its_reason_instead_of_returning_zero(
    flags, totals, reason
):
    result = point_biserial(flags, totals)
    assert result["r"] is None
    assert reason in result["reason"]


def test_it_matches_the_pearson_correlation_of_the_same_vectors():
    flags = [True, False, True, False, True, True]
    totals = [0.9, 0.2, 0.7, 0.4, 0.8, 0.6]
    numeric = [1.0 if f else 0.0 for f in flags]
    mean_x = sum(numeric) / len(numeric)
    mean_y = sum(totals) / len(totals)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(numeric, totals, strict=True))
    sd_x = sum((x - mean_x) ** 2 for x in numeric) ** 0.5
    sd_y = sum((y - mean_y) ** 2 for y in totals) ** 0.5
    assert point_biserial(flags, totals)["r"] == pytest.approx(cov / (sd_x * sd_y), abs=1e-4)
