# The PitchPulse dataset

Everything PitchPulse plays is **synthetic**: matches produced by our own match
engine, with two invented clubs and invented players. There is no real club,
player, competition or broadcaster data anywhere in it. This page covers what
is in the dataset, how it is made, where it falls short of real football, how
to download it, and how to play your own synthetic feed through PitchPulse.

Every field, type, unit, enum and the measured distributions are in
[`DATA-DICTIONARY.md`](DATA-DICTIONARY.md) (generated from the schema and the
data; a test fails when it is out of date).

## What is in it

| set | match ids | how many | scenario |
|---|---|---|---|
| Bundled | `MM-DEMO-001` | 1 | `demo_storyline`: the scripted demo (home club 2-0 up, red card 52', pressure 60-75', away win 3-2 in stoppage time, two missed square balls, an unfound run) |
| Bundled | `MM-SYN-001` .. `MM-SYN-004` | 4 | `chance_model`: unscripted; every goal comes from the engine's chance model |
| Seeded on request | `MM-GEN-01000` .. `MM-GEN-01019` (API), any `MM-GEN-<seed>` (CLI) | 20 / unlimited | `chance_model_with_beats`: chance model plus three decision beats ("should he have passed?" shots, unfound runs) |

The bundled matches live in `backend/data/matches/*.jsonl` with a
`manifest.json` (seed, clubs, score, event count). Each match has about 2,100
events. Each line is one event in the schema in `backend/schema/event.schema.json`
(the pydantic model `backend/src/matchmind/schema/events.py`).

Seeds: the bundled set is `matchmind-sim dataset --seed 100` (demo seed 100,
unscripted seeds 101-104); seeded matches use the generator the Lakehouse export
uses (`analytics/sources.py`). Same scenario and seed always give byte-identical
events, and CI regenerates the bundled set and diffs it byte for byte.

## How it is generated

`backend/src/matchmind/simulator/engine.py` walks a possession-chain model.
Whoever has the ball picks an action (pass, carry, dribble, cross, shot,
clearance or a run in behind) with probabilities that depend on the pitch
zone, pressure and the match state. Outfield players hold a simple team shape
around the ball, so shots can carry a freeze frame of everyone near the box
and runs carry 3 s of positions (every 0.5 s). A script (`scripts/demo.yaml`)
can force story moments (goals, a red card, a pressure spell, missed options);
those events carry `scripted:*` labels so they stay separable from natural
play. Labels are ground truth for evaluation; the stats engine strips them
before anything reaches the studio crew.

The 25 Hz tracking sample is rendered from the events by the auto-eventing
renderer (`autoevent/tracking.py`): the ball moves in straight lines at the
event's speed, players follow the team-shape model, and measurement noise
(about 5 cm) and short ball drop-outs are added. It is synthetic tracking, not
video, and nothing in PitchPulse presents it as video.

## Realism limits (read before drawing conclusions)

- **Not calibrated on real matches.** The action probabilities and the
  chance model are hand-set so matches look and feel plausible. Rates in the
  data (pass completion around 80%, 28-37 shots a match, shot outcomes) are
  properties of this engine, not estimates of real football. The measured
  numbers are in the data dictionary.
- **Two clubs, eleven players each.** No substitutions, injuries, transfers
  or squad rotation. Strength differs by a small constant per club.
- **Missing match detail.** No set-piece events (corners, free kicks, throw-ins,
  penalties), no offside, no goalkeeper distribution types, no aerial duels, no
  ball height. Fouls are simple; yellow cards are random (never a second one
  for the same player) and red cards only happen when a script asks for one.
- **Positions are a model.** Freeze frames and run tracking come from a team
  shape, not physics or real movement. Off-ball positions are only stored for
  shots (freeze frames) and runs (3 s); the 25 Hz sample is rendered after the
  fact.
- **Scripted beats are visible.** The demo match's storyline is forced by its
  script; seeded matches add three decision beats each, so "better option"
  labels have enough positives for evaluation. Use the `scripted:*` labels to
  separate them.
- **Clock and wall time are derived.** `ts` is kick-off plus elapsed time with
  a fixed 15-minute half-time; stoppage time is drawn at random per half.

## Download it

### API (public, read-only)

| route | returns |
|---|---|
| `GET /api/dataset` | every downloadable match with kind, scenario, seed, clubs (and score and event count for bundled matches), the formats and the seeded range |
| `GET /api/dataset/export?match_id=MM-DEMO-001&format=jsonl` | the events exactly as bundled (byte for byte) |
| `GET /api/dataset/export?match_id=MM-DEMO-001&format=csv` | the events as a flat table (nested arrays left out) |
| `GET /api/dataset/export?match_id=MM-DEMO-001&format=zip` | README, `match.json`, `events.jsonl`, `events.csv`, `rosters.csv`, `event.schema.json`, `DATA-DICTIONARY.md` |
| `...&format=zip&tracking_period=1&tracking_from=600&tracking_to=630` | the same plus `tracking.csv`: 25 Hz synthetic tracking for one window of at most 60 s |

Limits: `match_id` must be one of the listed ids (an allow-list; no file path
is ever built from the request); about one export every 5 s per client IP
(bursts of 6); at most two exports are built at once (429 with plain words
otherwise); each export is a few MB at most. Responses are streamed with
`Content-Disposition: attachment` and `Cache-Control: public, max-age=3600`
(the data is synthetic and the same for everyone); errors stay `no-store`.

### CLI

```bash
cd backend
matchmind-sim export --match MM-DEMO-001 --format zip --out data/export
matchmind-sim export --all --format all --out data/export          # every bundled match, all formats
matchmind-sim export --seed 1234 --tracking 2:4000-4030 --out data/export
matchmind-sim export --all --lakehouse --out data/export          # plus the Lakehouse star schema
matchmind-sim dictionary                                           # regenerate docs/DATA-DICTIONARY.md
```

`--lakehouse` reuses the analytics package's star schema writer (the same as
`matchmind-lakehouse export`, see [ANALYTICS.md](ANALYTICS.md)) for the
exported matches.

## Play your own synthetic feed

`matchmind.ingest` takes an external feed, checks it strictly and plays it
through the same session pipeline as the bundled match (stats engine, crew,
bookmarks, recap). Two formats:

1. **JSON lines in our event schema** (`.jsonl`), exactly like
   `backend/data/matches/*.jsonl`.
2. **Generic CSV** (`.csv`) with a mapping file: one row per on-ball action,
   columns `type,minute,second,team,player,x,y,end_x,end_y,outcome[,period]`
   (rename any of them in the mapping). The adapter adds what a CSV does not
   carry: match_start with line-ups, period markers, match_end and scores,
   possession ids and the receiver of a completed pass. See the docstring of
   `backend/src/matchmind/ingest/csv_feed.py` for every mapping key.

Clubs other than the two bundled ones need a **roster file** of invented names
(`data/examples/roster.yaml`). A complete worked example lives in
`backend/data/examples` (`feed.csv`, `mapping.yaml`, `roster.yaml`):

```bash
cd backend
matchmind-ingest validate data/examples/feed.csv --mapping data/examples/mapping.yaml --roster data/examples/roster.yaml
matchmind-ingest play     data/examples/feed.csv --mapping data/examples/mapping.yaml --roster data/examples/roster.yaml
matchmind-ingest play     data/examples/feed.csv --mapping data/examples/mapping.yaml --roster data/examples/roster.yaml --serve

# or point the app at it
MATCHMIND_MATCH_FILE=data/examples/feed.csv MATCHMIND_FEED_MAPPING=data/examples/mapping.yaml \
MATCHMIND_ROSTER_FILE=data/examples/roster.yaml matchmind-api
```

`play` uses the template crew only (it never calls a paid model) and prints the
score, the bookmarks and the recap headline.

### What is checked

Every door (JSON file, CSV, live stream) ends in the same checks
(`ingest/validate.py`), and a feed that fails any of them is refused with
plain words and the line or row number:

- **Size caps**: 20 MB per file, 256 KB per line, 10,000 events, 64 KB roster,
  16 KB mapping, 64 characters per CSV cell, 16 details keys of at most 80
  characters, 8 labels, 22 players per frame.
- **Shape**: exactly one match_start first (home, away and line-ups), match_end
  last, one match id, seq strictly increasing, unique event ids, types and
  enums from the schema, timestamps with a time zone, finite numbers, speeds at
  most 60 m/s (ball) and 15 m/s (player), coordinates on the 105 x 68 pitch.
- **Clock**: `(period, clock_s)` never runs backwards (many events in the same
  second are fine), clocks stay inside their half (first-half stoppage at most
  30 minutes), `ts` never runs backwards.
- **People**: clubs are bundled or in the roster; line-up players match the
  roster by shirt number and name; every player reference (actor, receiver,
  pressure, freeze frames, tracking, `*_id` details) is in the line-up and in
  the right team.
- **No real names**: club, player, style and details text is checked against
  the fact-checker's banned list (real clubs, players, managers, stadiums,
  competitions and broadcasters, accents folded). Names must look like names.
- **Untrusted text**: no control characters; details keys are lower_snake_case.

Ids are normalised: match and club ids upper-cased, player ids rewritten to
`<team>-<number>` (a feed may use its own ids in the line-up), event ids to
`<match_id>-<seq>`. On the bundled matches this changes nothing (tested).

### Why there is no upload endpoint

The public app takes no files. An unauthenticated upload route would be a
storage and abuse surface (our rules require type and size checks, private
storage, signed short-lived links and storage-side caps for any upload) and
would let anyone replace the match every viewer is watching. A feed is
therefore something the operator puts on disk and plays with
`matchmind-ingest` or `MATCHMIND_MATCH_FILE`. If uploads are ever needed they
will come with sign-in and those controls.

## Live mode: Event Hubs consumer

By default the API replays a file. With `MATCHMIND_SOURCE=eventhubs` it
consumes the live stream the simulator publishes
(`matchmind-sim live --sink eventhub`, partitioned by match id):

- **Keyless**: `EVENTHUB_FULLY_QUALIFIED_NAMESPACE` and `EVENTHUB_NAME`,
  signed in with `DefaultAzureCredential` (managed identity in Azure,
  `az login` locally). There is no connection-string path in the consumer.
  Needs the `azure` extra; switched on without these settings, the app stops at
  start-up with a message naming what is missing.
- **Position**: reads every partition from the latest position (`@latest`;
  `MATCHMIND_EVENTHUBS_START=-1` for the earliest retained event) and follows one
  match: `MATCHMIND_EVENTHUBS_MATCH_ID`, or the first match_start it sees. If
  no match_start arrives within `MATCHMIND_EVENTHUBS_WAIT_S` (default 90 s), the
  app replays the match file instead and `GET /api/source` says so.
- **Same checks** as a file, one event at a time, plus delivery rules
  (`ingest/stream.py`): redeliveries (same seq, same content) are dropped and
  counted; the same seq with different content is refused (the first version
  stands); out-of-order events wait in a 256-event reorder buffer and are
  released in seq order; a gap that does not fill in 5 s is skipped and
  counted; events that overtake their own match_start are kept; other matches
  and anything after match_end are ignored.
- **Backpressure**: checked events wait in a bounded queue (2,000). When the
  session is behind, the consumer's callback blocks, so Event Hubs stops
  pulling until there is room; nothing is dropped for being slow.
- **Live session**: the session grows as events arrive (bookmarks and seek
  checkpoints included) and ends only at match_end, or at the last event
  received if the stream stops. Seeking past the live edge says "That part of
  the match has not been played yet."
- `GET /api/source` reports the source and the stream counters (received,
  accepted, duplicates, conflicts, reordered, skipped, rejected, queued,
  backpressure waits).

In Azure the switch is the Bicep parameter `eventHubsSource` (repo variable
`MATCHMIND_EVENTHUBS_SOURCE`); only then does the app identity get the Azure
Event Hubs Data Receiver role (setup/owner-todo.md). Tests run the whole path
against a fake consumer with duplicates, reordering and a late join; the
consumer has not been run against a live namespace from this repository's
tests.
