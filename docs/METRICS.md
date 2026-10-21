# PitchPulse metrics

Every number PitchPulse shows comes from the stats engine
(`backend/src/matchmind/stats/`). It is deterministic: no randomness, no
model, no wall clock. The same events in give the same numbers out, and the
fact-checker only lets generated text use numbers that came from here.

Conventions:

- Pitch is 105 x 68 metres. "Attacking frame" means the acting team attacks
  towards x = 105 (the away team's coordinates are rotated 180 degrees).
- "Final third" is the last 35 m (attacking-frame x >= 70). "The box" is the
  16.5 m x 40.32 m penalty area.
- Every value marked **estimate** below is worked out from partial data and is
  labelled as such wherever it appears.

## Per-event metrics (`metrics.py`, `EventMetrics`)

| Metric | Events | How it is worked out |
|---|---|---|
| Pass distance | passes | Straight line from where the pass was played to where it ended (metres). |
| Forward metres | passes, carries | Change in attacking-frame x. Negative means backwards. |
| Progressive | passes, carries | Moves the ball at least 10 m forward **and** ends at least 25% closer to the goal centre. |
| Pass difficulty (0-100) | passes | See below. |
| Expected threat added (xT delta) | passes, carries | See below. |
| Ball speed | passes, shots, clearances | Recorded ball speed in m/s x 3.6, in km/h. |
| Player speed, sprint | carries, dribbles, runs | Recorded player speed in km/h. A sprint is faster than 8 m/s (28.8 km/h). |
| Rocket shot | shots | Ball speed of 100 km/h or more. |
| Chance quality (xG) | shots | See below. |
| Distance to goal | shots | From the shot spot to the centre of the goal line. |
| Pitch zone | any event with a location | Penalty Box, Attacking Third (x >= 70), Middle Third (x >= 35) or Defensive Third. |

### Pass difficulty

A weighted average of capped factors, each between 0 and 1, scaled to 0-100:

| Weight | Factor | Full marks at |
|---|---|---|
| 25% | Length | 40 m or more |
| 25% | Pressure on the passer | 2 or more opponents within 3.5 m |
| 15% | Forward progress | 30 m or more forward |
| 10% | Ends in the final third | yes |
| 10% | Cross or through ball | yes |
| 10% | Opponents in the passing lane | 3 or more within 2 m of the line of the pass |
| 5% | Angle across the pitch | a 30 m+ pass played square: abs(sin(angle to goal)) x min(length / 30, 1) |

Opponent positions are only known for a pass when it is a through ball played
straight after a tracked run in behind (the run carries 3 s of positions). For
every other pass the lane term is unknown, so it is left out and the remaining
weights are rescaled; the score stays on the same 0-100 scale. The length,
pressure, lane and lofted-ball terms follow the pass difficulty rating from
the team's first build; forward progress and the final-third term are ours.

### Expected threat (xT)

A fixed 12 x 8 grid (12 zones along the pitch, 8 across) gives the chance that
having the ball in that zone leads to a goal: about 0.001 near your own goal,
0.07 centrally at the start of the final third, 0.30 around the penalty spot
and 0.61 in the central zone closest to goal.

- Completed pass or carry: xT at the end minus xT at the start (attacking frame).
- Failed pass: minus the xT at the start (the threat the team had and lost).

So a central pass from 70 m to the penalty spot adds about +0.22, a pass back
to the defence is negative, and a misplaced pass is always negative. The grid
values are a smoothed, symmetric threat surface from the first build; they are
not fitted to the synthetic matches.

### Chance quality (xG)

A logistic curve on distance to goal and the angle the goal mouth makes at the
shot spot, fitted so that a penalty-spot shot is about 0.25, a central shot from
20 m about 0.07 and a central shot from 6 m about 0.56. Then:

- each outfield defender inside the triangle from the shooter to both posts
  (within 12 m) multiplies it by 0.75;
- a keeper standing on the shot line (within 1.5 m of it and within 6 m of
  goal) multiplies it by 0.85;
- a header multiplies it by 0.6.

The result is clamped between 0.01 and 0.95.

## "Should he have passed?" (`better_option.py`)

### The better option (shots)

Read from the shot's freeze frame (everyone in the final 35 m at the moment of
the shot).

1. Shot value = chance quality from the shooter's spot.
2. For each outfield teammate who is onside (no further forward than the
   second-last opponent, keeper included, or the ball) and **unmarked** (no
   opponent within 7 m): value = chance the pass arrives x chance quality from
   the teammate's spot.
3. The chance the pass arrives starts at 0.92, drops 0.006 per metre beyond
   10 m, and drops by up to 0.45 when an opponent stands close to the lane
   (a Gaussian on their distance to the line, width 1.8 m).
4. Flag the shot when the best teammate value is at least 0.10 higher than
   the shot value **and** at least 1.8 times it. "Times better" is the ratio.

Goals are never flagged: the decision paid off.

Why "unmarked" is 7 m and not 3 m: the synthetic team shapes often leave the
striker loose near the penalty spot, so with a 3 m rule up to 8 shots per
unscripted match were flagged. 7 m is the same "unmarked" distance the
simulator's own tests use; with it the demo flags exactly its two scripted
moments (34' and 78', both 4.0x better) and the four unscripted matches flag
0, 1, 2 and 0 shots.

### The unfound run (runs in behind)

Read from the run's tracking window (runner, ball carrier, back line and
keeper every 0.5 s for 3 s).

1. In each frame the offside line is the second-last defender, keeper included.
2. The pass is "on" at the first frame where the runner is onside (within
   0.3 m of the line) and 1.0 s later is at least 1.5 m beyond the line, with
   a clear lane from the carrier to where the runner will be (chance the pass
   arrives at least 0.6).
3. Projected chance = chance quality from the runner's last tracked spot,
   counting outfield defenders between him and goal. No defenders there means
   one-on-one with the keeper.
4. Only runs where the ball never came, with a projected chance of at least
   0.2, are reported.

## Match state (`state.py`, `MatchStateSnapshot`)

### Rolling window

Team numbers use the last 5 minutes of match clock. First-half stoppage time
is kept on the timeline, so the window flows across half-time instead of
jumping backwards. Rates are per minute of the window (at least one minute,
so the first events of a match do not produce huge rates).

| Number | How it is worked out |
|---|---|
| Possession % | Team's completed passes / all completed passes in the window. 50/50 when there are none. |
| Field tilt % | Team's completed passes ending in the final third / both teams' final-third passes. |
| Box entries | Completed passes, carries and successful dribbles that end in the box after starting outside it. |
| Shots, xG | Shots and chance quality in the window. |
| Pressure index (0-100) | 100 x (1 - e^(-L / 30)), with L = final-third passes + 2 x box entries + 4 x shots + 20 x xG. It rises quickly with the first attacks and levels off near 100. |

### Momentum (-100 to +100, + = home on top)

A moving average of (home pressure index - away pressure index), weighted by
match time: after each event it moves towards the current difference by
1 - e^(-seconds since last event / 120). A busy minute with many events does
not count double, and a two-minute spell moves it most of the way.

### Control vs chaos (-1 chaos to +1 control) and tempo

Ported from the team's first build and rescaled to our data:

- turnover load = turnovers per minute / 4 (capped at 1). A turnover is an
  interception, a won tackle, or the ball changing team between events;
- directness = share of window events that are passes, clearances or shots
  struck at 65 km/h or more;
- continuity = average completed passes per possession / 6 (capped at 1).

control/chaos = clamp(0.4 - 1.8 x (0.5 x turnover load + 0.5 x directness -
0.6 x continuity), -1, +1).

Tempo label: below -0.4 "Furious Chaos", below 0.1 "High-Tempo Transition",
below 0.5 "Methodical Control", otherwise "Total Positional Control".

The snapshot also gives events per minute, turnovers per minute and average
passes per possession for the window, plus match totals for the score, xG and
shots.

## Player stats (`PlayerStats`)

| Stat | How it is counted |
|---|---|
| Touches | Passes, carries, dribbles, shots, interceptions, tackles, clearances and recoveries by the player. |
| Passes, completed, accuracy | Every pass attempt; accuracy = completed / attempted x 100. |
| Key passes, xA | A completed pass whose receiver shoots in the same possession before anyone else receives a pass. xA adds that shot's xG. |
| Assists | Key passes whose shot was a goal. |
| Goals, shots, xG | From the player's shots. |
| Tackles won, interceptions | Count of those events. |
| Top speed | Highest recorded speed on the player's carries, dribbles and runs. |
| Sprints | Actions faster than 8 m/s. |
| Carry distance | Start-to-end distance of carries and successful dribbles. |
| Distance covered (**estimate**) | See below. |

### Distance covered is an estimate

We have no full tracking data. A player's position is only known at certain
moments: when they start or finish an action, when they receive a completed
pass, when they appear in a shot's freeze frame, and in the frames of a
tracked run. Distance covered adds up the straight lines between each
player's successive known positions.

This is a **lower bound**: movement between sightings is taken as a straight
line, and players far from the ball are rarely seen. Over 90 minutes it gives
roughly 0.2 to 3.8 km per player in the synthetic matches, against about
10 km for a real outfield player, so it must always be shown as "estimated"
and not compared with real tracking figures.

## Broadcast thresholds

Constants in `metrics.py`, used by the Spotter for on-screen tags:

| Constant | Value | Meaning |
|---|---|---|
| `SPEED_BURST_KMH` | 30.0 | Player speed worth a pitch tag |
| `ROCKET_SHOT_KMH` | 100.0 | Shot speed worth a pitch tag (also sets "rocket shot" on the event) |
| `DISTANCE_MILESTONES_KM` | 5, 8, 10 | Distance milestones. With today's estimate (above) these are not reached in the synthetic matches. |

## Delivery safety

Events are matched by event id. An event delivered twice returns its original
metrics and changes nothing; the same id with different content, or an event
older than the last one processed, is refused. Ground-truth `labels` on the
events are removed before any metric is worked out.
