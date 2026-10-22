"""Small, dependency-free statistics for the benchmark.

- Wilson score interval for a proportion (precision, recall). It behaves well
  for small counts and for proportions near 0 or 1, where the normal
  approximation gives intervals outside [0, 1].
- Percentile bootstrap for the mean of a list (kick-speed error), with a fixed
  seed so the same inputs always give the same interval.
"""

from __future__ import annotations

import math
import random

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """95% Wilson interval for k successes out of n; None when n is 0."""
    if n <= 0:
        return None
    if not 0 <= k <= n:
        raise ValueError("k must be between 0 and n")
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def f1(precision: float, recall: float) -> float:
    return round(2 * precision * recall / (precision + recall), 4) if precision + recall > 0 else 0.0


def bootstrap_mean_ci(
    values: list[float], *, resamples: int = 1000, seed: int = 20261027, level: float = 0.95
) -> tuple[float, float] | None:
    """Percentile bootstrap interval for the mean; None for an empty list."""
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(resamples))
    lo_i = int(math.floor((1 - level) / 2 * resamples))
    hi_i = min(resamples - 1, int(math.ceil((1 + level) / 2 * resamples)) - 1)
    return (round(means[lo_i], 3), round(means[hi_i], 3))
