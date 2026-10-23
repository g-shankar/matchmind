# ADR 0004: Agent Framework orchestration must match the in-process crew exactly

Status: Accepted (Oct 2026). The Agent Framework orchestrator is a future
enterprise extension, off by default; the in-process crew is the one that runs
([HACKATHON-BRIEF.md](../HACKATHON-BRIEF.md#beyond-the-brief)).

## Decision

The crew can be chained by Microsoft Agent Framework workflows
(`MATCHMIND_ORCHESTRATOR=agent_framework`, `crew/workflow.py`) or by the
default in-process orchestrator. Both run the same agent step functions, and
parity tests (`backend/tests/test_agent_framework.py`) replay the demo match
through both and require identical cards, in template mode and in a model mode
with injected rejections and failures.

## Why

Orchestration is plumbing; it must not change what a viewer sees. Parity
tests make the framework switch safe to turn on and keep the fact-checker in
the same process as the call it gates.

## Alternatives considered

- **Rewrite the crew natively in the framework.** Rejected: two
  implementations would drift.
- **Run the Fact-checker or Spotter as hosted agents.** Rejected: they are
  deterministic code on purpose (ADR 0001).

## Consequences

- The framework path is free and local but off by default; it needs the
  optional `agent-framework` extra.
