# Auto-eventing from synthetic tracking

**Detected from synthetic tracking, not video.** There is no vision model in
PitchPulse. This feature shows the other half of a real eventing pipeline:
turning tracking data (positions of the ball and every player, many times a
second) into match events, and measuring how often it gets them right.

Code: `backend/src/matchmind/autoevent/`. Tests: `backend/tests/test_autoevent.py`.

## How it works

1. **Render a tracking feed** (`tracking.py`). From a simulated match we draw
   the ball and all 22 players at 25 frames a second. The ball follows the
   events (passes, carries, shots, clearances) at their recorded speeds; the
   ball holder stands with it; everyone else holds a team shape and runs to
   where the events need them next. We then add 5 cm of position noise and
   short ball dropouts (about every 20 s of play), and mark dead-ball spells
   with a ball-in-play flag.
2. **Detect events from frames only** (`detect.py`). The detector gets the
   feed and nothing else: no events, no labels. It finds who controls the ball
   in each frame (nearest player, within 1 m, moving with the ball), finds
   kicks between spells of control (the ball reaches 8 m/s), fits the kick
   speed from the first 0.24 s of flight, and classifies each kick as a pass
   (complete, incomplete, out), a shot (goal, saved, blocked, off target) or a
   clearance. The rules are written out at the top of `detect.py`.
3. **Score against ground truth** (`score.py`). The simulator's own events are
   the truth. A detection matches a true event when it is the same player, in
   the same period, within 0.5 s, one to one.

## Results

`matchmind-autoevent score data/matches/*.jsonl` (25 Hz):

| Match | True passes | Pass precision | Pass recall | Right receiver | Shots found | Shot precision | Shot recall | Shot outcome right | Kick speed error (km/h) | Shot speed error (km/h) |
|---|---|---|---|---|---|---|---|---|---|---|
| MM-DEMO-001 | 1286 | 99.7% | 99.3% | 99.3% | 33/34 | 91.7% | 97.1% | 100% | 1.1 | 1.7 |
| MM-SYN-001 | 1341 | 99.6% | 99.3% | 99.2% | 25/28 | 96.2% | 89.3% | 100% | 1.0 | 1.1 |
| MM-SYN-002 | 1316 | 99.8% | 99.5% | 99.7% | 28/28 | 96.5% | 100.0% | 96% | 1.1 | 3.1 |
| MM-SYN-003 | 1285 | 99.5% | 99.5% | 99.5% | 31/32 | 96.9% | 96.9% | 97% | 1.0 | 0.8 |
| MM-SYN-004 | 1225 | 99.5% | 99.2% | 99.6% | 36/37 | 90.0% | 97.3% | 94% | 1.0 | 1.0 |

The thresholds in `detect.py` were set while looking at these five matches,
so the tests also score a held-out match (seed 901) that was never used for
tuning; it must reach the same standard.

What it gets wrong, and why:
- An intercepted cross that was heading for goal can be called a blocked shot,
  and a long shot can look like a pass that went out. Without ball height the
  two are hard to tell apart.
- A save the keeper holds can be called blocked, because the feed has no
  player roles, so the detector does not know who the keeper is.
- Clearances are judged by the ball lying loose afterwards; a clearance that
  lands at a teammate's feet is counted as a pass.

![Detected passes and the 34th-minute shot in the demo match](images/auto-eventing-demo-34min.svg)

## Honest limits

- The feed is **synthetic**. The ball moves in straight lines at constant
  speed with no height, spin or bounce, and players move by simple rules. Real
  tracking is messier, so these numbers are an upper bound for this method,
  not a claim about real footage.
- Ball control is close to perfect by construction: the holder stands 0.35 m
  from the ball and a receiver arrives exactly where the pass ends. So the 99%
  pass and receiver figures mostly test the kick and classification rules, not
  how well the detector finds who has the ball in a crowd.
- The detector is rule-based and its thresholds are documented constants, so
  every decision can be traced. It is not a trained model.
- In the product it must always carry the label "Detected from synthetic
  tracking, not video".

## Use it

```bash
cd backend
matchmind-autoevent score data/matches/*.jsonl            # the table above
matchmind-autoevent svg data/matches/MM-DEMO-001.jsonl --at 34:02 --seconds 16 --out data/local/a.svg
matchmind-autoevent frames data/matches/MM-DEMO-001.jsonl --out data/local/tracking.jsonl.gz
```

In code, `matchmind.autoevent.evaluate(events)` returns the
`AutoEventingStatus` served at `GET /api/auto-eventing` (see
`docs/API-CONTRACT.md`): `source`, `label`, `passes_detected_pct` (pass
recall), `speed_mae_kmh` (kick speed error over matched passes and shots) and
`events_checked`. It renders and scores the whole match, which takes about
8 s for one match on a laptop, so the API should compute it once per match and
keep the result. `report(events)` returns the full breakdown.
