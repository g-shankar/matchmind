# ADR 0005: Auto-eventing from synthetic tracking, not video

Status: Accepted (Oct 2026)

## Decision

PitchPulse detects events (passes, shots, clearances, tackles, interceptions,
recoveries, pressure) from a 25 Hz synthetic tracking feed rendered from the
simulator, and scores the detector against the simulator's own events on
held-out seeds. A pixel path renders top-down synthetic frames and recovers
positions with classical image processing (numpy, no trained model). Every
surface says "detected from synthetic tracking, not video".

## Why

We have no licensed footage and the rules forbid real data. A tracking-based
detector with an honest, held-out benchmark shows the method without
pretending to be a video model.

## Alternatives considered

- **A pretrained video detector on broadcast footage.** Rejected: no footage we
  may use, and presenting it as live would be a fake feature.
- **No auto-eventing.** Rejected: the benchmark is useful evidence of the
  method's limits.

## Consequences

- The benchmark is circular by construction (truth and tracking share the
  simulator's assumptions); docs/AUTO-EVENTING.md says so first.
- Real video input is planned, not built.
