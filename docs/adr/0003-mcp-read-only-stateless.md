# ADR 0003: The MCP server is read-only and stateless

Status: Accepted (Oct 2026)

## Decision

PitchPulse serves its match intelligence as Model Context Protocol tools at
`/mcp` (Streamable HTTP, stateless, JSON responses) and over stdio
(`matchmind-mcp`). Every tool is annotated read-only and none can play, pause,
seek or reset the shared match. Each tool calls the same accessor as its REST
route (`api/reads.py`), and a test checks byte parity between the two.

## Why

Agents and broadcaster tooling should get exactly the numbers the screens
show, without a second code path that could drift. Stateless HTTP works behind
the Container Apps ingress with no session affinity. Read-only means there is
nothing to authorise: everything returned is public synthetic data.

## Alternatives considered

- **Write tools (seek, play).** Rejected: anyone could move the clock for every
  viewer; would need sign-in first.
- **Stateful sessions with server-sent streams.** Rejected: harder to scale and
  to rate-limit; clients can poll the cue sheet instead.

## Consequences

- `ask_studio` is the one tool that takes free text; it goes through the same
  guard and parser as `POST /api/ask` (docs/ASK.md).
- `export_dataset` and `audit_claims` tools are planned; the data is reachable
  over REST today.
