# Cue sheet (output contract v1.0)

The cue sheet is PitchPulse's output for broadcast graphics systems: a numbered
list of instructions ("cues") saying what goes on air, on which layer, when, for
how long, and when it must come off. The in-app overlay (`#overlay`) follows the
same cues, so what an operator sees in OBS or vMix matches the studio.

- Python model: `backend/src/matchmind/crew/cues.py` (`Cue`, `CueCompiler`)
- JSON Schema: `backend/schema/cue.schema.json` (`$id urn:pitchpulse:cue:1.0`).
  Regenerate with `PYTHONPATH=src python -m matchmind.crew.cues > schema/cue.schema.json`;
  a test fails when it is out of date.
- TypeScript: `Cue`, `CueSheetPage`, `CuesData` in `frontend/src/api/contract.ts`

## Where cues come from

| Channel | What you get |
|---|---|
| `GET /api/match/cue-sheet?persona=&lang=&favourite_team=&since_seq=&limit=` | Every cue so far for one audience, paged by `seq` |
| WebSocket `CUES` message | New cues for this connection, right after the `MATCH_TICK` that caused them |
| `INITIAL_SNAPSHOT.cue_sheet` | `{ sheet_id, last_seq, active }`: what is on air now (connect, reconnect, seek, reset) |

A **sheet** is one audience: `sheet_id = "<match>/<persona>/<language>[/club=X][/focus=P][/metric=M]"`.
Each sheet numbers its cues `seq = 1, 2, 3...` with no gaps. Cue ids are stable:
compiling the same match to the same point always gives the same cues, byte for
byte, also after jumping away and back.

Text in the sheet is the template crew's fact-checked text. The sheet never
calls a paid model, even when the live crew is in AI mode (see Limits).

## The cue

| Field | Meaning |
|---|---|
| `schema_version` | `"1.0"` |
| `cue_id` | Stable id, e.g. `goal-MM-DEMO-001-00817@full_screen`, `scorebug@<moment>`, `retract:<cue_id>`, `clear@1:period_end` |
| `seq` | Position in this sheet (1, 2, 3...) |
| `op` | `show`, `update`, `retract`, `supersede`, `clear` |
| `layer` | `lower_third`, `side_panel`, `pitch_tag`, `metric_alert`, `full_screen`, `scorebug`, `momentum_ribbon`, `telestration`, or `all` (clear only) |
| `moment_id`, `kind` | The crew moment behind the cue |
| `retracts` | Cue ids this cue takes off air (op `retract`) |
| `supersedes` | Cue ids this cue replaces (op `supersede`, and state-layer updates after a correction) |
| `clears` | Layers a `clear` empties |
| `reason` | `var_offside`, `var_handball`, `var_foul` (corrections) or `period_end`, `full_time` (clears) |
| `start`, `end` | `CueTime` (see Timing); `end` is `null` for state layers (on until updated) |
| `duration_s` | Seconds on air; `0` for retract and clear |
| `priority` | 0-100; decides collisions |
| `collision` | What happened when it was placed: `replace`, `queue`, `stack`, `latest` |
| `persona`, `language`, `rtl` | The audience; `rtl` is true for Arabic text |
| `text` | `{ headline, body, why, text_language }` or `null` |
| `evidence` | The numbers behind the text, each with its source event |
| `source_event_ids`, `team`, `player_ids`, `produced_by` | Provenance |
| `scorebug` | `{ home_id, away_id, score_home, score_away }` (scorebug layer) |
| `ribbon` | `{ momentum, pressure_home, pressure_away }` (momentum ribbon, once per minute of play) |
| `telestration` | `{ frame: "pitch_105x68", shapes: [...] }`: arrows, circles and markers in metres on a 105 x 68 pitch, for "Should he have passed?" and unfound-run replays |

## Timing model

`CueTime = { period, clock_s, match_clock, t_s }`.

- `period` and `clock_s` are the engine's match clock. It is **not monotonic**:
  first-half stoppage runs past 2700 s while `period` is still 1, and the second
  half restarts at 2700 s.
- `match_clock` is the clock as shown, e.g. `39:11` or `45+1:20`.
- `t_s` is seconds of play since kick-off with the halves joined end to end
  (half time removed). It **always increases**. Sort, compare and schedule on
  `t_s`; show `match_clock`.

A cue is on air from `start.t_s` until `end.t_s` (or until something retracts,
supersedes, clears or replaces it). In playback the server plays
`10 x speed_multiplier` match seconds per real second, so a cue's real on-air
time is `duration_s / (10 x speed)`.

## Collision rules

Each layer has a fixed policy (`LAYER_POLICY` in `cues.py`):

| Layer | Holds | When busy |
|---|---|---|
| `full_screen` | 1 | Equal or higher priority replaces; lower waits up to 8 s, else dropped |
| `lower_third` | 1 | Waits up to 8 s for the current cue to end; higher priority replaces |
| `side_panel` | 2 | Stacks, newest on top; a third pushes the oldest off |
| `pitch_tag` | 3 | Stacks; the oldest leaves first |
| `metric_alert` | 3 | Ticker; the oldest leaves first |
| `telestration` | 1 | One drawing, on air exactly as long as its card |
| `scorebug` | 1 | State layer: the newest update is the score |
| `momentum_ribbon` | 1 | State layer: the newest update is the momentum |

A queued cue keeps its `seq` but its `start` moves later, so `t_s` order and
`seq` order can differ for queued cues only. Retract, supersede and clear cues
always apply. A sheet holds at most 5000 cues; past that only priority 80+ cues
and lifecycle ops are added.

## Applying cues (client rules)

1. Apply cues in `seq` order. Apply each `cue_id` once; a repeat (retry,
   duplicate delivery, replayed page) changes nothing.
2. `show` / `update`: put the cue on its layer (state layers keep only the newest).
3. `retract`: take every id in `retracts` off air.
4. `supersede`: take every id in `supersedes` off air, then show this cue.
5. `clear`: empty every layer in `clears` (transient layers at half time and full time; the scorebug stays).
6. A cue whose `moment_id` was ruled out by a VAR retract is never shown, even
   if it arrives late or out of order.
7. A snapshot (`INITIAL_SNAPSHOT.cue_sheet`) or a `CUES` message carrying
   `active` replaces local state: start from `active`.

The server's `active_cues(cues, now_t)` in `cues.py` and the browser's
`frontend/src/state/cues.ts` implement these rules; tests cover duplicates,
out-of-order delivery, seeks across a correction and reconnects.

## Lifecycle

```
                show ──────────────► on air ──── end.t_s reached ───► off
                  ▲                    │
     update (state layers: replace     ├── retract (VAR) ───────────► off, moment ruled out for good
      the previous cue on the layer)   ├── supersede by a correction ► off, correction card on air
                                       ├── replaced / pushed off by collision rules ► off
                                       └── clear (half time, full time) ──► off
```

A VAR overturn in one tick produces, in this order:
`retract` for each cue of the goal (card, telestration, scorebug), then the
correction card as `supersede`, then a scorebug `update` that supersedes the
goal's scorebug cue with the corrected score.

## Example

The demo match (`MM-DEMO-001`), casual English, around the disallowed goal.
Some cues, fields, text and evidence left out.

```json
{
  "schema_version": "1.0",
  "match_id": "MM-DEMO-001",
  "sheet_id": "MM-DEMO-001/casual/en",
  "persona": "casual",
  "language": "en",
  "position": { "period": 1, "clock_s": 2422.08, "match_clock": "40:22", "t_s": 2422.08 },
  "last_seq": 71, "since_seq": 63, "has_more": false, "next_since_seq": 71,
  "cues": [
    { "seq": 64, "cue_id": "goal-MM-DEMO-001-00817@full_screen", "op": "show", "layer": "full_screen",
      "start": { "period": 1, "clock_s": 2351.66, "match_clock": "39:11", "t_s": 2351.66 },
      "priority": 95, "collision": "replace", "text": { "headline": "GOAL! Asante scores for Northbridge FC" } },
    { "seq": 65, "cue_id": "scorebug@goal-MM-DEMO-001-00817", "op": "update", "layer": "scorebug",
      "end": null, "collision": "latest",
      "scorebug": { "home_id": "NBR", "away_id": "HCY", "score_home": 2, "score_away": 0 } },
    { "seq": 66, "cue_id": "retract:goal-MM-DEMO-001-00817@full_screen", "op": "retract", "layer": "full_screen",
      "retracts": ["goal-MM-DEMO-001-00817@full_screen"], "reason": "var_offside",
      "start": { "period": 1, "clock_s": 2422.08, "match_clock": "40:22", "t_s": 2422.08 }, "duration_s": 0.0 },
    { "seq": 67, "cue_id": "retract:scorebug@goal-MM-DEMO-001-00817", "op": "retract", "layer": "scorebug",
      "retracts": ["scorebug@goal-MM-DEMO-001-00817"], "reason": "var_offside" },
    { "seq": 68, "cue_id": "correction-MM-DEMO-001-00818@full_screen", "op": "supersede", "layer": "full_screen",
      "kind": "correction", "reason": "var_offside", "priority": 95, "duration_s": 8.0,
      "supersedes": ["goal-MM-DEMO-001-00817@full_screen", "scorebug@goal-MM-DEMO-001-00817"],
      "text": { "headline": "No goal! VAR rules out Asante",
                "body": "Kofi Asante's goal at 39:11 is ruled out for offside after a VAR review. It stays Northbridge FC 1-0 Harbour City." },
      "evidence": [{ "label": "Home score", "value": 1, "source_event_id": "MM-DEMO-001-00818" }],
      "source_event_ids": ["MM-DEMO-001-00818", "MM-DEMO-001-00817"] },
    { "seq": 70, "cue_id": "scorebug@correction-MM-DEMO-001-00818", "op": "update", "layer": "scorebug",
      "supersedes": ["scorebug@goal-MM-DEMO-001-00817"], "reason": "var_offside", "end": null,
      "scorebug": { "home_id": "NBR", "away_id": "HCY", "score_home": 1, "score_away": 0 } }
  ]
}
```

Paging: `GET /api/match/cue-sheet?since_seq=0&limit=500`, then repeat with
`since_seq = next_since_seq` while `has_more` is true. Poll with the last
`next_since_seq` to get only new cues, or use the WebSocket `CUES` stream.

## Compatibility

`CUES`, `INITIAL_SNAPSHOT.cue_sheet`, `OverlayCard.retracts`,
`Bookmark.ruled_out` and the `var_review` event fields are additions. A client
that ignores them keeps working, but it should at least drop cards whose
`moment_id` appears in a later card's `retracts`. Breaking changes to the cue
shape will bump `schema_version`.

## Limits

- Metric alerts for a viewer's focus metric are in the live `CUES` stream but
  not in the compiled REST sheet.
- With paid AI switched on, live cards may be model-worded while the compiled
  sheet uses template text (numbers are identical; both are fact-checked).
- A VAR review that lets a goal stand changes nothing and makes no cue.
- The offline demo (no backend) builds a simplified sheet in the browser: no
  layer queueing, momentum ribbon or telestration cues.
