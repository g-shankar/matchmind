# PitchPulse over MCP

PitchPulse serves its match intelligence as typed, read-only
[Model Context Protocol](https://modelcontextprotocol.io) tools, so any MCP
client (an assistant, an agent framework, a broadcaster's own tooling) can ask
the same questions the PitchPulse screens answer, and get the same numbers.

Everything here is about a **fictional, synthetic match**: invented clubs and
players, simulated events. Numbers come from the deterministic stats engine,
never from a model.

## What makes it trustworthy

- **One source for REST and MCP.** Every tool calls the same accessor as the
  REST route (`backend/src/matchmind/api/reads.py`); the read routes in `app.py` are
  one-line calls into that module. There is no second code path to drift.
- **Byte parity, tested.** `backend/tests/test_mcp.py` calls every tool through
  a real MCP client session over Streamable HTTP and checks that its JSON is
  byte-identical (canonical JSON: sorted keys, no spaces) to the REST response
  or the direct engine result for the same state. It runs on a small test match
  in both protocol eras (`2026-07-28` and the older initialize handshake) and on
  the real demo match parked at 70:00. A test fails if a new tool is registered
  without a parity case.
- **Typed both ways.** Inputs are closed pydantic models: enums, fixed-pattern
  ids and bounded numbers. No tool takes free text, so nothing a caller types
  can reach a model prompt. Outputs publish a JSON Schema
  (`structuredContent`), and the text block carries the same canonical JSON for
  clients that read text only.
- **Contract snapshot.** `backend/tests/snapshots/mcp_tools.json` holds every
  tool's name, description, annotations and input/output schema. Changing any of
  them fails the test until the snapshot is refreshed on purpose
  (`MATCHMIND_UPDATE_SNAPSHOTS=1 pytest tests/test_mcp.py -k snapshot`) and this
  page is updated.
- **Read-only.** Every tool is annotated `readOnlyHint: true`,
  `destructiveHint: false`. No tool plays, pauses, seeks or resets the shared
  match.

## Tools

All tools take JSON arguments and return one JSON object. Errors come back as a
tool error (`isError: true`) with one plain sentence, for example "We could not
find that moment." or "Check limit: the value is missing or not allowed."

| tool | inputs | output | same as |
|---|---|---|---|
| `get_match_snapshot` | none | the live match for the default viewer: clock, score, `state`, `control_chaos`, `playback`, `recent_cards`, `bookmarks`, `players`, `crew`, `languages`, `auto_eventing` | `GET /api/match/snapshot` |
| `list_moments` | `kind?` (goal, card, big_chance, better_option, unfound_run, momentum_swing, pressure_spell, milestone), `period?` (1, 2), `from_clock_s?`, `to_clock_s?` (0 to 10000), `played_only?` (default false), `limit?` (1 to 200, default 50) | `{ count, moments: Bookmark[] }`, earliest first | `GET /api/match/bookmarks`, filtered |
| `get_moment` | `moment_id` | `{ moment, explanation, replay, played }`: the moment's `facts` (the only numbers any agent may say about it), the analyst's `evidence`, its `source_event_ids`, and whether the live position has reached it | engine (the moment as spotted, before any persona voices it) |
| `get_overlay_card` | `moment_id`, `persona?` (casual, tactical, fantasy, player_spotlight), `language?` (en, es, fr, ar, ja, pt, de, hi, zh-Hans, sw, id, tr, ko), `favourite_team?` (club id) | `OverlayCard` | `GET /api/match/moment/{moment_id}` |
| `get_recap` | `persona?`, `language?` | `Recap` (so far, or the full match after full time) | `GET /api/match/recap` |
| `get_cue_sheet` | `persona?`, `language?`, `favourite_team?`, `since_seq?`, `limit?` (1 to 500, default 100) | `CueSheetPage`: numbered broadcast cues so far, including VAR retract and supersede (see CUE-SHEET.md) | `GET /api/match/cue-sheet` |
| `get_player_stats` | `player_id?` (fictional id like `NBR-9`; omit for everyone) | `{ players: PlayerStats[] }` | `GET /api/match/players` |
| `get_team_rosters` | none | `{ home, away }` with name, colours, formation, style and squad | `GET /api/teams` |
| `get_crew_status` | `trace_limit?` (0 to 100, default 20) | `{ status: CrewStatus, traces: CrewTrace[] }` | `GET /api/crew/status` + `GET /api/crew/trace` |
| `get_auto_eventing` | none | `AutoEventingStatus` (events detected from synthetic tracking, not video, scored against the simulator) | `GET /api/auto-eventing` |
| `get_recent_events` | `limit?` (1 to 100, default 20) | `{ count, events }`: the latest events played, oldest first, each with its stats engine `metrics`, in the `MATCH_TICK.event` shape | engine |
| `simulate_match` | `seed` (1 to 99999), `home?` (`NBR` or `HCY`) | `{ source: 'synthetic_simulator', match_id, seed, home, away, score_home, score_away, events, goals, final_state }` | engine (simulator + stats engine) |

Payload shapes are in [API-CONTRACT.md](API-CONTRACT.md); each tool's exact
JSON Schema is in its `outputSchema` (and in the snapshot file).

Notes:

- `list_moments` covers the whole match, like the REST bookmarks. Set
  `played_only: true` to stay at the live position (no spoilers).
- `get_overlay_card` and `get_recap` go through the studio crew. With the paid
  AI switch off (the default, `MATCHMIND_AI_ENABLED=false`) they are template
  text; with it on they share the REST routes' model budget and limits.
- `simulate_match` runs a fresh synthetic match in about half a second. Results
  are cached (64 most recent seeds); new seeds are limited to one simulation at
  a time and about one every two seconds for the whole server (bursts of 4),
  then "The match simulator is busy. Try again in a few seconds." A simulation
  over 10,000 events is refused.

### Planned tools (not built yet)

These are being built as separate features and will each be one
`register(ToolSpec(...))` line in `backend/src/matchmind/mcp/tools.py` once
their accessor lands. They are not listed by the server until then.

| tool | planned purpose |
|---|---|
| `get_metric_registry` | every metric with its definition, unit and source |
| `export_dataset` | a bundled synthetic match as events and stats |
| `audit_claims` | which numbers in crew text were checked against which facts |

## Attaching a client

### Over HTTP (the running app)

The match API serves MCP at **`/mcp`** on the same host and port, sharing the
live match everybody is watching:

- local: `http://localhost:8000/mcp` (start the app with `matchmind-api`)
- deployed: `https://<your Container Apps host>/mcp`

Transport: Streamable HTTP, stateless, JSON responses. Each tool call is one
`POST`; there is no session to keep and no long-lived stream, so it works behind
the Container Apps ingress with any number of replicas. In a client that takes a
server list:

```json
{
  "mcpServers": {
    "pitchpulse": { "type": "http", "url": "http://localhost:8000/mcp" }
  }
}
```

A raw call with `curl` (handshake-era clients send `mcp-protocol-version`):

```bash
curl -s http://localhost:8000/mcp \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -H 'mcp-protocol-version: 2025-06-18' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"list_moments","arguments":{"kind":"goal","played_only":true}}}'
```

From Python with the official SDK:

```python
import anyio
from mcp import Client

async def main():
    async with Client("http://localhost:8000/mcp") as client:
        moments = await client.call_tool("list_moments", {"kind": "goal"})
        first = moments.structured_content["moments"][0]["moment_id"]
        facts = await client.call_tool("get_moment", {"moment_id": first})
        card = await client.call_tool(
            "get_overlay_card", {"moment_id": first, "persona": "tactical", "language": "es"}
        )
        print(facts.structured_content["moment"]["facts"], card.structured_content["headline"])

anyio.run(main)
```

### Over stdio (a local process)

`matchmind-mcp` (or `python -m matchmind.mcp`) runs the same tools over stdio in
its own process. It loads the bundled demo match (or `MATCHMIND_MATCH_FILE`,
or `--match-file`) and parks it at full time, or at `--clock-s` seconds
(with `--period 1|2`). Nothing plays in that process. The crew runs in template
mode there whatever `MATCHMIND_AI_ENABLED` says, so a local client can never
spend on paid AI. Logs go to stderr.

```json
{
  "mcpServers": {
    "pitchpulse": { "command": "matchmind-mcp", "args": ["--clock-s", "4200", "--period", "2"] }
  }
}
```

## Security

- **No sign-in, on purpose.** Every tool is read-only and everything it returns
  is public synthetic data that the web app already shows to anyone. There are
  no accounts, no personal data and nothing to change. If a tool ever writes or
  reads private data, it needs sign-in first.
- **Origin and Host.** A browser `Origin` must be in
  `MATCHMIND_ALLOWED_ORIGINS` (or be this server's own origin when it serves the
  frontend), else 403. Requests without `Origin` (non-browser clients) are
  served. The `Host` header must be localhost, a host of an allowed or public
  origin (`MATCHMIND_PUBLIC_ORIGIN`), or one listed in
  `MATCHMIND_MCP_ALLOWED_HOSTS`, else 421. The Host check is only the SDK's
  DNS-rebinding guard; it is never used to trust a caller.
- **Limits.** A per-client-IP token bucket (about 3 POSTs a second, bursts of 30;
  the app's own limiter, separate from the REST buckets) answers 429 with
  `Retry-After`. Bodies over 16 KB get 413. JSON-RPC batches get 400 (one request
  per POST, so the rate limit counts every call). Only `POST` is served. String
  inputs are enums or fixed patterns with length caps; list sizes are capped.
- **No free text to a model.** No tool argument is free text, so prompt
  injection through a tool call has nowhere to go. Crew text is still
  fact-checked against the moment's facts as everywhere else.
- **Errors** are one plain sentence; a crash returns "Something went wrong on
  our side. Please try again." and the details stay in the server log.
- Responses carry `Cache-Control: no-store`.
- `MATCHMIND_MCP_ENABLED=false` removes the endpoint entirely.

## Adding a tool

1. Add (or reuse) an accessor in `backend/src/matchmind/api/reads.py`, and point
   the REST route at it if there is one.
2. Add input and output models in `backend/src/matchmind/mcp/models.py`
   (closed inputs: enums, patterns, bounds).
3. Register it in one line in `backend/src/matchmind/mcp/tools.py`.
4. Add its parity case in `backend/tests/test_mcp.py`, refresh the snapshot,
   and add its row above.
