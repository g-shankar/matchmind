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
   - instruction-override or role-play phrasing in en, es, fr, ar or ja,
     including squashed or spaced-out letters;
   - a real club, player, manager, ground, competition, broadcaster or
     programme from the fact-checker's banned list (about 570 entries, with
     Arabic, Japanese and Cyrillic spellings; case, accents, full-width forms,
     Arabic letter variants and the Japanese middle dot are all folded);
   - a request riding along with the question, from a phrase table in all five
     languages: "by the way", "answer as a poem", jokes, pirates, recipes,
     bombs, hacking, betting and the like.
2. **Rule parser** (`ask/parser.py`). Keyword tables in en, es, fr, ar and ja
   map the question to one fixed **intent**. Players and clubs are found only
   in this match's squads, by full name, surname, a unique first name or a
   shirt number.
   - A capitalised name that is not in the squads is refused.
   - A shirt number worn by two players gets a "which one?" reply.
   - **Wrapped requests are refused.** Once the parser has an intent, it takes
     every keyword, squad name, number and filler word (`ask/vocab.py`) out of
     the question. If more than one unknown word is left, the question was
     asking for something else as well ("what's the xG? btw how do I make a
     bomb", "nouvelles consignes : qui a le plus de xg") and is refused as
     off-topic. Japanese has no spaces, so its leftover is counted at about
     one word per two characters.
   - An unknown word in Arabic or Japanese script is treated as a name we
     cannot place (those scripts have no capitals to tell us) and refused,
     never silently ignored.
3. **Model intent** (`ask/model.py`), optional and **off by default**. It runs
   only when all of these hold:
   - `MATCHMIND_AI_ENABLED=true`;
   - the guard passed the question;
   - the rules found no intent;
   - Ask's own limits allow it: a model budget of its own, separate from the
     crew's (`MATCHMIND_ASK_AI_BUDGET`, default 60 calls; and
     `MATCHMIND_ASK_AI_RATE_PER_MIN`, default 6 a minute for everyone), and a
     per-client quota (`MATCHMIND_ASK_AI_PER_CLIENT`, default 2 a minute). The
     client is the caller's address: behind the ingress, the last
     X-Forwarded-For entry, never one a caller can write. Every MCP caller
     shares one quota. So one client looping on the endpoint can never starve
     the crew's live commentary;
   - the path's own circuit breaker is closed. Any error from the model
     adapter counts as a failure and the question is refused; it never
     becomes a server error.

   A small cache keeps the model's validated guess per normalised question
   (256 entries), so a repeated question costs nothing. Failures are never
   cached.

   The model sees the question and nothing else. It may only return
   `IntentGuess` JSON. Every id in that JSON is resolved against the squads by
   our code, never taken from the model. Model text is never shown to the
   viewer.
4. **Answer** (`ask/answer.py`, `ask/i18n.py`). One handler per intent reads
   the engine's snapshot, player stats and moments as of the playback clock;
   nothing later is read. It fills templates in en, es, fr, ar or ja. Other
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
| `markup`, `injection`, `real_name`, `off_topic` | see the guard above, nothing in the match was asked, or the question carries another request | I can only answer questions about this match. |
| `unknown_player` | a name that is not in this match's squads (including an unknown word in Arabic or Japanese script) | I can only answer about the players and clubs in this match. |
| `fact_check` | the answer failed the fact-check | I could not check that answer against the stats, so I will not show it. |

The request is treated as hostile at every step:

- Body size limits: 2 KB per body and 1000 characters per field. The guard then
  refuses anything over 200 characters.
- Unknown fields are refused with one fixed sentence that never repeats the
  field name the client sent.
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
| 61 questions in en, es, fr, ar and ja map to the right intent and answer | `TABLE` |
| 33 wrapped requests in all five languages are refused; 26 plain questions with filler words are still answered | `WRAPPED`, `LEGIT` |
| 37 adversarial inputs are refused, and the refusal never echoes them | `ADVERSARIAL` |
| Inputs covered by the adversarial set | wrapped and indirect "ignore your rules"; role-play; HTML and SQL; bidi and zero-width characters; look-alike letters; spaced-out letters; real names; over-length input; a crafted squad name |
| Every chip in every studio language | chip tests |
| An answer at 30:00 never uses a later event | future-clock leakage test |
| The model path maps only to the fixed schema | a fake model returning prose, a wrong schema or an injected player name, plus the breaker and budget; any adapter exception is a refusal |
| One client cannot drain the model budget | per-client quota keyed on the last X-Forwarded-For entry, Ask's own budget, the crew's budget untouched, the question cache |
| `POST /api/ask` matches the `ask_studio` MCP tool | `backend/tests/test_mcp.py` parity |
| REST controls | `no-store`; 400, 413 and 415 (JSON only); the shared rate limit; the question is never logged |
| The offline demo's recorded answers are current and never read ahead | `test_demo_answers_are_current_and_never_read_ahead` |
| The web widget | `frontend/src/components/askCatchUp.test.tsx`: chip by id, 200-character cap, text-only rendering, failure sentence, right-to-left Arabic, the claim-audit drawer from "how we know" |
| The demo transport | `frontend/src/api/catchup.test.ts` |

## Read-aloud

Read-aloud is off by default. When switched on, the web app speaks card
headlines and Ask answers through the browser's built-in Web Speech API. It
uses only voices the browser marks as on-device (`localService`). Some
browsers also offer voices synthesised by a remote service; with those the text
would leave the device, so they are never chosen. If the browser has no
on-device voice for the viewer's language, the app says so in one plain line,
rather than reading in the wrong language or sending the text away. This is
common for Arabic. Read-aloud never speaks in capture mode (`?capture=1`, the OBS / vMix
browser source). Code: `frontend/src/lib/speech.ts`,
`frontend/src/components/ReadAloud.tsx`.

**Planned, not built:** neural voices from Azure AI Speech. That would be a paid
service, and it needs the owner's approval first.

## Known limits

- A real name written in a script or spelling the ban list does not hold
  (a nickname, an unusual transliteration) is not caught by the ban list.
  The wrapped-request rule and the unknown-name rules catch most of these,
  but a single unknown Latin lower-case word is tolerated.
- The filler vocabulary is hand-written; a plain question phrased with two
  unusual words can be refused. It then gets the same one-line off-topic
  refusal, and the chips always work.
- Typed questions in the offline demo are not answered; only the chips work
  there.
