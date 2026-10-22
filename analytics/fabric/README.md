# PitchPulse on Microsoft Fabric

Two halves, both fed by the same synthetic match data:

* **Batch (Lakehouse):** the star schema written by `matchmind-lakehouse export`, loaded into Delta
  tables by `pitchpulse_lakehouse.ipynb`, ready for Power BI and for training on `decision_labels`.
* **Real time (Eventhouse):** `eventhouse.kql` ingests the Azure Event Hubs `match-events` stream
  and answers live questions (xG race, pressure, sprint leaders, better options).

Table descriptions and row counts: `docs/ANALYTICS.md`.

## Status: Not connected yet

| Item | State |
|---|---|
| Export code, Parquet and CSV output, labels, tests | Implemented, tested offline |
| `pitchpulse_lakehouse.ipynb` | Written. **Not run in Fabric yet** (no workspace exists) |
| `eventhouse.kql` | Written. **Not run against an Eventhouse yet** |
| Fabric capacity, workspace, Lakehouse, Eventhouse | **Not created.** Owner step |
| Event Hubs to Eventhouse connection | **Not connected yet.** Owner step |
| Live enriched stream (stats engine to a second event hub) | **Planned, not built.** The enriched table is loaded from a file |
| Power BI semantic model and report | **Not built.** Suggested relationships below |

Nothing here runs unless the owner runs it. No Azure or Fabric credentials are in the repo.

## 1. Make the files (free, offline)

```
cd backend
pip install -e ".[analytics]"              # pyarrow gives Parquet; without it you get CSV
matchmind-lakehouse export --input data/matches --seeds 50 --with-labels --out ../data/lakehouse
matchmind-lakehouse enrich --input data/matches --out ../data/enriched.jsonl
```

`--input data/matches --seeds 50` is the bundled 5 matches plus 50 new deterministic ones (the same
seed always gives the same match). Output layout: `Tables/<table>/part-0.parquet` and `_schema.json`
per table, plus `_manifest.json`.

## 2. Lakehouse (owner-run)

1. **Capacity.** Start a Fabric trial (free for 60 days; check the current terms) or use an existing capacity. See *Costs* below.
2. **Workspace and Lakehouse.** Create a workspace on that capacity, then a Lakehouse (for example
   `pitchpulse`).
3. **Upload.** In the Lakehouse, open Files, create a folder `pitchpulse`, and upload the contents of
   `data/lakehouse` (the `Tables` folder and `_manifest.json`) into it. Use OneLake file explorer or
   the Upload folder button.
4. **Notebook.** Import `pitchpulse_lakehouse.ipynb` into the workspace, attach the Lakehouse as the
   default, and run all cells. It creates Delta tables `pp_<table>` and five views
   (`pp_vw_match_summary`, `pp_vw_xg_timeline`, `pp_vw_pressure_5min`, `pp_vw_better_options`,
   `pp_vw_player_leaderboard`). Spark views may not show in the SQL analytics endpoint; if Power BI
   needs them, recreate them there as T-SQL views or build the measures in the semantic model.
5. **Power BI (optional).** Create a semantic model on the `pp_*` tables with these relationships
   (many to one): every fact's `match_id` to `pp_matches`; `team_id` to `pp_teams`; `player_id` to
   `pp_players`; `moments`, `better_options` and `decision_labels` `event_id` to `pp_events`. Good
   first pages: match summary, xG timeline, pressure by five minutes, better options, player
   leaderboard. Direct Lake works on Delta tables in the Lakehouse.

## 3. Real-time (owner-run)

1. Create an **Eventhouse** and a KQL database in the workspace (same trial capacity).
2. Open the KQL database query editor, paste `eventhouse.kql` and run the first section (tables,
   mappings, batching, retention). Each block runs on its own.
3. **Raw stream.** Get data, Event Hubs: point at the `match-events` hub deployed by
   `deployment/azure_bicep/main.bicep`, data format JSON, table `MatchEvents`, mapping
   `MatchEventsMapping`. Check two things before relying on this:
   * The template creates the namespace on the **Basic** tier with local (key) authentication
     **off**. Basic has only the `$Default` consumer group, and Fabric connectors may expect a key.
     If the connector cannot use Microsoft Entra ID, the options are a Standard tier namespace
     (a paid change, owner decision) or sending the simulator's events to a Fabric Eventstream
     custom endpoint instead.
   * The identity Fabric uses needs the Event Hubs Data Receiver role on the hub.
4. Start the stream: `matchmind-sim live --sink eventhub --speed 60` (set `EVENTHUB_*` as in the
   simulator docs; sign in with `az login`, no keys).
5. **Enriched table.** Get data, Local file: upload `enriched.jsonl`, table `MatchEventsEnriched`,
   mapping `MatchEventsEnrichedMapping`. This is a file load, not a live feed: the xG race,
   pressure windows, sprint leaders and better-option queries read this table. Streaming it live
   would need the stats engine to publish to a second event hub; that is planned, not built.
6. Run the queries in section 2 of the file. Pin them to a Real-Time Dashboard if wanted.

## Costs, honestly

* Everything in this repo (export, labels, tests) is free and offline.
* A Fabric trial capacity is free for 60 days and has limits (smaller than production capacities,
  and it ends). After it, Fabric needs a paid capacity (F SKUs, billed per hour while running; the
  smallest, F2, was roughly US$0.36 an hour at the time of writing: check current pricing) or Power
  BI Premium. A paused capacity does not bill compute, but OneLake storage still does.
* The Event Hubs Basic namespace already in the template has a small hourly charge; a Standard tier
  costs more.
* Pausing or deleting the capacity after the judging window is the owner's call.

## Files

| File | What it is |
|---|---|
| `pitchpulse_lakehouse.ipynb` | PySpark notebook: Parquet or CSV to Delta tables, five views, row-count check |
| `eventhouse.kql` | Tables, JSON mappings, ingestion and retention policies, five real-time queries |
