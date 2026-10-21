# Languages: studio packs and Azure AI Translator

PitchPulse speaks 13 languages. They come from two places, and the app always
says which.

| Source | Languages | How the text is made | Cost |
|---|---|---|---|
| **Studio packs** | English, Español, Français, العربية (right-to-left), 日本語 | Hand-written phrase packs in `backend/src/matchmind/crew/i18n`, filled with the moment's facts | Free, always on |
| **World languages** | Português, Deutsch, हिन्दी, 简体中文, Kiswahili, Bahasa Indonesia, Türkçe, 한국어 | The crew's English card or recap, translated by **Azure AI Translator**, then fact-checked again | Billed per character, off by default |

The studio packs are the primary path and never go through Translator.

## How a world-language card is made

```
moment -> crew writes the English card (template or model; cached, so no extra model spend)
       -> protect: every number, clock, player and club name and stat term (xG, PDR, km/h)
          is wrapped in <span class="notranslate">
       -> ONE Translator request with all of the card's strings
          (headline, body, why it matters, evidence labels; for a recap: title, headline,
          paragraphs and key-moment headlines)
       -> unprotect: every protected piece must come back exactly as sent, or the
          translation is refused
       -> fact-checker: the translated text is checked against the moment's facts
          (every number must be a fact, no real names, length rules)
       -> shown with the tag "Translated by Azure AI Translator"
```

Any problem keeps the English text on screen, with `language` set to the
viewer's choice, `text_language: 'en'` and a `fallback_reason`, and the card
says so in plain words ("Shown in English: Azure AI Translator is off").

| `fallback_reason` | Meaning |
|---|---|
| `translator_off` | The switch is off (the default) |
| `translation_rejected` | A protected number or name changed, or the fact-checker refused the translation |
| `translator_budget` | The character budget or per-minute rate is spent |
| `translator_circuit_open` | Three failures in a row: Translator is paused for 60 s |
| `translator_timeout` | No answer within 2.5 s |
| `translator_error` | Any other failure (network, sign-in, HTTP error). Provider text is never shown or logged |
| `translator_too_long` | More than 10,000 characters in one request (a card is far below this) |

## The call

Translator v3 REST on the resource's own custom subdomain, signed in with
Microsoft Entra ID (managed identity through `DefaultAzureCredential`, token
scope `https://cognitiveservices.azure.com/.default`). No key exists: the
Bicep template creates the resource with local auth disabled and gives the
app's identity the Cognitive Services User role.

```
POST https://<custom-subdomain>.cognitiveservices.azure.com/translator/text/v3.0/translate
     ?api-version=3.0&from=en&to=<lang>&textType=html
Authorization: Bearer <Entra ID token>
Content-Type: application/json; charset=UTF-8
X-ClientTraceId: <uuid>

[{"Text": "..."}, {"Text": "..."}]
```

With a custom subdomain endpoint and an Entra token, no
`Ocp-Apim-Subscription-Key`, `Ocp-Apim-ResourceId` or
`Ocp-Apim-Subscription-Region` header is needed, so none is sent. The client
refuses any other endpoint (the global endpoint would need a key or resource
id). `httpx` and `azure-identity` are optional extras (`backend[azure]`), loaded
only when the translator is used.

## Switch, budget and rails

| Setting | Default | Meaning |
|---|---|---|
| `MATCHMIND_TRANSLATOR_ENABLED` | `false` | Translator on. Needs `MATCHMIND_AI_ENABLED` on too (owner approval for paid AI) |
| `AZURE_TRANSLATOR_ENDPOINT` | (none) | `https://<custom-subdomain>.cognitiveservices.azure.com/` (set by the Bicep) |
| `AZURE_TRANSLATOR_REGION` | (none) | Set by the Bicep; kept for reference, not sent |
| `MATCHMIND_TRANSLATOR_CHAR_BUDGET` | `200000` | Most characters sent per process |
| `MATCHMIND_TRANSLATOR_CHARS_PER_MIN` | `20000` | Most characters sent in any 60 s |

- **Cost is per character.** PitchPulse counts every character it sends,
  protection tags included, so its own count is never below what is billed.
  A card is a few hundred characters. Check the Azure AI Translator pricing
  page for the current rate; the template deploys the S1 (pay as you go) tier.
- **Cache.** Translations are kept in a bounded LRU (4,096 entries) by (hash
  of the strings, language). It holds public match text only, never anything
  about a viewer. A cached translation is still fact-checked every time it is
  used. A refused translation is cached too, so it is never bought twice.
- **One request per text at a time.** When many viewers ask for the same card
  at once, one request is sent and the others wait for it.
- **Passing problems are not stored.** A card or recap left in English by a
  timeout, error, paused breaker or spent budget is not cached, so the next
  request tries again.
- **The whole-match bookmark pass never translates**, so loading a match costs
  nothing.

## What the screen shows

- The language picker groups **Studio languages** and **World languages ·
  Azure AI Translator**. While Translator is off, world languages are greyed
  out with "Off: needs Azure AI Translator", and a "World languages: off" chip
  sits next to the picker.
- Translated cards and recaps carry a "Translated by Azure AI Translator" tag.
- Card text is marked with its real language (`lang` attribute), so screen
  readers and fonts follow it. The app's own labels stay in English, Spanish
  or Arabic; none of the world languages is right-to-left.
- The offline demo (in-browser replay) never calls Translator. It lists French
  and Japanese as "Not in the offline demo" (the recording holds English,
  Spanish and Arabic text) and world languages as off.

## API

- `GET /api/languages` returns `{ languages: LanguageInfo[], translator: TranslatorStatus }`.
- `INITIAL_SNAPSHOT.languages` carries the same list; `CrewStatus.translator`
  carries the counters (requests, cache hits, characters sent, rejections).
- `OverlayCard` and `Recap` carry `text_language` and `translated_by`.

See `docs/API-CONTRACT.md` for the types.

## Tests

`backend/tests/test_translator.py` (no network; every request goes to an
injected transport): request shape (one batched POST, `from=en`, `to=<lang>`,
bearer token from the injected credential, no key headers), protection round
trip, refusal of any changed number or name, fact-checker rejection of a
tampered translation, off mode, budget and rate, breaker, timeout, cache hits,
one request for many concurrent viewers, and a faithful translation of every
studio card passing for every audience.
`frontend/src/components/LanguagePicker.test.tsx` covers the greyed-out
picker and the card tags.
