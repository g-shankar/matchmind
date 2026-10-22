# The trust layer

What PitchPulse checks before a sentence reaches a viewer, what it does not
check, and how anyone can inspect the evidence for one moment.

In one line: **numeric-claim validation with deterministic fallback.** Every
number and squad name in shown text is matched to a fact from the stats
engine; text that fails is never shown, and a fact-checked template is shown
instead. This is a narrow, mechanical guarantee. It is not a guarantee that
every sentence is true: tone, causal wording and negation are not
machine-checked (see [What is not checked](#what-is-not-checked)).

Code: `backend/src/matchmind/crew/fact_checker.py` (checks),
`crew/claims.py` (claims and parity), `crew/audit.py` (the audit),
`crew/telemetry.py` (service levels).

## What is checked

Every text the crew shows (Analyst explanation, Commentator headline and body,
recap, metric alert, and every translation into a world language) goes through
the fact-checker against the moment's own facts. A failure means the text is
not shown: model text falls back to the template, a failed translation falls
back to English, and a template that fails is withheld (none does today).

| Check | Rejects | Where |
|---|---|---|
| Numbers | Any number (digits in any script, decimals, percentages, "3.1x") that is not a fact, within printing tolerance | All text |
| Number words | Spelled-out numbers and count words ("three", "trois", "ثلاثة", "三本", "hat-trick") that are not facts | Model text only |
| Real names | Real clubs, players, managers, grounds, competitions, broadcasters (accent-folded) | All text |
| Squad names | A squad player's or club's name that is not in the moment's facts (a true number pinned on the wrong player) | All text |
| Units | A number printed with a unit that does not match the fact it equals: "16 km/h" when 16 is the pass distance in metres. Units read: km/h, km, m, %, x, xG, xA, xT, minutes, in all five studio languages (時速 for speed in Japanese) | All text |
| Range | A percentage over 100 | All text |
| Attribution | A per-club number (score, xG, shots) printed right after one club's name that is the other club's value ("Harbour City 2" when Harbour City has 1); a scoreline "A 1-2 B" in the wrong order for the two clubs named | All text |
| Comparison | "N more than M" with N not above M, "N less than M" with N not below M, and a multiplier read as "more" or "better" that is not above 1 | English, Spanish, French |
| Length | Headline words or characters, body sentences, paragraph length (CJK-aware) | All text |

## Claims: every sentence tied to its evidence

Every `OverlayCard` and `Recap` now carries `claims`: one entry per sentence of
its headline, body and explanation (recaps: title, headline, paragraphs and
key-moment lines). Sentences are split for Latin, Arabic (؟) and Japanese
(。！？) punctuation; decimal points and "(est.)" never end a sentence.

| Field | Meaning |
|---|---|
| `sentence`, `field` | The sentence as shown, and where it is |
| `fact_keys` | The facts the sentence states |
| `numbers` | Every number as printed |
| `bindings` | Each number and name, the fact key it matched, its value and unit, and the squad player or club id for names |
| `source_event_ids` | The events the facts came from (recap goal lines point at the goal events; key-moment lines at their moment's events) |
| `check` | `verified_numeric`: every number in it is a fact. `verified_name`: no numbers, and its names are facts. `unverified_text`: nothing to check, or a check failed |
| `reason` | Why, in words. Always says that wording is not machine-checked |
| `origin` | `template`: the fact keys come from the template's own placeholders, so "3.1x" is known to be `times_better`. `matched`: model or translated text, matched to facts by value (the unit printed next to a number picks between equal values) |

### Example: "Should he have passed?" at 34:16 of the demo match

Moment `better_option-MM-DEMO-001-00717`, source event `MM-DEMO-001-00717`.
Facts include `shot_xg` 0.05, `alt_xg` 0.24, `pass_success_pct` 83,
`alt_value` 0.2, `times_better` 4.0, `pass_distance_m` 16.

Tactical, English:

| Field | Sentence | Bound to | Check |
|---|---|---|---|
| headline | Shot selection: Asante ignored Kerrigan | Asante -> `player_short`, Kerrigan -> `teammate_short` | `verified_name` |
| body | Shot at 0.05 xG; the 16 m pass had 83% success odds and a 0.24 xG chance behind it. | 0.05 -> `shot_xg`, 16 -> `pass_distance_m`, 83 -> `pass_success_pct`, 0.24 -> `alt_xg` | `verified_numeric` |
| body | Expected value 0.2, 4x the shot. | 0.2 -> `alt_value`, 4 -> `times_better` | `verified_numeric` |
| why | The pass to Kerrigan was worth 0.2 expected goals against 0.05 for the shot, 4x more. | Kerrigan -> `teammate_short`, 0.2 -> `alt_value`, 0.05 -> `shot_xg`, 4 -> `times_better` | `verified_numeric` |

Casual, Japanese:

| Field | Sentence | Bound to | Check |
|---|---|---|---|
| headline | Asanteはパスすべきだった？ | Asante -> `player_short` | `verified_name` |
| body | Asanteはシュートを選びましたが、Kerriganがフリーでした。 | Asante -> `player_short`, Kerrigan -> `teammate_short` | `verified_name` |
| body | パスの価値はシュートの4倍でした。 | 4 -> `times_better` | `verified_numeric` |

`verified_numeric` on the "why" sentence means its four numbers are the
engine's. It does not mean the machine checked that the pass *was* the better
choice: that judgement is the stats engine's model (docs/METRICS.md), and the
wording around it is not verified.

## Cross-persona and cross-language parity

One moment is voiced for 4 personas x 5 studio languages (and, with the
translator on, world languages). `fact_parity` checks that those renderings
tell the same story:

1. Every rendering uses only the moment's facts (no claim failed a check).
2. Every rendering states the moment's anchor: who or what it is about (for a
   goal the scorer or the club; for a pressure spell the club; for half-time
   both scores).
3. For each persona, every language states the same **key facts** as English.
   Template text is compared by template keys; model and translated text by
   the numbers and names printed.

Key facts per moment kind (`claims.KEY_FACTS`):

| Kind | Key facts |
|---|---|
| goal | scorer, club, home score, away score |
| correction (VAR) | scorer of the ruled-out goal, corrected home and away score, time of the ruled-out goal |
| card | player, card colour |
| big chance | player, xG |
| better option | shooter, teammate, pass vs shot multiplier |
| unfound run | runner, projected xG |
| momentum swing | club, momentum change |
| pressure spell | club, pressure index |
| speed burst | player, speed |
| rocket shot | player, shot speed |
| distance milestone | player, distance |
| hard pass | player, pass difficulty |
| kick-off | both clubs |
| half-time, full-time | both clubs, both scores |
| player milestone | player, appearance number |

A persona may leave a key fact out (fantasy goal cards do not repeat the
score); parity requires every language of that persona to leave out the same
ones.

**Result (template mode, 22 Oct 2026):** a test sweeps every moment of the 5
bundled matches x 4 personas x 5 studio languages
(`tests/test_trust.py::test_parity_holds_for_every_moment_persona_and_studio_language`).
358 of 358 moments pass parity; 7,160 of 7,160 renderings were shown (0
withheld). Their 27,119 sentence claims: 19,754 `verified_numeric`, 4,921
`verified_name`, 2,444 `unverified_text` (sentences with no number or name,
such as "Something may have to give."), and 0 failed checks. Tests also show
parity failing when a language drops a key fact, loses the anchor, or prints a
number outside the facts.

## The moment audit

`GET /api/match/moment/{moment_id}/audit` returns, for one moment: its facts
and source events, the Analyst's explanation and evidence rows, every
rendering's text, claims and fact-check outcome, the parity result, the
crew's trace steps for that moment, and the list of things not checked.

- Renderings marked `template_sweep` are voiced for the audit by the
  template-only crew the session already keeps for bookmarks: **no model call
  and no translation can happen**, whatever the AI switch says (tested).
- Renderings marked `live` are cards the live crew already made for viewers
  (model text or translations included), read from its cache, at most 16.
- Rate limited like the moment route; the response is bounded (about 65 KB
  for a 20-rendering moment) and never cached (`no-store`).

## Service levels in `/api/crew/status`

`CrewStatus.health` (rolling window of the last 256 steps per agent, the last
256 fact-check verdicts, and the last 60 s of moments; memory is bounded):

| Field | Meaning |
|---|---|
| `latency[]` | Per agent: `samples`, `p50_ms`, `p95_ms`, `max_ms` (nearest-rank percentiles) |
| `model_steps`, `fallback_steps`, `fallback_rate` | Analyst, Commentator and recap steps in the window, how many fell back to a template, and the ratio |
| `checks`, `rejected_checks`, `rejection_rate` | Fact-check verdicts in the window, how many rejected, and the ratio |
| `moments_per_min` | Moments spotted in the last 60 s of wall clock |

Rates are `null` when there is nothing to divide by, and the counts always sit
next to them. In template mode the fallback rate is 0 because no model is
asked; that is not evidence about model quality.

## What is not checked

Said plainly, because a clean checker report can still hide these:

- **Tone, wording and causal claims.** "Control has changed hands" or "so they
  have to adjust" are not verified. Every claim's `reason` says so.
- **Negation.** "Kerrigan did not score" and "Kerrigan scored" read the same to
  the checker (a test pins this limit).
- **Player attribution.** A player's number next to another player's name is
  not caught; only per-club numbers (score, xG, shots) and scorelines are.
  "Your team" wording is not attribution-checked.
- **Comparisons** are checked only for "more/less than" and multipliers, and
  only in English, Spanish and French.
- **Number words** are checked only in model text; templates use phrases such
  as "first half" by design.
- **Right number, wrong meaning.** A model sentence can use a true fact for the
  wrong thing when the units match ("pressure index 59" written as "59 passes").
- **The stats engine itself.** The checker proves text matches the engine, not
  that the engine is right. The engine is deterministic and documented in
  docs/METRICS.md; its estimates are labelled.
- **Model mode at scale.** Everything above was measured in template mode. The
  same checks run on model text, but the model path has not been evaluated on
  live output (owner-approved spend).

## In the app

- **Show your working** on every studio story card and full replay opens the
  moment audit in a side drawer: each sentence with its numbers and names
  marked inline (matched fact, no matching fact, or nothing to check), the fact
  key and value each one binds to, the source event ids, the fact-check result,
  the parity table, the crew trace with timings, VAR retract and ruled-out
  links, and the list of what is not checked.
- **Crew health** (studio, under the moment list) polls `/api/crew/status`
  every 5 s: provider and orchestrator (the ones not in use are labelled "off
  until deployed"), fallback and rejection rates with their counts, moments per
  minute, per-agent p50/p95, breakers and the translator.
- **Under the hood** (`#lab`) shows the metric registry, basic stats, the
  synthetic auto-eventing benchmark, dataset downloads, the MCP endpoint and the
  broadcast outputs (OBS capture URL, cue-sheet link).
- **Offline demo.** `frontend/scripts/build_demo_fixture.py` also writes
  `frontend/public/demo/demo-insights.json` (about 1 MB, loaded only when a
  panel opens): an audit for every demo moment, worked out by the server's own
  claim and fact-check code against the demo's own card text, plus the metric
  registry, the benchmark and the dataset index. There is no crew trace in the
  recording and the app says so; basic stats, downloads, the MCP endpoint and
  the cue-sheet feed say they need the live server. Three demo goal cards carry
  a parity note (the Arabic stats-scout text writes "two key passes" as a word
  where English prints "2"); the audit shows it as reported.
