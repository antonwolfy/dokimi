# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Invariants of the statistics code, checked over seeded random inputs.

``test_stats.py`` and ``test_binary_stats.py`` pin hand-worked examples. These tests pin
the properties every example must satisfy -- symmetry under swapping the arms, agreement
with SciPy's reference implementations, monotonicity of the multiplicity corrections -- so
a change that keeps the worked examples but breaks the math elsewhere still fails. Inputs
come from a fixed seed: a failure reproduces exactly.
"""

from __future__ import annotations

import random

import pytest

from agent_benchmarks.eval.binary_stats import exact_binomial_two_sided, mcnemar_test
from agent_benchmarks.eval.stats import adjust_pvalues, bootstrap_ci, mean_ci

scipy_stats = pytest.importorskip("scipy.stats")

ROUND = 1e-4  # the modules round reported values to 4 decimals


def _cases(seed: int, count: int):
    return [random.Random(seed * 1000 + i) for i in range(count)]


# ---------------------------------------------------------------------------
# Exact binomial / McNemar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("trials", range(1, 41))
def test_exact_binomial_matches_scipy_and_is_symmetric(trials):
    for k in range(trials + 1):
        p = exact_binomial_two_sided(k, trials)
        assert 0.0 < p <= 1.0
        assert p == exact_binomial_two_sided(trials - k, trials)
        ref = scipy_stats.binomtest(k, trials, 0.5, alternative="two-sided").pvalue
        assert p == pytest.approx(min(1.0, ref), rel=1e-9, abs=1e-12)


@pytest.mark.parametrize("trials", range(2, 31))
def test_exact_binomial_shrinks_away_from_the_null(trials):
    ps = [exact_binomial_two_sided(k, trials) for k in range(trials // 2 + 1)]
    assert ps == sorted(ps)


def _pairs(rng: random.Random):
    n = rng.randint(2, 40)
    pt, pc = rng.random(), rng.random()
    return [rng.random() < pt for _ in range(n)], [rng.random() < pc for _ in range(n)]


@pytest.mark.parametrize("rng", _cases(1, 15))
def test_mcnemar_swapping_arms_mirrors_the_result(rng):
    t, c = _pairs(rng)
    fwd, rev = mcnemar_test(t, c), mcnemar_test(c, t)
    assert fwd["p_exact"] == rev["p_exact"]
    assert (fwd["n_gained"], fwd["n_lost"]) == (rev["n_lost"], rev["n_gained"])
    assert fwd["paired_pass_rate_delta"] == -rev["paired_pass_rate_delta"]
    assert fwd["n_gained"] + fwd["n_lost"] + fwd["n_both_passed"] + fwd["n_both_failed"] == fwd["n"]


@pytest.mark.parametrize("rng", _cases(2, 15))
def test_mcnemar_ignores_concordant_pairs(rng):
    t, c = _pairs(rng)
    extra = rng.randint(1, 30)
    padded = mcnemar_test(t + [True] * extra, c + [True] * extra)
    assert padded["p_exact"] == mcnemar_test(t, c)["p_exact"]


@pytest.mark.parametrize("rng", _cases(3, 20))
def test_mcnemar_interval_brackets_the_delta(rng):
    t, c = _pairs(rng)
    r = mcnemar_test(t, c)
    assert -1.0 <= r["ci_lo"] <= r["paired_pass_rate_delta"] + ROUND
    assert r["paired_pass_rate_delta"] - ROUND <= r["ci_hi"] <= 1.0
    assert r["significant"] is None if r["p_exact"] is None else r["significant"] == (
        r["p_exact"] < 0.05
    )


# ---------------------------------------------------------------------------
# Multiplicity correction
# ---------------------------------------------------------------------------


def _pvals(rng: random.Random):
    m = rng.randint(1, 12)
    return [rng.random() ** rng.choice([1, 2, 4]) for _ in range(m)]


@pytest.mark.parametrize("method", ["holm", "bh"])
@pytest.mark.parametrize("rng", _cases(4, 40))
def test_adjusted_pvalues_bound_and_order(rng, method):
    raw = _pvals(rng)
    adj = adjust_pvalues(raw, method=method)
    for p, a in zip(raw, adj, strict=True):
        assert p - ROUND <= a <= 1.0
    # Monotone: a smaller raw p never gets a larger adjusted p.
    by_raw = [a for _, a in sorted(zip(raw, adj, strict=True))]
    assert by_raw == sorted(by_raw)


@pytest.mark.parametrize("rng", _cases(5, 40))
def test_adjustment_is_order_equivariant_and_skips_none(rng):
    raw = _pvals(rng)
    perm = list(range(len(raw)))
    rng.shuffle(perm)
    adj = adjust_pvalues(raw)
    adj_perm = adjust_pvalues([raw[i] for i in perm])
    assert adj_perm == [adj[i] for i in perm]
    with_gaps = adjust_pvalues(raw + [None, None])
    assert with_gaps[:-2] == adj and with_gaps[-2:] == [None, None]


@pytest.mark.parametrize("rng", _cases(6, 40))
def test_holm_is_never_less_conservative_than_bh(rng):
    raw = _pvals(rng)
    for h, b in zip(adjust_pvalues(raw, "holm"), adjust_pvalues(raw, "bh"), strict=True):
        assert h >= b - ROUND


@pytest.mark.parametrize("rng", _cases(7, 20))
def test_adjustment_matches_the_textbook_definitions(rng):
    """Holm and BH against a from-the-definition reference, unrounded."""
    raw = _pvals(rng)
    m = len(raw)
    order = sorted(range(m), key=lambda i: raw[i])
    holm = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * raw[i]))
        holm[i] = running
    bh = [0.0] * m
    running = 1.0
    for rank in range(m - 1, -1, -1):
        i = order[rank]
        running = min(running, min(1.0, raw[i] * m / (rank + 1)))
        bh[i] = running
    assert adjust_pvalues(raw, "holm") == pytest.approx(holm, rel=1e-3, abs=ROUND)
    assert adjust_pvalues(raw, "bh") == pytest.approx(bh, rel=1e-3, abs=ROUND)


# ---------------------------------------------------------------------------
# Confidence intervals for the mean
# ---------------------------------------------------------------------------


def _sample(rng: random.Random):
    n = rng.randint(2, 30)
    loc, scale = rng.uniform(-50, 50), rng.uniform(0.5, 30)
    return [rng.gauss(loc, scale) for _ in range(n)]


@pytest.mark.parametrize("rng", _cases(8, 40))
def test_mean_ci_matches_scipy_t_interval(rng):
    vals = _sample(rng)
    r = mean_ci(vals)
    assert r["method"] == "student_t"
    lo, hi = scipy_stats.t.interval(
        0.95, len(vals) - 1, loc=sum(vals) / len(vals), scale=scipy_stats.sem(vals)
    )
    assert r["lo"] == pytest.approx(lo, abs=ROUND)
    assert r["hi"] == pytest.approx(hi, abs=ROUND)


@pytest.mark.parametrize("rng", _cases(9, 40))
def test_mean_ci_shifts_with_the_data_and_narrows_with_confidence(rng):
    vals = _sample(rng)
    shift = rng.uniform(-100, 100)
    base, moved = mean_ci(vals), mean_ci([v + shift for v in vals])
    for key in ("mean", "lo", "hi"):
        assert moved[key] == pytest.approx(base[key] + shift, abs=3 * ROUND)
    narrow = mean_ci(vals, confidence=0.8)
    assert base["lo"] <= narrow["lo"] <= narrow["mean"] <= narrow["hi"] <= base["hi"]


@pytest.mark.parametrize("rng", _cases(10, 30))
def test_bootstrap_ci_is_seeded_and_inside_the_data_range(rng):
    vals = _sample(rng)
    a = bootstrap_ci(vals, n_resamples=2000, seed=7)
    assert a == bootstrap_ci(vals, n_resamples=2000, seed=7)
    assert min(vals) - ROUND <= a["lo"] <= a["hi"] <= max(vals) + ROUND
