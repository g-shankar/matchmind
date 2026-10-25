# Decision scoring: "Should he have passed?"

How PitchPulse decides that a shooter had a better option. Everything here is
read from `backend/src/matchmind/stats/better_option.py` and
`stats/metrics.py`; the shorter metric-by-metric summary is in
[METRICS.md](METRICS.md#should-he-have-passed-better_optionpy). The data is
synthetic, so the scores describe simulated football only.

**Method version: v1.** The current formula is the one documented below. At the
time of writing the code carries no method-id or version constant; "v1" is the
name this document gives the current rules, and any change to a threshold or
formula is a new version that must update this page.

## What it answers

For a shot that did not score: was there a teammate in a clearly better
position, and how much better? The output is a `BetterOption` (shot value,
chosen teammate, pass success, option value, `times_better`, and the geometry
the replay draws). It is one deterministic function of one event.

## Inputs

All read from a single shot event; nothing outside it is used.

- The shooter's position, team, body part (header or not) and outcome.
- The **freeze frame**: every player in the final 35 m at the moment of the
  shot, with team side, keeper flag and position.
- The pitch geometry (105 x 68 m, goal centred at the far end). Positions are
  turned into the shooting team's attacking frame, scored, and converted back
  to absolute coordinates for drawing.

## Formula (v1)

1. **Chance quality** (xG-style) from a spot `p`:
   `q = sigmoid(-0.407 - 0.1298 * distance_to_goal + 1.149 * goal_angle)`, then
   multiplied by `0.75` for each outfield opponent inside the shooting cone
   (within 12 m), by `0.85` when the keeper stands on the shot line (within
   1.5 m of it and within 6 m of goal), and by `0.6` for a header. Clamped to
   0.01 to 0.95, rounded to 3 places.
2. **Shot value** = chance quality from the shooter's spot (header if the shot
   was a header).
3. **Candidate teammates**: every outfield teammate in the freeze frame who is
   not the shooter, is **onside** (no further forward than the second-last
   opponent, keeper included, or the shooter), and is **unmarked** (no opponent
   within 7 m).
4. **Pass success** from shooter to teammate:
   `0.92 - 0.006 * max(0, d - 10) - 0.45 * exp(-(lane / 1.8)^2)`, where `d` is
   the pass length in metres and `lane` is the distance of the closest opponent
   to the passing lane (opponents level with or behind the passer do not
   count). Clamped to 0.05 to 0.97.
5. **Option value** = pass success x chance quality from the teammate's spot
   (never a header). The best candidate is the highest option value; ties keep
   the lowest player id so the result is deterministic.
6. **Flag** when both hold:
   - `option value >= shot value + 0.10` (absolute margin), and
   - `option value >= 1.8 x shot value` (ratio).

   `times_better = round(option value / shot value, 1)`. A goal is never
   flagged: the decision paid off.

Worked example (the seeded demo moment, event `MM-DEMO-001-00717`): shot value
0.05; pass success 0.83; teammate chance 0.24; option value `0.83 x 0.24 = 0.2`;
`0.2 / 0.05 = 4.0x`. Both thresholds pass, so the moment is flagged.

## Thresholds

| Constant | Value | Meaning |
|---|---|---|
| `MIN_GAIN` | 0.10 | Absolute gap the option must beat the shot by |
| `MIN_RATIO` | 1.8 | Ratio the option must beat the shot by |
| `MIN_MARKER_M` | 7.0 | "Unmarked": no opponent closer than this |

Both gain and ratio are required so that 0.02 versus 0.05 (2.5x but tiny) is not
flagged. 7 m rather than 3 m because the synthetic team shapes often leave the
striker loose, and 3 m flagged up to 8 shots per unscripted match
([METRICS.md](METRICS.md)).

## Related: the unfound run

The same family has a second trigger (`analyse_run`): a run in behind where a
through ball was on and never played. The pass is "on" when the runner is
onside (0.3 m tolerance) and one second later is at least 1.5 m beyond the
second-last defender with a lane success of at least 0.6; it is reported only
when the projected chance is at least 0.2. It does not use the shot formula
above.

## Limits and caveats

- **A score is not proof of the right decision.** It compares two modelled
  chances at one instant. It does not know the shooter's skill, fatigue, the
  coach's instruction, or whether the pass would have been controlled.
- **The chance model is hand-set**, a logistic on distance and angle with fixed
  multipliers. It is not fitted to real match data, and its coefficients were
  chosen on synthetic matches.
- **One frozen instant.** Nobody moves after the freeze frame: defenders do not
  react to the pass, the receiver is assumed to take the ball where he stands,
  and pass speed, ball height and body orientation are ignored.
- **Final 35 m only.** Players outside the freeze frame are not candidates.
- **Ground passes only.** Lofted or cut-back passes are not modelled; a header
  penalty applies to the shot, never to the pass target.
- **The best option, not every option.** Only the single highest-value
  teammate is reported; dribbling on or recycling possession is not compared.
- **Thresholds are design choices**, tuned so the demo flags exactly its two
  scripted moments; they say "clearly better by this model", not "obviously
  wrong".
- **Not betting advice, and not a judgement on any person.** All players are
  invented.
- Numbers on screen come from this function through the stats engine; the
  fact-checker rejects any number in generated text that is not in the moment's
  facts ([TRUST.md](TRUST.md)).

## Tests

`backend/tests/test_stats.py` and `backend/tests/test_crew.py` cover the
detection and its narrative; run `cd backend && pytest -q tests/test_stats.py`.
