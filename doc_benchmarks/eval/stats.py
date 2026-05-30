"""Small statistics helpers for evaluation rigor (no heavy deps)."""

from __future__ import annotations

import random


def bootstrap_ci(
    values, confidence: float = 0.95, n_resamples: int = 1000, seed: int = 0
) -> dict:
    """Percentile bootstrap confidence interval for the mean of ``values``.

    Returns ``{"mean", "lo", "hi", "n"}``. Deterministic for a given ``seed``,
    so it is safe to use in tests and reproducible runs.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1 (exclusive)")
    if n_resamples < 1:
        raise ValueError("n_resamples must be >= 1")

    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if n == 0:
        return {"mean": None, "lo": None, "hi": None, "n": 0}
    if n == 1:
        return {"mean": round(vals[0], 4), "lo": round(vals[0], 4), "hi": round(vals[0], 4), "n": 1}

    rng = random.Random(seed)
    means = []
    for _ in range(n_resamples):
        sample_sum = sum(vals[rng.randrange(n)] for _ in range(n))
        means.append(sample_sum / n)
    means.sort()

    alpha = (1.0 - confidence) / 2.0
    lo = means[int(alpha * n_resamples)]
    hi = means[min(n_resamples - 1, int((1.0 - alpha) * n_resamples))]
    return {
        "mean": round(sum(vals) / n, 4),
        "lo": round(lo, 4),
        "hi": round(hi, 4),
        "n": n,
    }
