# Crew-shape eval

`python -I evals/crew_skills_eval.py` scores ten fixed examples on the demo match
(34 checks) for the current crew and for each "fold an agent into a skill" variant,
one at a time, stopping at the first variant that makes any example worse. A
scripted model stands in for the paid one, so it runs free and offline; it tests
the crew's wiring and recovery, not the model's prose. Results go to `last_run.json`.

Last run (26 Oct 2026):

| Variant | Score | Worse on |
|---|---|---|
| Current crew | 34/34 | - |
| Analyst folded into the Commentator (one call per card) | 32/34 | 5 (invented number also kills the why), 7 (one outage takes out both texts) |
| Fact-checker as a prompt skill | not run | stopped after the first regression |
