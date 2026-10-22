"""Physical numbers per player from the 25 Hz synthetic tracking feed.

Distance covered, distance in each speed band, sprints and top speed, worked
out the way a tracking provider would: smooth the positions, take speeds over
short steps, add the steps up. The feed is synthetic (rendered from the
simulated match by `matchmind.autoevent.tracking`), so every number here is
labelled "Estimated from synthetic tracking" wherever it is shown.

Method (constants below, formulas in docs/METRICS.md):
1. Average each player's positions over blocks of 0.2 s (5 frames at 25 Hz),
   then take a centred moving average over 1 s. This removes the feed's 5 cm
   position noise, which would otherwise add about 12 km of fake distance.
2. Speed of each 0.2 s step = step length / 0.2 s. A step faster than
   10.5 m/s (37.8 km/h, beyond any footballer) is a tracking glitch (in the
   synthetic feed: a player snapped onto the ball) and is left out of
   distance and speed.
3. Each step's length goes into the band its speed falls in: walk under
   7.2 km/h, jog 7.2-14.4, run 14.4-25.2, sprint 25.2 km/h and over.
4. A sprint is an unbroken spell of at least 1 s in the sprint band.
5. Top speed is the fastest step.

The whole match is worked out once (about a second) into a timeline sampled
every second, so the value "so far" at any clock is a quick lookup and a seek
needs no extra work.
"""

from __future__ import annotations

import bisect
import hashlib
import math
import threading
from array import array
from collections import OrderedDict
from dataclasses import dataclass
from itertools import accumulate

from matchmind.schema import Event

SOURCE = "synthetic_tracking"
LABEL = "Estimated from synthetic tracking"

BLOCK_S = 0.2  # positions are averaged over blocks this long
SMOOTH_S = 1.0  # then smoothed with a centred moving average this long
MAX_STEP_MPS = 10.5  # 37.8 km/h, faster than any footballer: a tracking glitch
WALK_MAX_KMH = 7.2
JOG_MAX_KMH = 14.4
RUN_MAX_KMH = 25.2  # at or above this is the sprint band
SPRINT_MIN_S = 1.0
TIMELINE_STEP_S = 1.0
BANDS = ("walk", "jog", "run", "sprint")

# Per sample, per player: distance, walk, jog, run, sprint (metres), sprints, top speed (m/s).
_FIELDS = 7


@dataclass(frozen=True, slots=True)
class PhysicalStats:
    """One player's physical numbers up to a moment in the match."""

    distance_km: float = 0.0
    walk_km: float = 0.0
    jog_km: float = 0.0
    run_km: float = 0.0
    sprint_km: float = 0.0
    sprints: int = 0
    top_speed_kmh: float = 0.0


@dataclass(frozen=True, slots=True)
class SprintEffort:
    """One sprint: an unbroken spell in the sprint band of at least 1 s."""

    player_id: str
    period: int
    start_s: float  # match clock
    end_s: float
    peak_s: float  # when the top speed of the sprint was reached
    peak_kmh: float
    distance_m: float


def _stats(row: array, i: int) -> PhysicalStats:
    b = i * _FIELDS
    return PhysicalStats(
        distance_km=round(row[b] / 1000, 2),
        walk_km=round(row[b + 1] / 1000, 2),
        jog_km=round(row[b + 2] / 1000, 2),
        run_km=round(row[b + 3] / 1000, 2),
        sprint_km=round(row[b + 4] / 1000, 2),
        sprints=int(row[b + 5]),
        top_speed_kmh=round(row[b + 6] * 3.6, 1),
    )


class PhysicalTimeline:
    """Per-player physical numbers for one match, sampled every second.

    Immutable once built; copying it (a stats engine checkpoint) shares it."""

    source = SOURCE
    label = LABEL

    def __init__(
        self,
        match_id: str,
        player_ids: tuple[str, ...],
        periods: dict[int, tuple[array, list[array]]],
        efforts: list[SprintEffort],
    ) -> None:
        self.match_id = match_id
        self.player_ids = player_ids
        self._index = {pid: n for n, pid in enumerate(player_ids)}
        self._periods = periods  # period -> (sample clocks, one row per sample)
        self.efforts = sorted(efforts, key=lambda e: (e.period, e.peak_s, e.player_id))
        self._effort_keys = [(e.period, e.peak_s) for e in self.efforts]

    def __deepcopy__(self, memo: dict) -> PhysicalTimeline:
        return self

    def __copy__(self) -> PhysicalTimeline:
        return self

    def _row(self, period: int, clock_s: float) -> array | None:
        """The cumulative row at the last sample at or before (period, clock)."""
        best: array | None = None
        for p in sorted(self._periods):
            if p > period:
                break
            times, rows = self._periods[p]
            if p < period:
                best = rows[-1] if rows else best
                continue
            i = bisect.bisect_right(times, clock_s + 1e-9) - 1
            if i >= 0:
                best = rows[i]
        return best

    def at(self, period: int, clock_s: float) -> dict[str, PhysicalStats]:
        """Every player's numbers so far at this match clock."""
        row = self._row(period, clock_s)
        if row is None:
            return {pid: PhysicalStats() for pid in self.player_ids}
        return {pid: _stats(row, n) for n, pid in enumerate(self.player_ids)}

    def player_at(self, player_id: str, period: int, clock_s: float) -> PhysicalStats:
        n = self._index.get(player_id)
        row = self._row(period, clock_s)
        if n is None or row is None:
            return PhysicalStats()
        return _stats(row, n)

    def final(self) -> dict[str, PhysicalStats]:
        last = max(self._periods) if self._periods else 1
        return self.at(last, math.inf)

    def efforts_between(
        self, after: tuple[int, float] | None, until: tuple[int, float]
    ) -> list[SprintEffort]:
        """Sprints whose peak came after `after` (exclusive) and at or before `until`."""
        lo = 0 if after is None else bisect.bisect_right(self._effort_keys, (after[0], after[1] + 1e-9))
        hi = bisect.bisect_right(self._effort_keys, (until[0], until[1] + 1e-9))
        return self.efforts[lo:hi] if hi > lo else []


# --------------------------------------------------------------------------- build


def _band(kmh: float) -> int:
    if kmh < WALK_MAX_KMH:
        return 0
    if kmh < JOG_MAX_KMH:
        return 1
    if kmh < RUN_MAX_KMH:
        return 2
    return 3


def _block_means(frames: list, block: int, n_players: int) -> tuple[list[float], list[tuple[float, ...]]]:
    """Mean clock and mean x, y of every player for each full block of frames.
    A player missing (NaN) in any frame of a block is NaN for that block."""
    times: list[float] = []
    means: list[tuple[float, ...]] = []
    inv = 1.0 / block
    for k in range(0, len(frames) - block + 1, block):
        chunk = frames[k : k + block]
        means.append(tuple(sum(col) * inv for col in zip(*(f.xy for f in chunk), strict=True)))
        times.append(sum(f.clock_s for f in chunk) * inv)
    return times, means


def _smooth(series: list[float], half: int) -> list[float]:
    """Centred moving average over 2 * half + 1 points (shorter at the ends);
    NaN wherever any point in the window is NaN."""
    n = len(series)
    vals = [0.0 if v != v else v for v in series]
    prefix = [0.0, *accumulate(vals)]
    bad = [0, *accumulate(1 if v != v else 0 for v in series)]
    out = []
    for i in range(n):
        lo, hi = (i - half if i >= half else 0), (i + half + 1 if i + half < n else n)
        out.append((prefix[hi] - prefix[lo]) / (hi - lo) if bad[hi] == bad[lo] else math.nan)
    return out


def _player_steps(xs: list[float], ys: list[float], step_s: float) -> list[float]:
    """Speed of each step in m/s; NaN for a gap (player not tracked) or a glitch."""
    out = []
    for k in range(1, len(xs)):
        v = math.hypot(xs[k] - xs[k - 1], ys[k] - ys[k - 1]) / step_s  # NaN propagates
        out.append(v if v <= MAX_STEP_MPS else math.nan)
    return out


def _close_spell(
    spell: list[int],
    speeds: list[float],
    times: list[float],
    step_s: float,
    player_id: str,
    period: int,
    min_steps: int,
    efforts: list[SprintEffort],
) -> int:
    """Record a spell of steps in the sprint band as a sprint if it lasted long
    enough. Returns 1 for a sprint, else 0."""
    if len(spell) < min_steps:
        return 0
    peak = max(spell, key=lambda k: speeds[k])
    efforts.append(
        SprintEffort(
            player_id=player_id,
            period=period,
            start_s=round(times[spell[0]], 2),
            end_s=round(times[spell[-1] + 1], 2),
            peak_s=round(times[peak + 1], 2),
            peak_kmh=round(speeds[peak] * 3.6, 1),
            distance_m=round(sum(speeds[k] for k in spell) * step_s, 1),
        )
    )
    return 1


def build_timeline(feed) -> PhysicalTimeline:
    """Work out the physical timeline from a tracking feed (`TrackingFeed`)."""
    ids = tuple(feed.player_ids)
    n_players = len(ids)
    block = max(1, round(BLOCK_S * feed.hz))
    step_s = block / feed.hz
    half = max(0, round(SMOOTH_S / step_s) // 2)
    sprint_steps = max(1, math.ceil(SPRINT_MIN_S / step_s - 1e-9))
    sample_every = max(1, round(TIMELINE_STEP_S / step_s))

    by_period: dict[int, list] = {}
    for f in feed.frames:
        by_period.setdefault(f.period, []).append(f)

    carried = [0.0] * (n_players * _FIELDS)  # totals at the end of the previous period
    periods: dict[int, tuple[array, list[array]]] = {}
    efforts: list[SprintEffort] = []
    for period in sorted(by_period):
        times, means = _block_means(by_period[period], block, n_players)
        n_steps = max(0, len(times) - 1)
        marks = list(range(sample_every - 1, n_steps, sample_every))
        if not marks or marks[-1] != n_steps - 1:
            marks.append(n_steps - 1)  # always sample the period's last step
        # One column per player and field, sampled at the marks.
        columns: list[list[float]] = []
        for n in range(n_players):
            xs = _smooth([m[2 * n] for m in means], half)
            ys = _smooth([m[2 * n + 1] for m in means], half)
            speeds = _player_steps(xs, ys, step_s)
            base = carried[n * _FIELDS : (n + 1) * _FIELDS]
            dist, bands, sprints, top = base[0], base[1:5], base[5], base[6]
            cols: list[list[float]] = [[] for _ in range(_FIELDS)]
            spell: list[int] = []
            m_i = 0

            ctx = (speeds, times, step_s, ids[n], period, sprint_steps, efforts)
            for k, v in enumerate(speeds):
                if v == v:  # not NaN
                    d = v * step_s
                    dist += d
                    band = _band(v * 3.6)
                    bands[band] += d
                    if v > top:
                        top = v
                    if band == 3:
                        spell.append(k)
                    elif spell:
                        sprints += _close_spell(spell, *ctx)
                        spell = []
                elif spell:
                    sprints += _close_spell(spell, *ctx)
                    spell = []
                if k == len(speeds) - 1 and spell:
                    sprints += _close_spell(spell, *ctx)
                    spell = []
                if m_i < len(marks) and k == marks[m_i]:
                    for f, value in enumerate((dist, *bands, sprints, top)):
                        cols[f].append(value)
                    m_i += 1
            carried[n * _FIELDS : (n + 1) * _FIELDS] = [dist, *bands, sprints, top]
            columns.extend(cols)
        sample_t = array("d", (round(times[k + 1], 2) for k in marks if k >= 0))
        rows = [array("f", (columns[c][i] for c in range(n_players * _FIELDS))) for i in range(len(sample_t))]
        periods[period] = (sample_t, rows)
    return PhysicalTimeline(feed.match_id, ids, periods, efforts)


# --------------------------------------------------------------------------- cache

_CACHE: OrderedDict[str, PhysicalTimeline] = OrderedDict()
_CACHE_SIZE = 4
_LOCK = threading.Lock()


def events_digest(events: list[Event]) -> str:
    h = hashlib.sha256()
    for e in events:
        h.update(e.to_json().encode())
    return h.hexdigest()


def timeline_for(events: list[Event]) -> PhysicalTimeline:
    """The physical timeline for a simulated match, rendered and worked out once
    per match and kept (a few matches at most; each is a few megabytes)."""
    from matchmind.autoevent.tracking import render_tracking

    key = events_digest(events)
    with _LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
            return hit
    timeline = build_timeline(render_tracking(events))
    with _LOCK:
        _CACHE[key] = timeline
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    return timeline
