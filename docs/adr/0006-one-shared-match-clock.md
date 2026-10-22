# ADR 0006: One shared match clock per server

Status: Accepted (Oct 2026)

## Decision

A server plays one match on one clock (`api/session.py`). Every viewer, the
overlay, the cue sheet, Ask answers and MCP reads see the match at that
position. Play, pause, speed and seek are shared and rate limited. Per-viewer
state (persona, language, club, focus player, focus metric, catch-up) lives on
the connection, never on the clock.

## Why

A studio show has one clock: the overlay in OBS and the studio screen must
agree. Answers "as of the clock" can never read ahead, which is what makes
catch-up mode and spoiler-free answers safe.

## Alternatives considered

- **A clock per viewer.** Rejected for this build: N copies of the session and
  crew work, and the overlay could disagree with the studio.

## Consequences

- Seeking moves the match for everyone; the UI and docs/OBS.md say so.
- The app runs one replica (the session is in memory).
