# ADR 0001: Numbers come from the stats engine; a fact-checker gates every text

Status: Accepted (Oct 2026)

## Decision

Every number a viewer sees is computed by the deterministic stats engine
(`backend/src/matchmind/stats`) and attached to a moment as `facts`. No model
computes, estimates or rounds a number. Every text the crew shows (explanation,
card, recap, Ask answer, translation) passes `crew/fact_checker.py` against the
moment's facts; text that fails is never shown and a fact-checked template is
shown instead.

## Why

A broadcast graphic with a wrong number is worse than no graphic. A
deterministic engine is reproducible (same match, same numbers, every time),
testable and explainable (formulas in docs/METRICS.md). Gating text at one
point means the guarantee does not depend on which model, prompt or language
produced it.

## Alternatives considered

- **Let the model compute stats from raw events.** Rejected: not reproducible
  and not checkable.
- **Check only model text, trust templates.** Rejected: templates also run
  through the checker, which is how template bugs are caught (0 withheld of
  6,680 cards in docs/EVALUATION.md).
- **Model-graded groundedness only.** Kept as an optional, paid, owner-run
  extra (Foundry evaluators); not a gate.

## Consequences

- The guarantee is narrow and stated as such: numbers and squad names are
  checked; tone, causal wording and negation are not (docs/TRUST.md).
- Every sentence carries `claims` binding each number to a fact key and source
  event, which makes the audit drawer possible.
