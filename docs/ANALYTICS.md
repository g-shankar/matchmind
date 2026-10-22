# Analytics: Lakehouse export, decision dataset and real-time queries

PitchPulse turns its synthetic matches into a Microsoft Fabric friendly dataset: a star schema
(Parquet, with a CSV fallback), a labelled decision dataset for machine learning, and Eventhouse
(KQL) tables for real-time queries over the Event Hubs stream. All data is synthetic (two
fictional clubs). Every number comes from the stats engine (`backend/src/matchmind/stats`) and
the rule-based Spotter; the export never estimates or models a value of its own.

Code: `backend/src/matchmind/analytics/`. Tests: `backend/tests/test_analytics.py`.
Fabric assets and owner-run setup: `analytics/fabric/` (see its README).

## Status

| Part | State |
|---|---|
| `matchmind-lakehouse export` / `labels` / `enrich` | Implemented and tested (offline, no Azure) |
| Parquet output | Implemented and tested (needs the `analytics` extra, `pyarrow`, Apache-2.0) |
| CSV fallback without pyarrow | Implemented and tested |
| Fabric notebook (`pitchpulse_lakehouse.ipynb`) | Written, valid JSON and Python, view SQL checked on a local engine. **Not run in Fabric yet** |
| Eventhouse KQL (`eventhouse.kql`) | Written, table and mapping columns checked against the event schema in tests. **Not run against an Eventhouse yet** |
| Live enriched stream (stats engine to a second event hub) | **Planned, not built.** Today the enriched events are a file (`enrich`) |
| Fabric capacity, workspace, Power BI report | **Not connected yet** (owner-run, see `analytics/fabric/README.md`) |

## Commands

```
pip install -e "backend[analytics]"            # adds pyarrow; without it the export writes CSV

matchmind-lakehouse export --out data/lakehouse                 # the 5 bundled matches
matchmind-lakehouse export --input data/matches --seeds 50 --out data/lakehouse   # expand: 5 + 50 new matches
matchmind-lakehouse export --seeds 20 --seed-start 5000 --with-labels --out data/lakehouse
matchmind-lakehouse labels --input data/matches --out data/lakehouse-labels
matchmind-lakehouse enrich --input data/matches --out enriched.jsonl   # events + stats, JSON lines
```

* `--seeds N` simulates N new unscripted matches with seeds `seed-start .. seed-start + N - 1`
  (default 1000). The same seed always gives the same match, whatever else is generated. Match ids
  are `MM-GEN-<seed>`; kick-offs are spread over a season of weekly fixtures.
* `--beats K` (default 3) adds K story beats to each new match: "should he have passed?" shots and
  runs where the through ball never came. The engine's own chance model produces these only a few
  times per hundred shots, so without them the decision labels have almost no positives. The beats
  are marked in `events.truth_labels` (`scripted:*`) so they stay separable from natural play.
  `--beats 0` gives purely unscripted matches.
* More matches means more rows, not more clubs: there are two fictional squads (22 players).
* Output is deterministic: same inputs give the same CSV bytes (and the same Parquet bytes for the
  same library versions). Rows are ordered by match id, then event sequence. Re-running into the
  same folder overwrites, and a re-export in the other format removes the old part file.

## Layout

```
<out>/_manifest.json                      format, matches, row count per table
<out>/Tables/<table>/part-0.parquet       (or part-0.csv)
<out>/Tables/<table>/_schema.json         columns, types, descriptions, primary and foreign keys, row count
```

Types are `string`, `int64`, `float64`, `bool` and `timestamp` (UTC, microseconds). CSV is UTF-8
with LF line endings, `true`/`false`, ISO-8601 timestamps and an empty cell for null.

## Tables and row counts

Row counts of the bundled dataset (5 matches in `backend/data/matches`), checked by a test:

| Table | Kind | Rows | What it holds |
|---|---|---|---|
| `teams` | dim | 2 | The two fictional clubs |
| `players` | dim | 22 | Fictional squads, 11 per club |
| `matches` | dim | 5 | One row per match: score, xG, seed, kick-off |
| `events` | fact | 10433 | Every event, with stats-engine metrics (xG, pass difficulty, pressure, xT, sprint) and the running match state (score, cumulative xG, momentum, five-minute pressure index) |
| `moments` | fact | 328 | Spotter output: kind, priority, players, facts as JSON |
| `moment_facts` | fact | 5801 | The same facts, one row per fact (text and numeric value) |
| `better_options` | fact | 6 | "Should he have passed?": shot vs best pass, and unfound runs, with positions |
| `player_match` | fact | 110 | Per-player aggregates for one match |
| `team_match` | fact | 10 | Per-club aggregates for one match |
| `decision_labels` | fact | 6612 | ML training set (`labels` command, or `export --with-labels`) |

Relationships (also in each `_schema.json`): every fact row points to `matches` by `match_id`, to
`teams` by `team_id` and to `players` by `player_id`; `moments`, `better_options` and
`decision_labels` point to `events` by `event_id`.

An example of expanding the dataset: `export --input data/matches --seeds 20 --with-labels` gives
25 matches, 53,149 events, 1,893 moments, 69 better-option rows, 33,399 decision rows (about 25
seconds on a laptop).

## Decision dataset (`decision_labels`)

One row per shot or pass. Features come from the stats engine and the event (position in the
attacking frame, zone, pressure, ball speed, pass distance and difficulty, shot xG, defenders
within 7 m, keeper distance, the best alternative pass option). Labels:

* Shots: `label_better_option` (the engine's "should have passed" flag), `label_xg_gain`
  (best alternative minus the shot, floored at zero, whatever the flag thresholds), `label_goal`.
* Passes: `label_completed`, `label_progressive`, `label_leads_to_shot` (same club shoots in the
  same possession within 15 s) and `label_next_shot_xg`.
* `split` is `train` (70%), `val` (20%) or `test` (10%) by a hash of the match id, so a match is
  never in two splits and keeps its split as the dataset grows. The hash salt was picked so the
  five bundled matches cover all three splits.

The simulator's ground-truth labels (`events.truth_labels`) are for evaluation only and never a
feature. A test shows that removing them changes no number.

## Real-time (Eventhouse)

`analytics/fabric/eventhouse.kql` defines `MatchEvents` (the raw `match-events` stream, mapped from
the event schema) and `MatchEventsEnriched` (the `events` table columns), plus five queries: live
xG race, pressure by five-minute window, sprint leaders, better-option count and a raw stream check.
The queries only count, sum or take the latest value of numbers the stats engine already wrote.
