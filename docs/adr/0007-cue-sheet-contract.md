# ADR 0007: The cue sheet is a versioned output contract

Status: Accepted (Oct 2026)

## Decision

PitchPulse's broadcast output is a **cue sheet**: numbered cues (`show`,
`update`, `retract`, `supersede`, `clear`) per audience, with layer, timing on
a monotonic `t_s`, priority and collision outcome, and text with its claims.
It has a JSON Schema (`backend/schema/cue.schema.json`, `$id
urn:pitchpulse:cue:1.0`), a TypeScript twin, and client rules that are
idempotent per `cue_id`. The in-app overlay follows the same cues.

## Why

Graphics systems need instructions, not prose: what goes on air, where, when
and when it must come off. VAR corrections need an explicit retract so a
ruled-out goal never airs late or out of order.

## Alternatives considered

- **Push cards only.** Rejected: no retract semantics, no timing contract.
- **A vendor graphics protocol.** Rejected: ties the product to one vendor;
  any system can map the cue sheet.

## Consequences

- Breaking changes bump `schema_version`; a test fails when the schema file is
  stale.
- The compiled sheet uses template text even when model text is on air
  (numbers identical).
