"""Make a tracking feed worse, on purpose, for the robustness sweep.

The base feed already has 5 cm of position noise and short ball dropouts.
`degrade` adds more on top, from the frames alone:
- extra Gaussian noise so the total position noise is `noise_m` (per axis);
- extra ball dropouts at `ball_dropout_per_s` (each 0.12 to 0.4 s);
- player occlusions at `player_occlusion_per_s` per player (each 0.2 to 1.0 s),
  during which that player's position is missing.
Same feed, same settings and same seed give the same result.
"""

from __future__ import annotations

import math
from array import array
from dataclasses import dataclass

import numpy as np

from .tracking import BALL_NOISE_M, PLAYER_NOISE_M, Frame, TrackingFeed

BALL_DROPOUT_S = (0.12, 0.4)
PLAYER_OCCLUSION_S = (0.2, 1.0)


@dataclass(frozen=True, slots=True)
class Degradation:
    name: str
    noise_m: float = PLAYER_NOISE_M
    ball_dropout_per_s: float = 0.0
    player_occlusion_per_s: float = 0.0


def _spells(rng: np.random.Generator, n: int, rate: float, dur: tuple[float, float], hz: float) -> np.ndarray:
    """Boolean mask of n frames covered by spells that start at `rate` per second."""
    mask = np.zeros(n, bool)
    if rate <= 0 or n == 0:
        return mask
    starts = np.nonzero(rng.random(n) < rate / hz)[0]
    lengths = np.maximum(1, np.round(rng.uniform(dur[0], dur[1], len(starts)) * hz).astype(int))
    for s, length in zip(starts, lengths, strict=True):
        mask[s : s + length] = True
    return mask


def degrade(feed: TrackingFeed, d: Degradation, *, seed: int = 11) -> TrackingFeed:
    rng = np.random.default_rng(seed)
    n = len(feed.frames)
    n_players = len(feed.player_ids)
    xy = np.array([f.xy for f in feed.frames], dtype=np.float64).reshape(n, 2 * n_players)
    extra_p = math.sqrt(max(0.0, d.noise_m**2 - PLAYER_NOISE_M**2))
    extra_b = math.sqrt(max(0.0, d.noise_m**2 - BALL_NOISE_M**2))
    if extra_p > 0:
        xy += rng.normal(0.0, extra_p, xy.shape)
    for p in range(n_players):
        hidden = _spells(rng, n, d.player_occlusion_per_s, PLAYER_OCCLUSION_S, feed.hz)
        xy[hidden, 2 * p] = np.nan
        xy[hidden, 2 * p + 1] = np.nan
    xy[:, 0::2] = np.clip(xy[:, 0::2], 0.0, 105.0)
    xy[:, 1::2] = np.clip(xy[:, 1::2], 0.0, 68.0)
    ball_noise = rng.normal(0.0, extra_b, (n, 2)) if extra_b > 0 else np.zeros((n, 2))
    dropped = _spells(rng, n, d.ball_dropout_per_s, BALL_DROPOUT_S, feed.hz)
    out = TrackingFeed(
        match_id=feed.match_id,
        hz=feed.hz,
        player_ids=feed.player_ids,
        player_teams=feed.player_teams,
        attacks_right=dict(feed.attacks_right),
        source=feed.source,
    )
    rows = xy.astype(np.float32)
    for k, f in enumerate(feed.frames):
        ball = None
        if f.ball is not None and not dropped[k]:
            ball = (
                min(max(f.ball[0] + float(ball_noise[k, 0]), 0.0), 105.0),
                min(max(f.ball[1] + float(ball_noise[k, 1]), 0.0), 68.0),
            )
        out.frames.append(Frame(f.period, f.clock_s, f.alive, ball, array("f", rows[k].tobytes())))
    return out
