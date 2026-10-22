# Ask the studio

Viewers can ask one short question about the match they are watching, such as
"who has run the furthest?", "¿quién domina ahora?" or "ما النتيجة؟". They can
also tap a suggested question (a chip). The studio answers from the stats
engine, as of the match clock. Every answer is a fixed template filled with
engine numbers. It is fact-checked like a card, and it carries the evidence and
claims behind it. No model ever writes an answer.

| Surface | Where |
|---|---|
| REST | `POST /api/ask` (docs/API-CONTRACT.md) |
| MCP tool | `ask_studio` (docs/MCP.md); same answer as REST, checked by a parity test |
| Web app | the "Ask the studio" box in the Studio and My match views (`frontend/src/components/AskStudio.tsx`) |
| Code | `backend/src/matchmind/ask/` |

## How a question is answered

```
question ─> guard ─> rule parser ─> [model intent: AI switch on only] ─> intent
chip id ───────────────────────────────────────────────────────────────> intent
intent ─> answer from the stats engine (as of the clock) ─> fact-check ─> claims ─> AskAnswer
```

1. **Guard** (`ask/guard.py`). The guard normalises the text: NFKC, look-alike
   letters folded, accents and Arabic letter forms folded, digits normalised.
   It refuses the question when it finds any of these:
   - empty input, or more than 200 characters;
   - hidden control or bidi characters;
   - anything that looks like HTML, script or SQL;
   - instruction-override or role-play phrasing in en, es, fr or ar, including
     squashed or spaced-out letters;
   - a real club, player or broadcaster name from the fact-checker's banned
     list.
2. **Rule parser** (`ask/parser.py`). Keyword tables in en, es, fr and ar map
   the question to one fixed **intent**. Players and clubs are found only in
   this match's squads, by full name, surname, a unique first name or a shirt
   number.
   - A capitalised name that is not in the squads is refused.
   - A shirt number worn by two players gets a "which one?" reply.
3. **Model intent** (`ask/model.py`), optional and **off by default**. It runs
   only when all of these hold:
   - `MATCHMIND_AI_ENABLED=true`;
   - the guard passed the question;
   - the rules found no intent;
   - there is shared model budget left, and the path's own circuit breaker is
     closed.

   The model sees the question and nothing else. It may only return
   `IntentGuess` JSON. Every id in that JSON is resolved against the squads by
   our code, never taken from the model. Model text is never shown to the
   viewer.
4. **Answer** (`ask/answer.py`, `ask/i18n.py`). One handler per intent reads
   the engine's snapshot, player stats and moments as of the playback clock;
   nothing later is read. It fills templates in en, es, fr or ar. Other
   languages get English, and `text_language` says so. Each sentence goes
   through the fact-checker. If any sentence fails, the whole answer is
   replaced by a refusal (`reason: fact_check`).

Suggested chips are sent as an id, never as text: `score`, `top_xg`,
`furthest`, `fastest`, `on_top`, `better_option` and `explain_xg`.

## Intents

| Intent | Example | Answer from |
|---|---|---|
| `score` | "what's the score?" | snapshot score, goal moments |
| `scorers` | "who scored?" | goal moments (and goals VAR ruled out) |
| `team_stat` | "how many shots have Northbridge had?" | team snapshot and basic stats: xG, shots, on target, possession, pass accuracy, passes, tackles, distance |
| `top_player` | "who has run the furthest?" | player stats: distance, top speed, passes, tackles, xG, shots, sprints, key passes, interceptions, touches |
| `player_stats` | "how is Kerrigan doing?", "number 9?" | that player's stats |
| `control` | "who has the ball more?" | possession, control vs chaos, tempo |
| `momentum` | "who is on top?" | momentum, pressure index, pressure spells |
| `better_option` | "should he have passed?" | better-option moments |
| `var` | "any VAR?" | correction moments |
| `cards` | "any bookings?" | card moments |
| `explain_metric` | "what is xG?" | the metric registry (formula and quality flag) plus a plain-words definition |
| `window` | "what happened between 60 and 70?" | moments in that window (never past the clock) |

## Refusal policy

A refusal is a single plain sentence in the viewer's language. It never repeats
the question, and it does not say which check caught it. Markup, injection and
real-name refusals all use the same "I can only answer questions about this
match." sentence.

| Reason | When | Sentence (en) |
|---|---|---|
| `empty` | nothing typed | Type a question about this match. |
| `too_long` | over 200 characters | Please keep your question under 200 characters. |
| `markup`, `injection`, `real_name`, `off_topic` | see the guard above, or nothing in the match was asked | I can only answer questions about this match. |
| `unknown_player` | a name that is not in this match's squads | I can only answer about the players and clubs in this match. |
| `fact_check` | the answer failed the fact-check | I could not check that answer against the stats, so I will not show it. |

The request is treated as hostile at every step:

- Body size limits: 2 KB per body and 1000 characters per field. The guard then
  refuses anything over 200 characters.
- Unknown fields are refused.
- It is rate limited per client IP in the same bucket as the moment and recap
  reads.
- Responses are `no-store`.
- Logs record only the status, the reason, the intent kind and the length.
  The question itself is never logged.
- The web app renders every answer as text, never as HTML.

## Catch-up mode

With `spoilers: false`, the `score`, `scorers` and `var` intents return
`status: hidden`, with "That would give away the result. Tap Reveal to see it,
…". Other answers drop every result fact before they leave the server. See
docs/PERSONALISATION.md, "Spoiler-safe catch-up".

## Offline demo

The browser demo has no server, so it offers the chips only. A typed question
gets "Typed questions need the live server", in the viewer's language.

`frontend/scripts/build_demo_ask.py` precomputes every chip answer, plus the
spoiler-free story, in en, es and ar. It runs the same `matchmind.ask` and
recap code over the numbers already in `demo-match.json`, so the answers agree
with what the demo shows on screen. Answers are recorded at kick-off, then
every 5 minutes of play, then at full time; the demo answers from the latest
point already played. The output is `public/demo/demo-ask.json`. A backend test
fails when that file is stale.

## Tests

Most of these are in `backend/tests/test_ask.py`. The catch-up tests are in
`backend/tests/test_spoilers.py`.

| What | Evidence |
|---|---|
| 50 questions in en, es, fr and ar map to the right intent and answer | `TABLE` |
| 37 adversarial inputs are refused, and the refusal never echoes them | `ADVERSARIAL` |
| Inputs covered by the adversarial set | wrapped and indirect "ignore your rules"; role-play; HTML and SQL; bidi and zero-width characters; look-alike letters; spaced-out letters; real names; over-length input; a crafted squad name |
| Every chip in every studio language | chip tests |
| An answer at 30:00 never uses a later event | future-clock leakage test |
| The model path maps only to the fixed schema | a fake model returning prose, a wrong schema or an injected player name, plus the breaker and budget |
| `POST /api/ask` matches the `ask_studio` MCP tool | `backend/tests/test_mcp.py` parity |
| REST controls | `no-store`; 400 and 413; the shared rate limit; the question is never logged |
| The offline demo's recorded answers are current and never read ahead | `test_demo_answers_are_current_and_never_read_ahead` |
| The web widget | `frontend/src/components/askCatchUp.test.tsx`: chip by id, 200-character cap, text-only rendering, failure sentence, right-to-left Arabic, the claim-audit drawer from "how we know" |
| The demo transport | `frontend/src/api/catchup.test.ts` |

## Read-aloud

Read-aloud is off by default. When switched on, the web app speaks card
headlines and Ask answers through the browser's built-in Web Speech API. It
uses only voices the browser already has, so nothing is sent to a server. If
the browser has no voice for the viewer's language, the app says so in one
plain line, rather than reading in the wrong language. This is common for
Arabic. Read-aloud never speaks in capture mode (`?capture=1`, the OBS / vMix
browser source). Code: `frontend/src/lib/speech.ts`,
`frontend/src/components/ReadAloud.tsx`.

**Planned, not built:** neural voices from Azure AI Speech. That would be a paid
service, and it needs the owner's approval first.

## Known limits

- An unknown name written in Arabic or Japanese script is not detected as a
  name. The question is answered without it.
- Japanese answers are given in English.
- Typed questions in the offline demo are not answered; only the chips work
  there.
