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
- The metric reference at the end of this page (formula, units, source events,
  window, range, quality flag, limitations, edge cases) is generated from
  `backend/src/matchmind/stats/registry.py` and served at `GET /api/metrics`.

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

Sign convention: **+1 is control, -1 is chaos**. Tests in
`backend/tests/test_registry.py` feed the engine two made-up spells and check
the direction: one team passing patiently for five minutes (long possessions,
no turnovers, soft passes) scores towards +1, and five minutes of tackles,
interceptions and driven clearances swapping the ball every few seconds scores
towards -1.

The snapshot also gives events per minute, turnovers per minute and average
passes per possession for the window, plus match totals for the score, xG and
shots.

## Player stats (`PlayerStats`)

| Stat | How it is counted |
|---|---|
| Touches | Passes, carries, dribbles, shots, interceptions, tackles, clearances and recoveries by the player. |
| Passes, completed, accuracy | Every pass attempt; accuracy = completed / attempted x 100. |
| Key passes, xA | A completed pass whose receiver shoots in the same possession before anyone else receives a pass. xA adds that shot's xG. |
| Assists | Key passes whose shot was a goal (a goal VAR ruled out does not count). |
| Goals, shots, shots on target, xG | From the player's shots. On target = goals plus saved shots. A goal VAR ruled out comes off goals (team and player); the shot, its xG and its on-target count stay. |
| Tackles won | Tackle events by the player. |
| Tackles lost | Times the player was dribbled past (a successful dribble names him as the opponent). |
| Tackles attempted, tackle success | Won plus lost; success = won / attempted x 100. |
| Interceptions | Count of those events. |
| Distance covered, speed bands, sprints, top speed (**estimated from synthetic tracking**) | See below. |
| Carry distance | Start-to-end distance of carries and successful dribbles. |

`physical_source` on each player says where distance, sprints and top speed
came from: `synthetic_tracking` (the live app and the demo) or
`event_estimate` (the engine on its own, without a tracking feed).

### Distance, speed bands and sprints (estimated from synthetic tracking)

Code: `backend/src/matchmind/stats/physical.py`. The tracking renderer
(`autoevent/tracking.py`, see docs/AUTO-EVENTING.md) draws all 22 players at
25 frames a second from the simulated match. From that feed, the way a
tracking provider would:

1. Each player's positions are averaged over 0.2 s blocks (5 frames), then
   smoothed with a centred 1 s moving average. The feed carries 5 cm of
   position noise; summed raw at 25 Hz it would add about 12 km of fake
   distance. After smoothing, a player standing still for 95 minutes covers
   under 0.3 km (a test checks this).
2. Speed of each 0.2 s step = step length / 0.2 s. A step faster than
   37.8 km/h (10.5 m/s, beyond any footballer) is a tracking glitch and is left
   out of distance and speed. In the synthetic feed these are moments where a
   player is snapped onto the ball.
3. Speed bands: **walk** under 7.2 km/h, **jog** 7.2-14.4 km/h, **run**
   14.4-25.2 km/h, **sprint** 25.2 km/h and over. Each step's length goes into
   the band of its speed; the four bands add up to the distance.
4. A **sprint** is an unbroken spell of at least 1 s in the sprint band.
5. **Top speed** is the fastest step.

The whole match is worked out once when the match loads (about a second, from
the same tracking feed the auto-eventing check uses, drawn once) into a
timeline sampled every second. The stats engine reads it as it plays, so the
numbers are always "so far" at the current clock, and a jump needs no extra
work. A player's numbers are re-sent to clients when his distance moves by
0.1 km, or his sprints or top speed change.

What the synthetic matches give (bundled five matches): outfield players
**9.2-11.9 km** (the one player sent off, in the demo, about 6 km), keepers 5.4-6.2 km, top
speeds 35-37 km/h, sprint distance 0-0.33 km. Real outfield players run about
10-12 km, so totals are plausible; sprint counts (0-8 per player) are lower
than in real matches because the synthetic players only sprint on recovery
runs and to reach passes. These numbers are **estimated from synthetic
tracking**: not real tracking and not video, and they must be labelled that
way wherever they are shown.

Without a tracking feed (the engine on its own) distance falls back to the old
estimate: straight lines between each player's successive known positions in
the events (action start and end, receiving a pass, freeze frames, run
frames). That is a lower bound of roughly 0.2-3.8 km per match and is marked
`physical_source: event_estimate`.

## Basic stats (`GET /api/match/stats/basic`)

A plain layer beside the advanced metrics, for viewers who want the box score.
Per team and per player, match so far:

| Stat | How it is counted |
|---|---|
| Possession % (team) | Completed passes / both teams' completed passes (a pass share, not time on the ball). |
| Pass accuracy % | Completed / attempted x 100. The denominator is **every pass attempt**, passes out of play included, and is sent beside the percentage. |
| Shots / on target | Shots; on target = goals plus saved shots. |
| Tackles won (of attempted) | Won; attempted = won plus dribbled past. |
| Interceptions | Interception events. |
| Distance, top speed | From synthetic tracking (above), labelled. Team distance is the sum of its players. |
| PPDA (team) | See below. |

### PPDA (passes per defensive action)

How hard a team presses: the passes the opponent attempts in their own 60% of
the pitch (attacking-frame x under 63 m), divided by this team's defensive
actions in that same zone (tackles won, challenges lost, interceptions and
fouls, at x 42 m or more in this team's attacking frame). Lower means a more
intense press. It is null until the team makes a defensive action in the zone.
The synthetic events have no pressure or duel events, so the action count is
narrower than a data provider's and the values run low (3.5-4.1 at full time in the bundled matches).

## Broadcast thresholds

Constants in `metrics.py`, used by the Spotter for on-screen tags:

| Constant | Value | Meaning |
|---|---|---|
| `SPEED_BURST_KMH` | 30.0 | Player speed worth a pitch tag. With tracking: a sprint (above) that peaked at 30 km/h or more, at most one per player per 20 minutes. Without tracking: a carry, dribble or run recorded that fast. |
| `ROCKET_SHOT_KMH` | 100.0 | Shot speed worth a pitch tag (also sets "rocket shot" on the event) |
| `DISTANCE_MILESTONES_KM` | 5, 10 | Distance milestones from synthetic tracking: the first player in each team to pass each one (so at most four a match). Not fired from the event estimate. |

### Key tackle

A tackle won in the tackler's own third (attacking-frame x under 35 m) where
the attackers' expected threat at the spot (the xT grid above) was at least
0.09, about the last 25 m in front of goal. Inside the own penalty box it is
marked last-ditch. At most one every 5 minutes of match clock. The moment's
facts carry the threat stopped (xT), the distance from the tackler's own goal,
his tackles won so far and, when the tackle ended a failed dribble, the player
he dispossessed. The demo match has three (47:36, 64:46 last-ditch, 72:20).

## Corrections (VAR)

A `var_review` event names the goal it decided on (`reviewed_event_id`) and
why (`review_reason`: offside, handball or foul). When the outcome is
`overturned`:

| Stat | Effect |
|---|---|
| Score (`score_home` / `score_away`) | The goal comes off, from the review event on. |
| Scorer's goals, assister's assists | The goal and its assist come off. |
| Shots and xG (team and player) | **Unchanged.** The shot was taken; only the goal is ruled out. |
| Key passes, xA | **Unchanged**, for the same reason. |
| Recap goals and key moments | The ruled-out goal is left out. |

An `overturned` review of a shot that is not a counted goal, or a second
review of the same goal, changes nothing. A `stands` review changes no stat and
makes no moment. Nothing is recomputed backwards: the snapshot before the
review still shows the goal, because that was true at the time; seeking back
before the review shows it again, and seeking past it never does.

## Delivery safety

Events are matched by event id. An event delivered twice returns its original
metrics and changes nothing; the same id with different content, or an event
older than the last one processed, is refused. Ground-truth `labels` on the
events are removed before any metric is worked out.

## Metric reference

<!-- BEGIN METRIC REGISTRY: generated from backend/src/matchmind/stats/registry.py -->
<!-- Do not edit by hand: run `python -m matchmind.stats.registry --write` from backend/. -->

Quality flags:

- **counted**: Direct count or ratio of events; no model.
- **calibrated**: Model constants set against stated reference values.
- **heuristic**: Hand-weighted rule; reasonable, not fitted to data.
- **estimated_from_synthetic_tracking**: Worked out from the synthetic 25 Hz tracking feed (rendered from the simulated match; not real tracking, not video).

### Per event

#### Pass distance (`pass_distance_m`)

| | |
|---|---|
| Formula | Straight line from where the pass was played to where it ended. |
| Symbols | `d = \|end - start\|` |
| Units | m |
| Source events | pass |
| Window | per event |
| Range | 0-125 |
| Quality | counted |
| Limitations | 2D only: no ball height or curve. |
| Edge cases | Passes without an end location have no distance (null). |
| Fields | `event.metrics.pass_distance_m` |

#### Progressive pass or carry (`progressive`)

| | |
|---|---|
| Formula | Moves the ball at least 10 m forward and ends at least 25% closer to the goal centre. |
| Symbols | `dx >= 10 and D(end) <= 0.75 D(start)` |
| Units | yes/no |
| Source events | pass, carry |
| Window | per event |
| Range | true/false |
| Quality | counted |
| Limitations | Counted for failed passes too; the flag says nothing about success. |
| Edge cases | Backwards or square moves are never progressive. |
| Fields | `event.metrics.progressive` |

#### Pass difficulty (`pass_difficulty`)

| | |
|---|---|
| Formula | Weighted average of capped factors: length, pressure on the passer, forward progress, ending in the final third, cross or through ball, opponents in the lane, angle across the pitch. |
| Symbols | `PD = 100 * sum(w_i f_i) / sum(w_i), f_i in [0, 1]` |
| Units | 0-100 |
| Source events | pass, run |
| Window | per event |
| Range | 0-100 |
| Quality | heuristic |
| Limitations | Opponents in the lane are only known for through balls after a tracked run; the term is dropped (weights rescaled) otherwise. |
| Edge cases | A pass of zero length scores on pressure and type only. |
| Fields | `event.metrics.pass_difficulty` |

#### Expected threat added (xT) (`xt_delta`)

| | |
|---|---|
| Formula | Threat of the zone where the ball ends minus the zone where it started (12 x 8 grid); a failed pass gives up the starting threat. |
| Symbols | `xT_end - xT_start (complete); -xT_start (failed)` |
| Units | xT (goal probability) |
| Source events | pass, carry |
| Window | per event |
| Range | -0.61 to +0.61 |
| Quality | heuristic |
| Limitations | A smoothed, symmetric grid from the team's first build, not fitted to these matches. |
| Edge cases | Moves inside one zone add 0. |
| Fields | `event.metrics.xt_delta` |

#### Ball speed (`ball_speed_kmh`)

| | |
|---|---|
| Formula | Recorded ball speed of the pass, shot or clearance. |
| Symbols | `v_ball * 3.6` |
| Units | km/h |
| Source events | pass, shot, clearance |
| Window | per event |
| Range | 0-140 |
| Quality | counted |
| Limitations | Synthetic events: the speed is the simulator's, at release. |
| Edge cases | Null when the event has no ball speed. |
| Fields | `event.metrics.ball_speed_kmh` |

#### Chance quality (xG) (`chance_quality`)

| | |
|---|---|
| Formula | Logistic curve on distance to goal and the angle of the goal mouth, times 0.75 per defender in the shooting cone, 0.85 for a keeper on the line and 0.6 for a header. |
| Symbols | `xG = clamp(sigma(a + b d + c theta) * 0.75^n * k_keeper * k_header, 0.01, 0.95)` |
| Units | probability |
| Source events | shot |
| Window | per event |
| Range | 0.01-0.95 |
| Quality | calibrated |
| Limitations | Calibrated to three reference chances (penalty spot about 0.25, 20 m central about 0.07, 6 m central about 0.56), not fitted to match outcomes. |
| Edge cases | Shots without a freeze frame skip the defender and keeper terms. |
| Fields | `event.metrics.chance_quality`, `state.xg_home`, `state.xg_away`, `player.xg` |

### Moments

#### Should he have passed? (better option) (`times_better`)

| | |
|---|---|
| Formula | Best unmarked, onside teammate: chance the pass arrives x that teammate's xG, compared with the shot's xG. Flagged when at least 0.10 higher and 1.8 times the shot. |
| Symbols | `alt = P(pass) * xG_mate; flag if alt - xG_shot >= 0.10 and alt / xG_shot >= 1.8` |
| Units | x (ratio) |
| Source events | shot |
| Window | per event |
| Range | >= 1.8 when flagged |
| Quality | calibrated |
| Limitations | Thresholds (7 m unmarked, 0.10, 1.8) were set on the five bundled matches. |
| Edge cases | Goals are never flagged. |
| Fields | `card.replay.times_better`, `moment.facts.times_better` |

#### Unfound run (`projected_chance_quality`)

| | |
|---|---|
| Formula | When a runner was onside then 1.5 m beyond the line with a clear lane, the xG from his last tracked spot; reported when the ball never came and the chance is at least 0.2. |
| Symbols | `xG(runner_end) with defenders between runner and goal` |
| Units | probability |
| Source events | run |
| Window | 3 s run window |
| Range | 0.2-0.95 when reported |
| Quality | heuristic |
| Limitations | Runs carry 6 tracking frames (every 0.5 s), not continuous tracking. |
| Edge cases | No defenders between runner and goal counts as one-on-one. |
| Fields | `card.replay.projected_chance_quality` |

### Rolling window

#### Possession (rolling) (`possession_pct`)

| | |
|---|---|
| Formula | Team's completed passes over both teams' completed passes in the window. |
| Symbols | `100 * P_team / (P_home + P_away)` |
| Units | % |
| Source events | pass |
| Window | rolling 5 min of match clock |
| Range | 0-100 |
| Quality | counted |
| Limitations | A pass share, not time on the ball. |
| Edge cases | 50/50 when neither team completed a pass in the window. |
| Fields | `state.home.possession_pct`, `state.away.possession_pct` |

#### Field tilt (`field_tilt_pct`)

| | |
|---|---|
| Formula | Team's completed passes ending in the final third over both teams' final-third passes. |
| Symbols | `100 * FT_team / (FT_home + FT_away)` |
| Units | % |
| Source events | pass |
| Window | rolling 5 min of match clock |
| Range | 0-100 |
| Quality | counted |
| Limitations | Final third = the last 35 m; touches other than passes are not counted. |
| Edge cases | 50/50 when there are no final-third passes in the window. |
| Fields | `state.home.field_tilt_pct`, `state.away.field_tilt_pct` |

#### Pressure index (`pressure_index`)

| | |
|---|---|
| Formula | Saturating load of final-third passes, box entries, shots and xG. |
| Symbols | `100 * (1 - exp(-L / 30)), L = FT + 2 BE + 4 S + 20 xG` |
| Units | 0-100 |
| Source events | pass, carry, dribble, shot |
| Window | rolling 5 min of match clock |
| Range | 0-100 |
| Quality | heuristic |
| Limitations | Weights are hand-set; it measures attacking pressure, not pressing. |
| Edge cases | 0 with no attacking actions. |
| Fields | `state.home.pressure_index`, `state.away.pressure_index` |

#### Momentum (`momentum`)

| | |
|---|---|
| Formula | Time-weighted moving average of home pressure index minus away pressure index. |
| Symbols | `M += (1 - exp(-dt / 120)) * ((PI_home - PI_away) - M)` |
| Units | -100 (away on top) to +100 (home on top) |
| Source events | pass, carry, dribble, shot |
| Window | exponential, 120 s time constant |
| Range | -100 to +100 |
| Quality | heuristic |
| Limitations | Follows the pressure index, so it inherits its weights. |
| Edge cases | Starts at 0 on the first event. |
| Fields | `state.momentum` |

#### Control vs chaos (CCI) (`control_chaos`)

| | |
|---|---|
| Formula | Rises with passes per possession, falls with turnovers per minute and direct, driven balls. Sign convention: +1 is patient control, -1 is end-to-end chaos. |
| Symbols | `clamp(0.4 - 1.8 (0.5 T + 0.5 D - 0.6 C), -1, 1); T = turnovers/min / 4, D = direct share, C = passes per possession / 6` |
| Units | -1 (chaos) to +1 (control) |
| Source events | pass, interception, tackle, clearance, shot |
| Window | rolling 5 min of match clock |
| Range | -1 to +1 |
| Quality | heuristic |
| Limitations | Ported from the team's first build and rescaled; not fitted to outcomes. |
| Edge cases | 0 with no events; a long passing spell tends to +1, a turnover-heavy spell to -1 (tests show both directions). |
| Fields | `state.control_chaos`, `control_chaos.chaos_index` |

### Per player

#### Pass accuracy (`pass_accuracy`)

| | |
|---|---|
| Formula | Completed passes over attempted passes (every pass attempt, out of play included). |
| Symbols | `100 * completed / attempted` |
| Units | % |
| Source events | pass |
| Window | match so far |
| Range | 0-100 |
| Quality | counted |
| Limitations | Does not weigh pass difficulty. |
| Edge cases | 0 when no passes were attempted (the denominator is shown next to it). |
| Fields | `player.pass_accuracy`, `basic.teams.pass_accuracy_pct`, `basic.players.pass_accuracy_pct` |

#### Expected assists (xA) and key passes (`xa`)

| | |
|---|---|
| Formula | A completed pass whose receiver shoots in the same possession before anyone else receives a pass is a key pass; xA adds that shot's xG. |
| Symbols | `xA = sum xG(shot after key pass)` |
| Units | xG |
| Source events | pass, shot |
| Window | match so far |
| Range | >= 0 |
| Quality | counted |
| Limitations | Inherits xG's calibration. |
| Edge cases | One shot per pass: a second shot in the same possession is not credited again. |
| Fields | `player.xa`, `player.key_passes` |

#### Shots and shots on target (`shots`)

| | |
|---|---|
| Formula | Shots taken; on target = goals plus saved shots. |
| Symbols | `on_target = goals + saved` |
| Units | count |
| Source events | shot |
| Window | match so far |
| Range | >= 0 |
| Quality | counted |
| Limitations | Blocked shots are not on target. |
| Edge cases | - |
| Fields | `player.shots`, `player.shots_on_target`, `basic.teams.shots` |

#### Tackles won, lost and success (`tackles`)

| | |
|---|---|
| Formula | Won: tackle events. Lost: the player was dribbled past (a successful dribble names him as the opponent). Success = won over won plus lost. |
| Symbols | `success = 100 * won / (won + lost)` |
| Units | count, % |
| Source events | tackle, dribble |
| Window | match so far |
| Range | 0-100 % |
| Quality | counted |
| Limitations | The simulator records no other failed challenges, so attempts are a lower bound. |
| Edge cases | Success is 0 with no attempts. |
| Fields | `player.tackles_won`, `player.tackles_lost`, `player.tackle_success_pct` |

#### Interceptions (`interceptions`)

| | |
|---|---|
| Formula | Interception events by the player. |
| Symbols | `count(interception)` |
| Units | count |
| Source events | interception |
| Window | match so far |
| Range | >= 0 |
| Quality | counted |
| Limitations | - |
| Edge cases | - |
| Fields | `player.interceptions`, `basic.teams.interceptions` |

#### Distance covered (`distance_km`)

| | |
|---|---|
| Formula | Positions averaged over 0.2 s blocks and smoothed over 1 s; the lengths of the 0.2 s steps are added up. Steps faster than 37.8 km/h are tracking glitches and left out. |
| Symbols | `sum \|p_k - p_(k-1)\| over 0.2 s steps with \|v\| <= 10.5 m/s` |
| Units | km |
| Source events | synthetic tracking (25 Hz) |
| Window | match so far (per-second timeline) |
| Range | 0-14 |
| Quality | estimated_from_synthetic_tracking |
| Limitations | Synthetic tracking: off-ball movement follows simple rules, so totals are plausible, not real. Without tracking the field falls back to the event estimate (physical_source). Smoothing cuts tight corners (about 3% shorter than raw). |
| Edge cases | A sent-off player stops at the red card; stoppages count (players still move). |
| Fields | `player.distance_km`, `basic.players.distance_km` |

#### Distance by speed band (`speed_bands`)

| | |
|---|---|
| Formula | Each 0.2 s step's length goes into the band of its speed: walk < 7.2 km/h, jog 7.2-14.4, run 14.4-25.2, sprint >= 25.2. |
| Symbols | `band(v) for each step; bands sum to distance_km` |
| Units | km |
| Source events | synthetic tracking (25 Hz) |
| Window | match so far (per-second timeline) |
| Range | 0-14 |
| Quality | estimated_from_synthetic_tracking |
| Limitations | Synthetic tracking: off-ball movement follows simple rules, so totals are plausible, not real. Without tracking the field falls back to the event estimate (physical_source). |
| Edge cases | Rounding to 0.01 km can make the bands differ from the total by 0.01-0.02. |
| Fields | `player.walk_km`, `player.jog_km`, `player.run_km`, `player.sprint_km` |

#### Sprints (`sprints`)

| | |
|---|---|
| Formula | An unbroken spell of at least 1 s at 25.2 km/h or more. |
| Symbols | `count(spells with v >= 25.2 km/h for >= 1 s)` |
| Units | count |
| Source events | synthetic tracking (25 Hz) |
| Window | match so far |
| Range | >= 0 |
| Quality | estimated_from_synthetic_tracking |
| Limitations | Synthetic tracking: off-ball movement follows simple rules, so totals are plausible, not real. Without tracking the field falls back to the event estimate (physical_source). The synthetic players sprint less often than real ones. |
| Edge cases | Without tracking: actions faster than 28.8 km/h (event estimate). |
| Fields | `player.sprints` |

#### Top speed (`top_speed_kmh`)

| | |
|---|---|
| Formula | Fastest 0.2 s step of the smoothed track. |
| Symbols | `max v_k * 3.6` |
| Units | km/h |
| Source events | synthetic tracking (25 Hz) |
| Window | match so far |
| Range | 0-37.8 |
| Quality | estimated_from_synthetic_tracking |
| Limitations | Synthetic tracking: off-ball movement follows simple rules, so totals are plausible, not real. Without tracking the field falls back to the event estimate (physical_source). |
| Edge cases | Without tracking: the fastest recorded carry, dribble or run. |
| Fields | `player.top_speed_kmh`, `basic.players.top_speed_kmh` |

### Per team

#### Possession (match) (`match_possession_pct`)

| | |
|---|---|
| Formula | Team's completed passes over both teams' completed passes, whole match so far. |
| Symbols | `100 * P_team / (P_home + P_away)` |
| Units | % |
| Source events | pass |
| Window | match so far |
| Range | 0-100 |
| Quality | counted |
| Limitations | A pass share, not time on the ball. |
| Edge cases | 50/50 before the first completed pass. |
| Fields | `basic.teams.possession_pct` |

#### Passes per defensive action (PPDA) (`ppda`)

| | |
|---|---|
| Formula | Passes the opponent attempts in their own 60% of the pitch, over this team's tackles, challenges lost, interceptions and fouls in that same zone. Lower means a more intense press. |
| Symbols | `PPDA = opp_passes(x_opp < 63 m) / def_actions(x_own >= 42 m)` |
| Units | passes per action |
| Source events | pass, tackle, dribble, interception, foul |
| Window | match so far |
| Range | > 0 |
| Quality | counted |
| Limitations | Synthetic events have no pressure or duel events, so the action count is narrower than a data provider's. |
| Edge cases | Null until the team makes a defensive action in the zone. |
| Fields | `basic.teams.ppda` |

### Not computed

| Metric | Why not |
|---|---|
| Fantasy bonus points (BPS) | Needs the official scoring rules and data feed; not built. |
| Clean-sheet odds | Needs a calibrated match-outcome model; not built. |
| Half-space occupation | Needs continuous team shape analysis; planned on top of the synthetic tracking. |
| Defensive line height | Planned on top of the synthetic tracking; not computed yet. |
| Pressures and pressing duels | The synthetic events have no pressure events; PPDA is the pressing measure. |
<!-- END METRIC REGISTRY -->
