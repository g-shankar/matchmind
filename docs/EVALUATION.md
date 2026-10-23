# Evaluating the studio crew

> **Future enterprise extension.** Built and tested, not needed for the
> hackathon brief and not in the demo; the core pipeline runs without it
> ([HACKATHON-BRIEF.md](HACKATHON-BRIEF.md#beyond-the-brief)).

How we check the studio crew (five agents: Spotter, Analyst, Commentator,
Fact-checker, Producer; plus the recap step) before and after any change, and
the numbers we got. Measured on 22 Oct 2026, template mode.

What the crew checks is **numeric-claim validation with deterministic
fallback**: every number and squad name in shown text must match a fact from
the stats engine, and text that fails is replaced by a fact-checked template.
It does not verify tone, causal wording or negation; see
[docs/TRUST.md](TRUST.md) for what is and is not checked, per-sentence claims,
and the cross-language parity results.

Everything on this page ran **free and offline**: the crew is pinned to
`TemplateLLM()` for evaluation, so no paid model call is possible even when
`MATCHMIND_AI_ENABLED=true` (a test enforces this). Foundry's model-graded
evaluators are described at the end; they are paid, owner-run and **have not
been run yet**.

## The dataset

```
matchmind-foundry eval-dataset          # writes backend/data/local/pitchpulse-evaluation.jsonl
matchmind-foundry eval                  # prints the scorecard below
matchmind-foundry eval --json result.json --min-rate 0.99   # exit 1 if groundedness or length drop
```

`eval-dataset` replays every match in `backend/data/matches` (5 synthetic
matches) through the stats engine and the crew, then voices **every moment for
every persona x language** (4 x 5 = 20 audiences), plus each match's full-time
recap for the same 20 audiences.

| | Count |
|---|---|
| Matches | 5 |
| Moments spotted | 334 (13 of the 14 moment kinds; no distance milestone occurs in these five matches) |
| Card records (moments x 20 audiences) | 6,680 |
| Recap records (5 matches x 20 audiences) | 100 |
| **Total records** | **6,780** (about 12 MB, git-ignored, rebuilt in seconds) |
| Cards the crew withheld (no template fits, or the fact-checker refused it) | 0 |

The run is deterministic: two runs write byte-identical files (tested).

Each JSON line uses the Azure AI Evaluation column names, so the same file
feeds Foundry's evaluators unchanged:

| Column | Content |
|---|---|
| `query` | What the agent was asked: moment kind, the persona brief, the language |
| `context` | The moment's facts as JSON: the only numbers and names the text may use |
| `response` | What the viewer sees: headline and body (recaps: title, headline, paragraphs) |
| `ground_truth` | The fact-checked Analyst explanation in the same language (recaps: the headline) |

Extra columns (`facts`, `headline`, `body`, `persona`, `language`,
`focus_player`, `produced_by`, `fallback_reason`, ...) feed the local
evaluators and slicing. No viewer data is in the file: audiences are the
fixed persona x language grid, and all names are from our fictional squads.

## Local evaluators (free, deterministic)

| Evaluator | Passes when | Why it matters |
|---|---|---|
| `groundedness_numbers` | Every number in every field is a stats-engine fact, with the unit, range, per-club attribution and comparison checks (the production fact-checker, template rules) | The product's core rule: numbers come from the engine, never a model |
| `groundedness_numbers_strict` | Same, and no spelled-out number or count word outside the facts ("three", "trois", "hat-trick") | The stricter bar every model-written text must clear before it is shown |
| `length` | Headline, body and paragraph length rules (words, characters, sentences; CJK-aware) | Overlays must fit a lower third |
| `persona_vocab` | casual: no `xG`/`xA`/`xT`/`PDR`; tactical: has numbers when the moment has numeric facts; fantasy: no chalkboard acronyms (`xT`, `PDR`); player spotlight: names the focus player | Each audience gets its own voice |
| `language` | The text is in the requested language (Arabic script, kana/kanji, or English/Spanish/French stop words and spelling cues, after fictional names are removed) | Catches an English fallback leaking into a translated card |

## Scorecard (template mode, 22 Oct 2026, with the trust-layer checks)

Reproduce: `cd backend && matchmind-foundry eval-dataset && matchmind-foundry eval`.

```
PitchPulse crew evaluation: 6780 records from 5 matches (produced_by: template=6780)

evaluator                            all      card     recap    casual  tactical   fantasy player_sp        en        es        fr        ar        ja
groundedness_numbers              100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%
groundedness_numbers_strict        97.7%     97.6%    100.0%     94.5%     97.2%     99.4%     99.6%     97.3%    100.0%     92.8%     99.0%     99.2%
length                            100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%
persona_vocab                      99.1%     99.1%    100.0%    100.0%     96.5%    100.0%    100.0%     99.1%     99.1%     99.1%     99.1%     99.1%
language                          100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%    100.0%
```

| Evaluator | Passed / total |
|---|---|
| groundedness_numbers | 6,780 / 6,780 |
| groundedness_numbers_strict | 6,622 / 6,780 |
| length | 6,780 / 6,780 |
| persona_vocab | 6,720 / 6,780 |
| language | 6,780 / 6,780 |

### What the numbers say

- **Groundedness: 6,780 of 6,780** is partly by construction: the crew
  refuses to show any card that fails the fact-checker. The useful signal is
  that it had to withhold **0 of 6,680** cards, so every template fits its
  facts, including the unit, attribution and comparison checks added with the
  trust layer.
- **Strict groundedness: 6,622 of 6,780 (97.7%)**: 158 template texts use ordinal
  or idiom words the strict rule flags: French "passe la cinquième" (fifth gear,
  92), English "the defensive third" and "this one came" on key-tackle cards
  (32), Japanese 一 in set phrases (一撃 "one blow", 11), Arabic "الشوط الأول"
  (first half, 8) and the kick-off line "from the first whistle" in English,
  French and Arabic (15). Templates are exempt from the strict rule by design
  (the words are not counts); a model that wrote the same words would be
  rejected and the template shown instead.
- **Persona: 6,720 of 6,780 (99.1%)**: the 60 misses are one real gap: the tactical **card**
  (booking) template has no numbers although the facts carry the player's xA
  and sprints (12 bookings x 5 languages). Logged for the template owners.
- **Language: 6,780 of 6,780**: no English fallback leaked into any
  studio-language text. The
  detector is a small, transparent heuristic tuned on football vocabulary;
  tests show it catches English inside a Spanish or Japanese card and Spanish
  inside a French one.

### Claims and parity (same run)

| Measure | Result |
|---|---|
| Moments where all 20 renderings agree on the key facts (`fact_parity`) | 334 of 334 |
| Renderings shown | 6,680 of 6,680 |
| Sentence claims | 25,713: 17,889 `verified_numeric`, 5,742 `verified_name`, 2,082 `unverified_text` (no number or name to check), 0 failed |

### Limits and what can still be wrong

- A passing score means the numbers and names match the engine. It does not
  mean the prose is right: tone, causal wording ("so they have to adjust") and
  negation are not checked, and a model can still use a true number for the
  wrong thing when the units match. docs/TRUST.md lists every gap.
- Template mode only. With paid AI switched on, the same commands evaluate
  the model path once a dataset is built from a crew with a live model; that
  is owner-approved spend and has not been done.
- The local evaluators check rules, not quality of prose. Fluency and
  relevance need a model-graded judge (next section).

## Foundry evaluators (owner-run, paid)

Microsoft Foundry's built-in Groundedness and Relevance evaluators read the
same JSONL. They call a judge model for **every row**, so start with a sample
(for example `head -n 200`), not all 6,780 rows. Prerequisites: the Foundry
resource and project deployed (`docs/FOUNDRY.md`), the
`azure-ai-evaluation` package (MIT) installed locally, and the person running
it signed in with `az login` with access to the project (the template does
not grant this to the app).

```python
# Written against azure-ai-evaluation 1.x; check the installed version's docs.
from azure.ai.evaluation import GroundednessEvaluator, RelevanceEvaluator, evaluate
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()
model_config = {
    "azure_endpoint": "https://<foundry-name>.openai.azure.com/",  # Bicep output openAiEndpoint
    "azure_deployment": "gpt-4o-mini",
    "api_version": "2024-10-21",
}
result = evaluate(
    data="backend/data/local/sample.jsonl",
    evaluators={
        "groundedness": GroundednessEvaluator(model_config, credential=credential),
        "relevance": RelevanceEvaluator(model_config, credential=credential),
    },
    evaluator_config={
        "default": {
            "column_mapping": {
                "query": "${data.query}",
                "context": "${data.context}",
                "response": "${data.response}",
            }
        }
    },
    # Logs the run to the project's Evaluation page (Bicep output foundryProjectEndpoint).
    azure_ai_project="https://<foundry-name>.services.ai.azure.com/api/projects/proj-pitchpulse",
    output_path="backend/data/local/foundry-evaluation.json",
)
print(result["metrics"])
```

Results appear in the Foundry portal under the project's **Evaluation** page.
Until the owner runs this, this page reports local scores only.
