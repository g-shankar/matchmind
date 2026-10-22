"""Pixel path: rendered synthetic top-down video, and positions recovered from it.

Rendered synthetic top-down video, not broadcast footage; no real-video model.

This is the honest answer to "but is it video?". It does not touch real
footage. It shows the step a vision system would have to do before the
detector can run, on frames we draw ourselves:

1. Render (`Raster.frame`). Each tracking frame becomes a small RGB image
   (320 x 208 px, 3 px per metre) from a fixed overhead camera: a striped
   pitch with white lines, one coloured disc per player (one colour per team),
   a white disc for the ball. Then pixel noise, a 3 x 3 blur and, now and
   then, a dark patch that hides whatever is under it for about a second.
2. Recover (`Vision`, `_Tracker`), from the pixels alone:
   - a background model (per-pixel median of frames spread over the clip)
     and a foreground mask (pixels far from the background);
   - colour classification of foreground pixels by the direction of their
     difference from the background (team A, team B, ball, or neither);
   - connected components per class (8-connected), intensity-weighted
     centroids, and blobs that are about k times a single player's area
     split into k with a few rounds of k-means;
   - nearest-neighbour tracking per team with a constant-velocity
     prediction, coasting through short misses.
   Player identities are seeded once from the feed at the first frame of the
   clip (an operator tagging players at kick-off) and only tracked after
   that, so identity swaps are real errors here. The ball-in-play flag is
   passed through from the feed: it is an officiating signal, not something
   this step recovers.
3. The same detector (`detect_events`) runs on the recovered positions, and
   the benchmark scores both paths on the same frames.

numpy only; no trained model of any kind.
"""

from __future__ import annotations

import math
import random
from array import array
from dataclasses import dataclass, field

import numpy as np

from .score import PIXEL_LABEL
from .tracking import Frame, TrackingFeed

__all__ = ["PIXEL_LABEL", "PixelConfig", "PixelPath", "PixelStats", "Raster", "Vision"]

PITCH_L, PITCH_W = 105.0, 68.0
TEAM_RGB = ((214, 48, 49), (46, 92, 224))  # team attacking right, team attacking left
BALL_RGB = (255, 255, 255)
LINE_RGB = (232, 236, 232)
GRASS_RGB = ((36, 122, 60), (31, 110, 54))
OCCLUDER_RGB = (16, 34, 22)

FG_THRESHOLD = 40.0  # max channel difference from the background, 0-255
CLASS_MIN_COS = 0.82  # how close a pixel's colour change must be to a class
GATE_M = 2.0
MAX_GATE_M = 6.0
COAST_OUTPUT_S = 0.4  # report a predicted position for this long after a miss
BALL_GATE_M = 3.5
REACQUIRE_M = 8.0
NOISE_BANK = 8
REACQUIRE_PENALTY = 100.0  # sorts the second pass after every gated pair


@dataclass(frozen=True, slots=True)
class PixelConfig:
    width: int = 320
    height: int = 208
    px_per_m: float = 3.0
    player_radius_m: float = 0.9
    ball_radius_m: float = 0.5
    noise_sd: float = 6.0
    blur: bool = True
    occluder_rate_per_s: float = 0.15
    occluder_px: tuple[int, int] = (10, 22)
    occluder_s: tuple[float, float] = (0.5, 1.5)
    background_samples: int = 15
    seed: int = 7


@dataclass(slots=True)
class PixelStats:
    frames: int = 0
    player_errors_m: list[float] = field(default_factory=list)
    ball_errors_m: list[float] = field(default_factory=list)
    ball_frames: int = 0  # frames where the feed tracked the ball
    ball_found: int = 0  # ... and the pixels gave one back

    @staticmethod
    def _median(xs: list[float]) -> float | None:
        return round(float(np.median(xs)), 3) if xs else None

    def summary(self) -> dict:
        pe = self.player_errors_m
        return {
            "frames": self.frames,
            "player_error_m": self._median(pe),
            "player_error_p95_m": round(float(np.percentile(pe, 95)), 3) if pe else None,
            "ball_error_m": self._median(self.ball_errors_m),
            "ball_found_pct": round(100 * self.ball_found / self.ball_frames, 1) if self.ball_frames else 0.0,
        }


class Raster:
    """Draws tracking frames as small top-down RGB images."""

    def __init__(self, cfg: PixelConfig) -> None:
        self.cfg = cfg
        self.s = cfg.px_per_m
        self.ox = (cfg.width - PITCH_L * self.s) / 2
        self.oy = (cfg.height - PITCH_W * self.s) / 2
        self.background = self._pitch()
        self._bank: np.ndarray | None = None

    def to_px(self, x: float, y: float) -> tuple[float, float]:
        return (self.ox + x * self.s, self.oy + (PITCH_W - y) * self.s)

    def to_m(self, u: float, v: float) -> tuple[float, float]:
        return ((u - self.ox) / self.s, PITCH_W - (v - self.oy) / self.s)

    def _pitch(self) -> np.ndarray:
        cfg = self.cfg
        h, w = cfg.height, cfg.width
        u = np.arange(w) + 0.5
        v = np.arange(h) + 0.5
        uu, vv = np.meshgrid(u, v)
        xm, ym = (uu - self.ox) / self.s, PITCH_W - (vv - self.oy) / self.s
        img = np.empty((h, w, 3), np.float32)
        stripe = (np.floor(xm / 5.25).astype(int) % 2).astype(bool)
        img[:] = GRASS_RGB[0]
        img[stripe] = GRASS_RGB[1]
        half = 0.6 / self.s  # line half-width in metres (about 0.6 px)
        lines = np.zeros((h, w), bool)

        def seg(x0, y0, x1, y1):
            if x0 == x1:
                m = (np.abs(xm - x0) <= half) & (ym >= min(y0, y1) - half) & (ym <= max(y0, y1) + half)
            else:
                m = (np.abs(ym - y0) <= half) & (xm >= min(x0, x1) - half) & (xm <= max(x0, x1) + half)
            lines[m] = True

        for a, b, c, d in (
            (0, 0, 105, 0),
            (0, 68, 105, 68),
            (0, 0, 0, 68),
            (105, 0, 105, 68),
            (52.5, 0, 52.5, 68),
        ):
            seg(a, b, c, d)
        for gx, sgn in ((0.0, 1), (105.0, -1)):
            for depth, half_w in ((16.5, 20.16), (5.5, 9.16)):
                xd = gx + sgn * depth
                seg(gx, 34 - half_w, xd, 34 - half_w)
                seg(gx, 34 + half_w, xd, 34 + half_w)
                seg(xd, 34 - half_w, xd, 34 + half_w)
        r = np.hypot(xm - 52.5, ym - 34.0)
        lines |= np.abs(r - 9.15) <= half
        img[lines] = LINE_RGB
        return img

    def _disc(self, img: np.ndarray, x: float, y: float, r_m: float, rgb) -> None:
        u, v = self.to_px(x, y)
        r = r_m * self.s
        h, w = img.shape[:2]
        j0, j1 = max(0, int(u - r - 1)), min(w, int(u + r + 2))
        i0, i1 = max(0, int(v - r - 1)), min(h, int(v + r + 2))
        if j0 >= j1 or i0 >= i1:
            return
        jj = np.arange(j0, j1) + 0.5 - u
        ii = np.arange(i0, i1) + 0.5 - v
        d = np.hypot(jj[None, :], ii[:, None])
        a = np.clip(r + 0.5 - d, 0.0, 1.0)[..., None]  # anti-aliased coverage
        patch = img[i0:i1, j0:j1]
        patch *= 1 - a
        patch += a * np.asarray(rgb, np.float32)

    def frame(
        self,
        f: Frame,
        colour_of: list[int],
        rng: np.random.Generator,
        occluders: list[tuple[int, int, int, int]] = (),
    ) -> np.ndarray:
        """One RGB uint8 image of frame f. colour_of[n] is 0 or 1 for player n."""
        cfg = self.cfg
        img = self.background.copy()
        for n, c in enumerate(colour_of):
            p = f.player(n)
            if p is not None:
                self._disc(img, p[0], p[1], cfg.player_radius_m, TEAM_RGB[c])
        if f.ball is not None:
            self._disc(img, f.ball[0], f.ball[1], cfg.ball_radius_m, BALL_RGB)
        for j0, i0, w, h in occluders:
            img[i0 : i0 + h, j0 : j0 + w] = OCCLUDER_RGB
        if cfg.blur:  # 3 x 3 box blur, as two 3-tap passes
            p = np.pad(img, ((1, 1), (0, 0), (0, 0)), mode="edge")
            img = (p[:-2] + p[1:-1] + p[2:]) / 3.0
            p = np.pad(img, ((0, 0), (1, 1), (0, 0)), mode="edge")
            img = (p[:, :-2] + p[:, 1:-1] + p[:, 2:]) / 3.0
        if cfg.noise_sd > 0:
            img += self._noise(rng)
        return np.clip(img, 0, 255).astype(np.uint8)

    def _noise(self, rng: np.random.Generator) -> np.ndarray:
        """Sensor noise: a random roll of a fixed bank of Gaussian frames (cheap, reproducible)."""
        if self._bank is None:
            bank_rng = np.random.default_rng(self.cfg.seed + 99)
            shape = (NOISE_BANK, self.cfg.height, self.cfg.width, 3)
            self._bank = bank_rng.normal(0.0, self.cfg.noise_sd, shape).astype(np.float32)
        i = int(rng.integers(NOISE_BANK))
        dy, dx = int(rng.integers(self.cfg.height)), int(rng.integers(self.cfg.width))
        return np.roll(self._bank[i], (dy, dx), axis=(0, 1))


def _components(ys: np.ndarray, xs: np.ndarray, width: int) -> list[np.ndarray]:
    """8-connected components of a sparse pixel set; returns index arrays into ys/xs.

    Vectorised: neighbour pairs are found by binary search on the sorted linear
    pixel index, then labels are propagated to the minimum with pointer jumping.
    """
    n = len(ys)
    if n == 0:
        return []
    lin = ys.astype(np.int64) * width + xs
    order = np.argsort(lin, kind="stable")
    lin_s, xs_s = lin[order], xs[order]
    ea, eb = [], []
    for off, ok in (
        (1, xs_s < width - 1),
        (width - 1, xs_s > 0),
        (width, None),
        (width + 1, xs_s < width - 1),
    ):
        tgt = lin_s + off
        pos = np.minimum(np.searchsorted(lin_s, tgt), n - 1)
        hit = lin_s[pos] == tgt
        if ok is not None:
            hit &= ok
        ea.append(np.nonzero(hit)[0])
        eb.append(pos[hit])
    a, b = np.concatenate(ea), np.concatenate(eb)
    lab = np.arange(n)
    while len(a):
        m = np.minimum(lab[a], lab[b])
        new = lab.copy()
        np.minimum.at(new, a, m)
        np.minimum.at(new, b, m)
        new = new[new]
        if np.array_equal(new, lab):
            break
        lab = new
    _, inv, counts = np.unique(lab, return_inverse=True, return_counts=True)
    grouped = order[np.argsort(inv, kind="stable")]
    return np.split(grouped, np.cumsum(counts)[:-1])


def _kmeans(pts: np.ndarray, wts: np.ndarray, init: np.ndarray, rounds: int = 6) -> np.ndarray:
    centres = init.astype(np.float64).copy()
    for _ in range(rounds):
        d = ((pts[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
        lab = d.argmin(axis=1)
        for c in range(len(centres)):
            m = lab == c
            if m.any():
                centres[c] = (pts[m] * wts[m, None]).sum(axis=0) / wts[m].sum()
    return centres


class Vision:
    """Finds team blobs and the ball in one image, using pixels only."""

    def __init__(self, raster: Raster, background: np.ndarray) -> None:
        self.raster = raster
        self.bg = background.astype(np.float32)
        grass = np.asarray(GRASS_RGB, np.float32).mean(axis=0)
        protos = np.asarray([TEAM_RGB[0], TEAM_RGB[1], BALL_RGB], np.float32) - grass
        self.protos = protos / np.linalg.norm(protos, axis=1, keepdims=True)
        r = raster.cfg.player_radius_m * raster.s
        self.player_area = math.pi * r * r  # updated from the data once blobs are seen
        self._areas: list[float] = []

    def detect(self, img: np.ndarray) -> tuple[list[list[tuple[float, float, float]]], list]:
        """Per team: (u, v, area) blobs; and ball candidates (u, v, area)."""
        diff = img.astype(np.float32) - self.bg
        mag = np.abs(diff).max(axis=2)
        ys, xs = np.nonzero(mag > FG_THRESHOLD)
        teams: list[list[tuple[float, float, float]]] = [[], []]
        balls: list[tuple[float, float, float]] = []
        if len(ys) == 0:
            return teams, balls
        vec = diff[ys, xs]
        unit = vec / (np.linalg.norm(vec, axis=1, keepdims=True) + 1e-6)
        cos = unit @ self.protos.T
        cls = cos.argmax(axis=1)
        ok = cos.max(axis=1) >= CLASS_MIN_COS
        w_all = mag[ys, xs]
        for c in range(3):
            sel = ok & (cls == c)
            cy, cx, cw = ys[sel], xs[sel], w_all[sel]
            for comp in _components(cy, cx, img.shape[1]):
                wts = cw[comp]
                u = float((cx[comp] + 0.5) @ wts / wts.sum())
                v = float((cy[comp] + 0.5) @ wts / wts.sum())
                area = float(len(comp))
                if c == 2:
                    balls.append((u, v, area))
                else:
                    teams[c].append((u, v, area, cx[comp] + 0.5, cy[comp] + 0.5, wts))
        return teams, balls

    def single_area(self) -> float:
        return float(np.median(self._areas)) if len(self._areas) >= 20 else self.player_area

    def learn(self, area: float) -> None:
        if len(self._areas) < 400:
            self._areas.append(area)


class _Tracker:
    """Nearest-neighbour tracking of one team's players with constant-velocity prediction."""

    def __init__(self, members: list[int], start: list[tuple[float, float] | None], dt: float) -> None:
        self.members = [n for n in members if start[n] is not None]
        self.pos = {n: start[n] for n in self.members}
        self.vel = {n: (0.0, 0.0) for n in self.members}
        self.missed = {n: 0 for n in self.members}
        self.dt = dt

    def predict(self, n: int) -> tuple[float, float]:
        (x, y), (vx, vy) = self.pos[n], self.vel[n]
        k = min(self.missed[n] + 1, 10)
        return (x + vx * self.dt * k, y + vy * self.dt * k)

    def step(self, dets: list[tuple[float, float]]) -> dict[int, tuple[float, float] | None]:
        preds = {n: self.predict(n) for n in self.members}
        pairs = []
        for n in self.members:
            gate = min(MAX_GATE_M, GATE_M + 4.0 * self.missed[n] * self.dt)
            px, py = preds[n]
            for k, (x, y) in enumerate(dets):
                d = math.hypot(x - px, y - py)
                if d <= gate:
                    pairs.append((d, n, k))
        pairs.sort()
        # Second pass: a blob nobody claimed goes to the nearest unclaimed player of the team
        # within REACQUIRE_M (players who jumped, or come back from behind an occluder).
        late = [
            (math.hypot(x - preds[n][0], y - preds[n][1]), n, k)
            for n in self.members
            for k, (x, y) in enumerate(dets)
        ]
        pairs += [(REACQUIRE_PENALTY + d, n, k) for d, n, k in sorted(late) if d <= REACQUIRE_M]
        used_n, used_k = set(), set()
        out: dict[int, tuple[float, float] | None] = {}
        for _, n, k in pairs:
            if n in used_n or k in used_k:
                continue
            used_n.add(n)
            used_k.add(k)
            x, y = dets[k]
            ox, oy = self.pos[n]
            steps = self.missed[n] + 1
            nv = ((x - ox) / (self.dt * steps), (y - oy) / (self.dt * steps))
            self.vel[n] = (0.5 * self.vel[n][0] + 0.5 * nv[0], 0.5 * self.vel[n][1] + 0.5 * nv[1])
            self.pos[n] = (x, y)
            self.missed[n] = 0
            out[n] = (x, y)
        for n in self.members:
            if n in used_n:
                continue
            self.missed[n] += 1
            out[n] = preds[n] if self.missed[n] * self.dt <= COAST_OUTPUT_S else None
        return out


def _occluders(cfg: PixelConfig, n_frames: int, hz: float, rng: random.Random) -> list[list]:
    per_frame: list[list] = [[] for _ in range(n_frames)]
    k = 0
    while k < n_frames:
        if rng.random() < cfg.occluder_rate_per_s / hz:
            dur = max(1, round(rng.uniform(*cfg.occluder_s) * hz))
            w = rng.randint(*cfg.occluder_px)
            h = rng.randint(*cfg.occluder_px)
            j0 = rng.randint(0, cfg.width - w)
            i0 = rng.randint(0, cfg.height - h)
            for m in range(k, min(n_frames, k + dur)):
                per_frame[m].append((j0, i0, w, h))
        k += 1
    return per_frame


def _split(blob, k: int, guesses: list[tuple[float, float]]) -> list[tuple[float, float]]:
    u, v, _, xs, ys, wts = blob
    pts = np.stack([xs, ys], axis=1)
    if len(guesses) >= k:
        init = np.asarray(guesses[:k])
    else:
        order = np.argsort(pts[:, 0] + 0.37 * pts[:, 1])
        init = pts[order[np.linspace(0, len(order) - 1, k).astype(int)]]
    return [(float(a), float(b)) for a, b in _kmeans(pts, wts.astype(np.float64), init)]


class PixelPath:
    """Renders a slice of a feed to images and recovers a feed from the images."""

    def __init__(self, feed: TrackingFeed, cfg: PixelConfig | None = None) -> None:
        self.feed = feed
        self.cfg = cfg or PixelConfig()
        self.raster = Raster(self.cfg)
        right = [feed.attacks_right[t] for t in feed.player_teams]
        self.colour_of = [0 if r else 1 for r in right]

    def images(self, lo: int, hi: int):
        """Yield (frame index, image) for frames lo..hi-1, deterministically."""
        cfg = self.cfg
        rng = np.random.default_rng(cfg.seed)
        occ = _occluders(cfg, hi - lo, self.feed.hz, random.Random(cfg.seed))
        for k in range(lo, hi):
            yield k, self.raster.frame(self.feed.frames[k], self.colour_of, rng, occ[k - lo])

    def background(self, lo: int, hi: int) -> np.ndarray:
        cfg = self.cfg
        n = max(3, cfg.background_samples)
        picks = sorted({lo + round(i * (hi - lo - 1) / (n - 1)) for i in range(n)})
        rng = np.random.default_rng(cfg.seed + 1)
        occ = _occluders(cfg, hi - lo, self.feed.hz, random.Random(cfg.seed))
        stack = np.stack(
            [self.raster.frame(self.feed.frames[k], self.colour_of, rng, occ[k - lo]) for k in picks]
        )
        return np.median(stack, axis=0)

    def recover(self, lo: int, hi: int, *, on_image=None) -> tuple[TrackingFeed, PixelStats]:
        """Run the vision step on frames lo..hi-1 and return the recovered feed.

        on_image(k, image, recovered_frame) is called per frame if given (for the clip).
        """
        feed, raster = self.feed, self.raster
        if not 0 <= lo < hi <= len(feed.frames):
            raise ValueError("frame range out of bounds")
        vision = Vision(raster, self.background(lo, hi))
        dt = 1.0 / feed.hz
        n_players = len(feed.player_ids)
        teams_idx = self.colour_of
        out = TrackingFeed(
            match_id=feed.match_id,
            hz=feed.hz,
            player_ids=feed.player_ids,
            player_teams=feed.player_teams,
            attacks_right=dict(feed.attacks_right),
        )
        stats = PixelStats()
        trackers: list[_Tracker] = []
        period = None
        ball_last: tuple[float, float] | None = None
        ball_vel = (0.0, 0.0)
        ball_missed = 0
        for k, img in self.images(lo, hi):
            src = feed.frames[k]
            if src.period != period:
                # Identities are tagged once per period from the feed, then only tracked.
                period = src.period
                start = [src.player(n) for n in range(n_players)]
                trackers = [
                    _Tracker([n for n in range(n_players) if teams_idx[n] == t], start, dt) for t in (0, 1)
                ]
                ball_last, ball_vel, ball_missed = src.ball, (0.0, 0.0), 0
            team_blobs, ball_blobs = vision.detect(img)
            xy = array("f", [math.nan]) * (2 * n_players)
            for t, tracker in enumerate(trackers):
                dets = self._team_points(vision, tracker, team_blobs[t])
                for n, p in tracker.step(dets).items():
                    if p is not None:
                        xy[2 * n] = min(max(p[0], 0.0), PITCH_L)
                        xy[2 * n + 1] = min(max(p[1], 0.0), PITCH_W)
            ball, ball_last, ball_vel, ball_missed = self._ball(
                ball_blobs, ball_last, ball_vel, ball_missed, dt
            )
            rec = Frame(src.period, src.clock_s, src.alive, ball, xy)
            out.frames.append(rec)
            self._score(stats, src, rec, n_players)
            if on_image is not None:
                on_image(k, img, rec)
        return out, stats

    def _team_points(self, vision: Vision, tracker: _Tracker, blobs) -> list[tuple[float, float]]:
        raster = self.raster
        single = vision.single_area()
        preds_px = {n: raster.to_px(*tracker.predict(n)) for n in tracker.members}
        pts: list[tuple[float, float]] = []
        for blob in blobs:
            u, v, area = blob[0], blob[1], blob[2]
            k = max(1, min(4, round(area / single))) if single > 0 else 1
            if k == 1:
                if area >= 0.4 * single:
                    vision.learn(area)
                pts.append(raster.to_m(u, v))
                continue
            near = sorted(preds_px.values(), key=lambda p: math.hypot(p[0] - u, p[1] - v))
            for cu, cv in _split(blob, k, near):
                pts.append(raster.to_m(cu, cv))
        return pts

    def _ball(self, blobs, last, vel, missed, dt):
        raster = self.raster
        cands = [(raster.to_m(u, v), a) for u, v, a in blobs if a <= 40]
        if not cands:
            return None, last, vel, missed + 1
        if last is not None:
            k = min(missed + 1, 10)
            pred = (last[0] + vel[0] * dt * k, last[1] + vel[1] * dt * k)
            gate = BALL_GATE_M + 2.0 * missed
            best = min(cands, key=lambda c: math.hypot(c[0][0] - pred[0], c[0][1] - pred[1]))
            if math.hypot(best[0][0] - pred[0], best[0][1] - pred[1]) > gate and missed < 25:
                return None, last, vel, missed + 1
        else:
            best = max(cands, key=lambda c: c[1])
        p = best[0]
        if last is not None:
            steps = missed + 1
            nv = ((p[0] - last[0]) / (dt * steps), (p[1] - last[1]) / (dt * steps))
            vel = (0.5 * vel[0] + 0.5 * nv[0], 0.5 * vel[1] + 0.5 * nv[1])
        p = (min(max(p[0], 0.0), PITCH_L), min(max(p[1], 0.0), PITCH_W))
        return p, p, vel, 0

    @staticmethod
    def _score(stats: PixelStats, src: Frame, rec: Frame, n_players: int) -> None:
        stats.frames += 1
        if stats.frames % 5 == 0:  # every 5th frame keeps the error lists small
            for n in range(n_players):
                a, b = src.player(n), rec.player(n)
                if a is not None and b is not None:
                    stats.player_errors_m.append(math.hypot(a[0] - b[0], a[1] - b[1]))
        if src.ball is not None:
            stats.ball_frames += 1
            if rec.ball is not None:
                stats.ball_found += 1
                stats.ball_errors_m.append(math.hypot(src.ball[0] - rec.ball[0], src.ball[1] - rec.ball[1]))
