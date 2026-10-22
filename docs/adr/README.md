# Architecture decision records

Short records of the decisions that shape PitchPulse: what we decided, why, and
what we turned down. A decision that changes gets a new record that supersedes
the old one; old records are not rewritten.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-deterministic-numbers-and-fact-checker.md) | Numbers come from a deterministic stats engine; a fact-checker gates every text | Accepted |
| [0002](0002-templates-first-ai-off-by-default.md) | Templates first; paid AI off by default | Accepted |
| [0003](0003-mcp-read-only-stateless.md) | MCP server is read-only and stateless | Accepted |
| [0004](0004-agent-framework-parity.md) | Agent Framework orchestration must match the in-process crew exactly | Accepted |
| [0005](0005-auto-eventing-from-synthetic-tracking.md) | Auto-eventing from synthetic tracking, not video | Accepted |
| [0006](0006-one-shared-match-clock.md) | One shared match clock per server | Accepted, amended by 0008 |
| [0007](0007-cue-sheet-contract.md) | The cue sheet is a versioned output contract | Accepted |
| [0008](0008-first-visit-on-the-shared-clock.md) | A first visit on the shared clock: 1x default, idle rewind, jumps that land | Accepted |
