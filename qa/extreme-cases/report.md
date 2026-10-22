# Extreme cases: pre-launch test round

Branch `feat/extreme-cases`, 22 Oct 2026. Local only: every load and probe ran
against a server started from this worktree on port 8820, with the bundled
synthetic demo match (MM-DEMO-001, invented clubs and players), the AI switch
off and no Azure resources. Scripts are in [`scripts/`](scripts/).

## Summary

We pushed PitchPulse to its limits: isolation between viewers, anything
admin-like, the offline demo and reconnects, 100 and 1,000 viewers, playback and
ingest queues, match-clock and wall-clock time, and odd feeds. There are no
accounts, so the account-heavy categories mostly do not apply (see below). The
existing controls held up well: per-IP caps and buckets, the seek throttle, the
live-feed validator, VAR retractions across seeks and UTC handling. We found two
High problems, both in shared resources. Viewers that stop reading could pin
about 800 MB in a 1 GiB container, and one address could toggle pause about 190
times a second for everyone. Both are fixed, each in its own commit with a test
that fails before the fix. Six more findings (two Medium, four Low) are fixed.
Four are left as they are, each with a reason: chiefly the per-replica
capacity, which is a deployment decision for the owner.

## Findings

Severity: High = one anonymous caller can degrade the service for everyone, or a
product promise breaks for all users. Medium = a promise breaks in a common
situation, or a ceiling that needs a decision. Low = a corner case that fails
safe or is cosmetic.

| ID | Severity | Area | What happens | Where | Repro | Status | Test |
|---|---|---|---|---|---|---|---|
| EC-1 | High | Volume / slow consumers | Each viewer that stops reading can queue 4 MB. 200 of them (the cap) pushed server RSS from 173 MB to 795 MB in 60 s. At 1x speed each one reaches the full 4 MB: about 1 GB in a 1 GiB container. The resulting out-of-memory restart drops every viewer | `backend/src/matchmind/api/app.py:329` (`Connection.send`) | `python3 scripts/slow_consumers.py --n 200 --seconds 70 --pid <pid>` | **Fixed** (939b2dd): all send queues share one byte budget (192 MB, `MATCHMIND_SEND_QUEUE_TOTAL_BYTES`). Once it is used up, viewers more than 256 KB behind are dropped with 1013; viewers that keep up are not. After: peak RSS 417 MB | `backend/tests/test_extreme_cases.py::test_ec1_stalled_viewers_cannot_pin_more_than_the_shared_budget`, `::test_ec1_bytes_go_back_to_the_budget_when_a_viewer_leaves` |
| EC-2 | High | Roles / shared clock | `toggle_pause` and `set_speed` had no throttle shared across viewers. 20 connections from one address sent 2,971 toggles in 15 s; every one went through and was broadcast to every viewer. The match played 35 s instead of 150 s. A double tap on pause also meant pause then resume (checklist item 1) | `backend/src/matchmind/api/app.py:600` (`Hub._claim_control`, new) | `python3 scripts/pause_storm.py --conns 20 --seconds 15` | **Fixed** (02b292a): pause and speed share one throttle, at most one change per 0.3 s (WebSocket and REST); asking for the speed already set does nothing. After: 50 of 2,972 accepted, and the bystander got 50 messages | `::test_ec2_pause_storm_changes_playback_once_per_window`, `::test_ec2_double_tap_on_pause_is_one_change`, `::test_ec2_rest_speed_shares_the_throttle_and_a_retry_is_a_no_op` |
| EC-3 | Medium | Isolation / reconnect | A catch-up viewer (spoilers off) saw the score on every connect and reconnect. The server's first snapshot is for the default audience. The reducer also took that snapshot's profile, which switched catch-up off on screen until the viewer's `set_view` came back | `frontend/src/state/matchStore.ts:174` (`catchUpGuard`, new); server side `app.py:1008` (`_serve` sends the default snapshot first) | WebSocket probe sending `set_view {spoilers:false}` on open: first message `INITIAL_SNAPSHOT` with `home_score: 2`, `profile.spoilers: true` | **Fixed** (e76a7de) in the web app. While catch-up is on, a default-audience snapshot or tick is scrubbed, cue messages are dropped, and only the viewer's own reveal turns catch-up off. Other WebSocket clients must still send `set_view` first (documented behaviour) | `frontend/src/state/matchStore.test.ts` "catch-up guard (extreme cases EC-3)" (4 tests) |
| EC-4 | Medium | Lifecycle / stale saved state | A club saved during another match, or a removed player, made the server refuse the whole `set_view`. `spoilers: false` never applied and the returning viewer saw the result (checklist item 3) | `backend/src/matchmind/api/app.py:1076` (`_set_view`) | `set_view` with `favourite_team: "OLD", spoilers: false`: only `ERROR`, no `PROFILE_CHANGED` | **Fixed** (96ef42d): the unknown club or player gets its message and is left out; the other fields apply | `::test_ec4_unknown_club_is_left_out_and_the_rest_of_the_view_applies`, `::test_ec4_only_an_unknown_club_changes_nothing` |
| EC-5 | Low | Time / live match start | Seek or reset on a live Event Hubs match that has only its `match_start` raised `max() arg is an empty sequence`. Result: REST 500, WebSocket "Something went wrong". No state was changed | `backend/src/matchmind/api/session.py:962` (`seek`) | `MatchSession([match_start], live_feed=...)` then `.reset()` | **Fixed** (447bc96) | `::test_ec5_reset_and_seek_work_on_a_live_match_with_only_its_kick_off` |
| EC-6 | Low | Roles / cross-site | `POST /api/ask` parsed any body as JSON. A `text/plain` form post (no CORS preflight) from any page got an answer, spending the visitor's Ask bucket (and model calls when the AI switch is on). Read-only and rate limited | `backend/src/matchmind/api/app.py:832` | `curl -X POST -H 'content-type: text/plain' -d '{"chip":"score"}' localhost:8820/api/ask` returned 200 | **Fixed** (7bd2070): JSON only, anything else gets 415 | `::test_ec6_ask_refuses_bodies_a_cross_site_form_could_send` |
| EC-7 | Low | Oddities / unicode names | An invented name typed with a combining accent (a + U+0301) was refused, while the same name with a single "á" passed | `backend/src/matchmind/ingest/roster.py:63` (`check_name`) | `check_name("Amá Kofi", ...)` | **Fixed** (b9c1b4d): names are NFC-normalised first. Thai and Devanagari names (spacing vowel marks) are still refused; left as is because this fails closed and they are not studio languages | `::test_ec7_invented_names_in_other_scripts_and_decomposed_accents_are_accepted` |
| EC-8 | Low | Offline demo | In the offline demo, a seek past full time (deep link `?t=99999`) or to period 3 jumped to full time and showed the result. The live server refuses these and nothing moves | `frontend/src/api/mockServer.ts:418` | `?demo=1&t=99999` | **Fixed** (facda82): the demo gives the same refusals | `frontend/src/api/mockServer.test.ts` "refuses a seek past full time or to a bad time, like the live server (EC-8)" |
| EC-9 | Medium | Volume / capacity | One replica tops out between 200 and 400 viewers on a 4-core machine (numbers below). With the cap raised to 1,000 the server collapses: snapshot p50 15 s, RSS 1.8 GB, health 9.6 s. The deployed container has 0.5 vCPU, and on one pinned core 200 viewers already gave REST p95 1.2 s | `backend/src/matchmind/api/app.py:59` (`MAX_CONNECTIONS` 200), `deployment/azure_bicep/main.bicep` (0.5 vCPU, 1 GiB, one replica) | `python3 scripts/ws_load.py --n 1000` with `MATCHMIND_MAX_CONNECTIONS=1000` or `=400` | **Left as is**. The default cap holds: 800 of 1,000 were refused cleanly. Changing the container size or the cap is a production config change for the owner. Recommendation: keep the cap at 200 with 1 vCPU, or lower it to about 100 at 0.5 vCPU; never raise it without a load run | none (measured) |
| EC-10 | Medium | Roles / shared clock | Even after EC-2, one address can keep the match mostly paused: one toggle per 0.3 s gave 54 s of play in 15 s at 1x instead of 150 s. Anyone can pause for everyone by design (shared clock, ADR 0006; "No sign-in" in the threat model's residual risks) | `backend/src/matchmind/api/session.py:922` | `scripts/pause_storm.py` after the fix | **Left as is**: a fix needs sign-in or an operator role, which is out of scope. The flood and its CPU cost are gone | covered by the EC-2 tests |
| EC-11 | Low | Lifecycle / VAR | `GET /api/match/moment/{id}` and MCP `get_card` return the card for a goal that VAR later ruled out, with no ruled-out marker | `backend/src/matchmind/api/session.py:562` | `curl localhost:8820/api/match/moment/goal-MM-DEMO-001-00817` | **Left as is**: a card records what was said at the time. Bookmarks (`ruled_out`) and the claim audit (`ruled_out_by`) carry the decision; marking the card would need spoiler-aware position logic | existing `test_corrections.py::test_audit_shows_the_retraction_both_ways` |
| EC-12 | Low | Slow consumers | A viewer that has stopped reading never receives our 1013 close frame because its buffers are full. The server's keepalive closes it with 1011 instead | uvicorn keepalive | `scripts/slow_consumers.py` (`server_close_codes`) | **Left as is**: unavoidable for a peer that does not read; its memory is freed either way | none |

## Volume: measured numbers

Machine: 4 vCPU Linux container, Python 3.13, uvicorn with the `websockets`
backend. The load generator ran on the same machine, so the numbers are
pessimistic. Default speed 10x, base rate 10: the expected delivery is 100
match seconds per wall second. Each viewer connects from its own address via
`X-Forwarded-For` (uvicorn accepts that header only from 127.0.0.1), except in
the "one IP" runs. Server started in `backend/` with
`PYTHONPATH=$PWD/src MATCHMIND_PORT=8820 python3 -m matchmind.api`.

Command: `python3 qa/extreme-cases/scripts/ws_load.py --n <N> --seconds 30 --pid <server pid>`

| Run | Accepted / refused | Snapshot p50 / p95 | Delivery (match s per s, min / p50) | `set_view` round trip p50 / max | REST health p50 / p95 | REST snapshot p50 / p95 | RSS before → peak |
|---|---|---|---|---|---|---|---|
| 5 viewers (smoke) | 5 / 0 | 23 / 34 ms | 100.7 / 100.9 | 0.9 / 2.7 ms | 3.3 / 6.2 ms | 5.9 / 10.2 ms | 173 → 176 MB |
| 100 viewers, before fixes | 100 / 0 | 251 / 368 ms | 101.5 / 101.7 | 1.6 / 460 ms | 12 / 170 ms | 8 / 284 ms | 176 → 204 MB |
| 100 viewers, after fixes | 100 / 0 | 243 / 356 ms | 101.0 / 101.3 | 7.1 / 149 ms | 20 / 122 ms | 7 / 173 ms | 175 → 205 MB |
| 1,000 attempted, cap 200, before | 200 / 800 | 1,440 / 1,713 ms | 103.9 / 104.2 | 241 / 1,375 ms | 208 / 999 ms | 572 / 1,912 ms | 204 → 261 MB |
| 1,000 attempted, cap 200, after | 200 / 800 | 1,131 / 1,380 ms | 101.7 / 102.1 | 267 / 1,417 ms | 102 / 1,270 ms | 365 / 1,907 ms | 205 → 295 MB |
| 25 from one IP (per-IP cap 20) | 20 / 5 | 78 / 146 ms | 102.4 / 102.6 | 1.1 / 6.6 ms | 3.6 / 17.7 ms | 13 / 37 ms | flat |
| 400 viewers, cap raised to 400 | 400 / 0 | 1,368 / 1,905 ms | **53.8 / 59.4** (falls behind) | 126 / 19,681 ms | 16 / 1,458 ms | **9,496** / 23,978 ms | 173 → 744 MB |
| 1,000 viewers, cap raised to 1,000 | 1,000 / 0 | **14,918** / 16,581 ms | collapses | 22 / 9,432 ms | **9,588** ms | timed out | 173 → **1,807 MB** |
| Server pinned to 1 core, 100 viewers | 100 / 0 | 179 / 275 ms | 101.0 / 101.1 | 17 / 82 ms | 5 / 78 ms | 6 / 154 ms | 173 → 202 MB |
| Server pinned to 1 core, 200 viewers | 200 / 0 | 383 / 571 ms | 99.5 / 101.4 | 165 / 1,357 ms | 70 / 1,194 ms | 152 / 1,374 ms | 202 → 250 MB |

The 1-core runs pinned the server with `taskset -c 0` and the loader with `taskset -c 1-3`.
Snapshot size: 33.6 KB (50.5 KB at full time). At 10x each viewer receives
about 44 messages and 110 KB a second.

**Slow consumers** (`python3 qa/extreme-cases/scripts/slow_consumers.py --n 200 --seconds 70 --pid <pid>`):
200 sockets that never read. Before EC-1: RSS 173 → 795 MB, still growing when
the match ended at about 60 s. After: 173 → 417 MB, flat from 42 s.

**Pause storm** (`python3 qa/extreme-cases/scripts/pause_storm.py --conns 20 --seconds 15`, 1x speed):
- Before EC-2: 2,971 toggles sent and all 2,971 accepted. The bystander
  received 2,971 playback messages and the match moved 35 s.
- After: 2,972 sent, 50 accepted, 2,922 refused with one plain message. The
  bystander received 50.

**REST, Ask and MCP bursts** (`python3 qa/extreme-cases/scripts/rest_burst.py --n 300`), 300 concurrent requests each:

| Route | One address | 300 addresses | One real address, 300 spoofed left `X-Forwarded-For` entries |
|---|---|---|---|
| `GET /api/match/recap` | 40 × 200, 260 × 429 | 300 × 200 (p50 503 ms) | 33 × 200, 267 × 429 |
| `POST /api/ask` | 22 × 200, 278 × 429 | 300 × 200 (p50 1,022 ms) | 31 × 200, 269 × 429 |
| `POST /mcp` (`get_match_snapshot`) | 36 × 200, 264 × 429 | 300 × 200 (p50 1,355 ms) | 35 × 200, 265 × 429 |

**Server restart with 50 viewers** (`python3 qa/extreme-cases/scripts/restart_check.py --n 50 --pid <pid>`):
all 50 closed with 1012 (service restart) within 0.01 s of SIGTERM, and the
process exited in 1.5 s. The web app reconnects and restates its profile with
`set_view`; EC-3 covers what it shows in between.

RSS does not drop when viewers leave, because Python keeps its memory arenas.
Later runs reuse that memory rather than grow: RSS stayed at 260 MB across the
next run.

## Bug-hunt checklist (CLAUDE.md section 5) against these flows

| Item | Applied to | Result |
|---|---|---|
| 1. Retries and double submits | Pause, speed, seek, reset, Ask, live feed redelivery | A double tap on pause counted as two changes: fixed (EC-2). Asking for the speed already set now does nothing. Seek and reset were already limited to one per 0.5 s. Live redelivery, and changed content under the same seq, were already refused (`test_live_source.py`) |
| 2. Snapshot vs live | Recaps, cue sheets, Ask answers | The recap cache is keyed by profile and position and cleared on seek. Ask copies the match as of the clock (`test_ask.py::test_answers_never_read_past_the_clock`). Held up |
| 3. Stale stored state | Saved viewer profile, cue cache, live append rollback | A stale saved club cancelled catch-up: fixed (EC-4). The cue sheet after a dropped live event was already guarded by a test |
| 4. Races | Connection slots, compile budget, `set_view` during a step, reconnect vs `set_view` | Slots are reserved before accept (held up). The reconnect snapshot raced ahead of the viewer's profile: fixed in the web app (EC-3) |
| 5. External events | Event Hubs fake: duplicates, out of order, same second, gaps, after match end | All held up (`test_live_source.py`). Kick-off-only live match: fixed (EC-5) |
| 6. Caching | `/api` routes, MCP, dataset downloads | `no-store` everywhere except the public synthetic downloads. Held up |
| 7. Whole flow | Stalled viewer → queue → memory → container; storm → broadcast → every viewer | Fixed (EC-1, EC-2) |

## Categories that do not apply, and why

- **Account isolation and roles:** there are no accounts, sign-in, tenants or
  roles. Instead we tested the nearest equivalents:
  - per-connection viewer state (persona, language, club, catch-up, cue sheet);
  - the shared controls anyone can use (pause, speed, seek, reset,
    `simulate_match`, dataset export).
- **100 and 1,000 accounts:** read as 100 and 1,000 concurrent viewers plus
  request bursts (above).
- **Offline sync of user data:** there is nothing to sync. The offline demo
  replays a recorded fixture in the browser. We checked its seek refusals
  (EC-8) and that reconnects restate the profile.
- **Money, payments, emails, uploads, database migrations, row-level security:**
  none exist.
- **DST, midnight and leap day in rate-limit windows:** every limiter and budget
  uses `time.monotonic`, so wall-clock changes cannot move them. Only the
  translator's sign-in token expiry uses wall time, which is correct for an
  epoch expiry. Dataset file names and zip dates are fixed, not read from the
  clock.

## What held up

- **Connection caps:** of 1,000 viewers attempted, 200 were accepted and 800
  refused with 1008, with no errors in the server log. Of 25 from one address,
  20 were accepted.
- **Per-IP buckets keyed on the last `X-Forwarded-For` entry:** 300 spoofed
  left-hand entries bought no fresh buckets on REST, Ask or MCP.
- **Seek throttle and seek edges:** each of these lands correctly or is refused
  in plain words:
  - 0, and 0 in period 2;
  - 2700 with and without a period;
  - first-half stoppage time (45+0:42) and past the end of a half;
  - the last event, and 9,999 s;
  - negative values, NaN and period 3.
- **VAR retraction across seeks:** seeking past an overturn never shows the goal
  as live, and playing through the overturn retracts it (`test_corrections.py`).
- **Feeds:**
  - duplicate, out-of-order, same-second, gapped and post-match events are handled;
  - period 3, clocks outside a half and naive timestamps are refused;
  - mixed DST offsets are ordered by instant;
  - kick-offs across midnight, new year, a leap day and both DST changes stay
    in UTC and in order (new tests).
- **Names:** bidi overrides, zero-width characters, markup and over-long names
  are refused. Real names written in full-width or mathematical letters are
  refused too, because names are folded before the banned-names check. Arabic,
  Chinese and accented names are accepted.
- **Empty match:** a feed with only `match_start` and `match_end` serves every
  route, Ask, seek and the WebSocket without an error.
- **Isolation:** one viewer's catch-up, language and persona never reach
  another (new test). MCP runs stateless, so there is no session to share.
- **Restart:** viewers are closed with 1012 at once and the process exits in
  1.5 s.

## Checks on the final commit

- Backend (`backend/`): `PYTHONPATH=$PWD/src python3 -m pytest -q`: 944 passed
  (915 at the start of the round); `ruff check .`: all checks passed; `ruff format --check .`:
  137 files already formatted
- Frontend (`frontend/`): `npm run typecheck`, `npm test` (19 files, 181 tests passed),
  `npm run build` (built)
