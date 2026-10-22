# PitchPulse API contract (v1)

The backend (`backend/src/matchmind/api`) serves one demo match session. The
frontend talks to it over one WebSocket and a few REST routes. Python models
live in `backend/src/matchmind/crew/contracts.py` (crew and viewer types) and
`backend/src/matchmind/stats/models.py` (stats types); this document is the
TypeScript-facing view of the same shapes.

Base URL: `VITE_API_URL` (e.g. `http://localhost:8000`), falling back to the
page's own origin. WebSocket: `${base with ws/wss}/ws/match`.

Rules:
- Every number on screen comes from these payloads. The frontend never makes up
  or recomputes a stat.
- Playback (play, pause, speed, seek, reset) is shared by everyone watching.
  Viewer choices (persona, language, favourite club, focus player, focus metric)
  are **per connection**: changing them only changes what that connection gets.
- Team names, short names, colours and players come from `teams`. No names in
  the frontend code.

## Shared types

```ts
// Studio languages: hand-written packs. World languages: English text translated by
// Azure AI Translator and fact-checked again, or English when it is off (docs/LANGUAGES.md).
type StudioLanguage = 'en' | 'es' | 'fr' | 'ar' | 'ja';    // 'ar' is right-to-left
type WorldLanguage = 'pt' | 'de' | 'hi' | 'zh-Hans' | 'sw' | 'id' | 'tr' | 'ko';
type Language = StudioLanguage | WorldLanguage;
type PersonaType = 'casual' | 'tactical' | 'fantasy' | 'player_spotlight';  // 'fantasy' is shown as "Stats scout"
type FocusMetric = 'pressure' | 'xg' | 'pass_difficulty' | 'top_speed' | 'momentum';
type MomentKind =
  | 'goal' | 'card' | 'big_chance' | 'better_option' | 'unfound_run'
  | 'momentum_swing' | 'pressure_spell' | 'speed_burst' | 'rocket_shot'
  | 'distance_milestone' | 'hard_pass' | 'milestone'
  | 'correction';                             // a VAR decision that rules an earlier moment out
type Slot = 'lower_third' | 'side_panel' | 'pitch_tag' | 'metric_alert' | 'full_screen';
type FactValue = string | number | boolean;

interface XY { x: number; y: number }                       // metres, 105 x 68; home attacks +x

interface TeamInfo {
  team_id: string; name: string; short_name: string;
  primary_color: string; secondary_color: string;
  formation: string; style: string;
  players: PlayerInfo[];
}
interface PlayerInfo {
  player_id: string; name: string; number: number;
  position: string; line: 'GK' | 'DEF' | 'MID' | 'FWD';
}

interface ViewerProfile {
  persona: PersonaType; language: Language;
  favourite_team: string | null; focus_player_id: string | null;
  focus_metric: FocusMetric | null;
}

interface Evidence { label: string; value: FactValue; unit: string | null; label_key: string | null; source_event_id: string | null }

interface LanguageInfo {
  code: Language; name: string;             // the language's own name, e.g. 'Português'
  english_name: string;
  source: 'studio' | 'translator';
  available: boolean;                       // false: shown in English (world languages while Translator is off)
  rtl: boolean;
  reason: 'translator_off' | null;
}
```

## Events and stats

```ts
// One match event, already enriched with its metrics. Coordinates absolute.
interface MatchEvent {
  event_id: string; seq: number; match_clock: string; clock_s: number; period: 1 | 2;
  type: 'pass' | 'carry' | 'dribble' | 'shot' | 'run' | 'interception' | 'tackle'
      | 'clearance' | 'recovery' | 'foul' | 'card' | 'milestone' | 'var_review'
      | 'match_start' | 'period_start' | 'period_end' | 'match_end';
  team: string | null; player_id: string | null; receiver_id: string | null;
  start: XY | null; end: XY | null;
  outcome: string | null;                     // complete, incomplete, goal, saved, ...
  under_pressure: boolean;
  details: Record<string, FactValue>;         // e.g. pass_type, card colour
  metrics: EventMetrics;
  // var_review only (outcome 'overturned' | 'stands'): the goal it decided on and why.
  reviewed_event_id?: string;
  review_reason?: 'offside' | 'handball' | 'foul' | null;
}

interface EventMetrics {
  pass_distance_m: number | null;
  pass_difficulty: number | null;             // 0-100
  progressive: boolean;
  ball_speed_kmh: number | null;
  player_speed_kmh: number | null;
  sprint: boolean;
  fast_shot: boolean;
  chance_quality: number | null;              // 0-1 (xG)
  distance_to_goal_m: number | null;
  pitch_zone: string | null;
  xt_delta: number | null;                    // expected threat added by a pass/carry
}

interface TeamWindow {                        // rolling 5 minutes of match clock
  possession_pct: number; field_tilt_pct: number; pressure_index: number; // 0-100
  shots: number; xg: number; final_third_passes: number; box_entries: number;
}

interface MatchState {
  match_id: string; clock_s: number; match_clock: string; period: number;
  home_id: string; away_id: string; score_home: number; score_away: number;
  home: TeamWindow; away: TeamWindow;
  momentum: number;                           // -100..100, + = home on top
  control_chaos: number;                      // -1 chaos .. +1 control
  tempo: string;                              // e.g. 'Controlled', 'Frantic'
  events_per_min: number; turnovers_per_min: number; avg_chain_passes: number;
  xg_home: number; xg_away: number; shots_home: number; shots_away: number;
}

// Compatibility shape for the existing ControlChaosGauge.
interface ControlChaosState {
  home_control_pct: number; away_control_pct: number;
  chaos_index: number;                         // = MatchState.control_chaos
  current_tempo: string; rolling_momentum_home: number; // = momentum
}

interface PlayerStats {
  player_id: string; team: string;
  touches: number; passes: number; passes_completed: number; pass_accuracy: number; // %
  key_passes: number; shots: number; goals: number; assists: number;
  xg: number; xa: number; tackles_won: number; interceptions: number;
  top_speed_kmh: number; sprints: number; distance_km: number; carry_distance_m: number;
}
```

## Crew output

```ts
// One timed overlay for this connection's viewer profile.
interface OverlayCard {
  card_id: string; moment_id: string; kind: MomentKind; slot: Slot;
  priority: number;                          // 0-100
  show_at_s: number; duration_s: number;     // match clock seconds
  persona: PersonaType; language: Language; rtl: boolean;
  headline: string; body: string;            // Commentator, fact-checked
  why: string; tactical_tag: string;         // Analyst
  evidence: Evidence[];                      // the numbers behind it
  player_ids: string[]; team: string | null;
  favourite_side: boolean | null;
  produced_by: 'ai' | 'template'; fallback_reason: string | null;
  replay: BetterOptionReplay | UnfoundRunReplay | null;
  text_language: Language;                   // what the text is really in: `language`, or 'en' when a
                                             // world language was not translated (see fallback_reason)
  translated_by: 'azure_ai_translator' | null;
  retracts?: string[];                       // correction cards only: the moment ids this card rules out
  claims: Claim[];                           // one per sentence of headline, body, why (docs/TRUST.md)
}

// One shown sentence and what was machine-checked about it. Wording, tone and
// causal claims are never machine-verified, whatever `check` says.
interface Claim {
  sentence: string;
  field: 'headline' | 'body' | 'why' | 'title' | 'paragraph' | 'key_moment';
  fact_keys: string[];                       // facts the sentence states
  numbers: string[];                         // every number as printed
  source_event_ids: string[];                // events behind those facts (at most 12)
  check: 'verified_numeric'                  // every number is a fact
       | 'verified_name'                     // no numbers; its squad names are facts
       | 'unverified_text';                  // nothing to check, or a check failed (see reason)
  reason: string;
  origin: 'template' | 'matched';            // keys from template placeholders, or matched by value
  bindings: { text: string; kind: 'number' | 'name' | 'text'; fact_key: string | null;
              value: FactValue | null; unit: string | null; entity_id: string | null }[];
}

// "Should he have passed?" drawing
interface BetterOptionReplay {
  shot_event_id: string; shooter_id: string; teammate_id: string;
  shot_chance_quality: number; alt_chance_quality: number;
  pass_success: number; alt_value: number; times_better: number;
  pass_distance_m: number; nearest_marker_m: number;
  shooter_pos: XY; teammate_pos: XY; defenders: XY[]; keeper: XY | null;
}

// The through ball that never came
interface UnfoundRunReplay {
  run_event_id: string; runner_id: string; carrier_id: string; found: boolean;
  pass_on_at_s: number; pass_on_clock: string; clear_of_line_m: number;
  projected_chance_quality: number; one_on_one: boolean;
  carrier_pos: XY; runner_path: XY[]; target: XY; defenders_at_pass: XY[];
}

interface Bookmark {
  moment_id: string; kind: MomentKind; match_clock: string; clock_s: number; period: 1 | 2; title: string;
  ruled_out: boolean;                        // a goal VAR later ruled out (show it only once the decision is past)
}

interface Recap {
  match_id: string; persona: PersonaType; language: Language; rtl: boolean;
  title: string; headline: string; summary_paragraphs: string[];
  key_moments: { match_clock: string; kind: MomentKind; headline: string; moment_id: string }[];
  player_of_the_match_id: string | null; player_of_the_match: string | null;
  stats: Record<string, FactValue>; generated_at_clock: string;
  produced_by: 'ai' | 'template'; fact_check: { ok: boolean; reasons: string[] };
  text_language: Language; translated_by: 'azure_ai_translator' | null;
  fallback_reason: string | null;            // world languages only: why the recap is in English
  claims: Claim[];                           // title, headline, paragraphs, key-moment lines
}

interface CrewStatus {
  mode: 'ai' | 'template'; model: string | null; breakers_open: string[];
  moments: number; fallbacks: number; rejections: number;
  translator: TranslatorStatus;
  health: CrewHealth;
  // Who runs the model steps: 'templates' (no model; show "templates"), 'azure_openai'
  // (Azure OpenAI deployment) or 'foundry_agents' (show "Foundry Agent Service").
  provider: 'templates' | 'azure_openai' | 'foundry_agents';
  // Who chains the agents: our in-process orchestrator or Microsoft Agent Framework workflows.
  orchestrator: 'in_process' | 'agent_framework';
}
// Rolling window (last 256 steps per agent, last 256 verdicts, last 60 s of moments).
interface CrewHealth {
  window: number;
  latency: { agent: string; samples: number; p50_ms: number; p95_ms: number; max_ms: number }[];
  model_steps: number; fallback_steps: number; fallback_rate: number | null;   // null: nothing to divide
  checks: number; rejected_checks: number; rejection_rate: number | null;
  moments_per_min: number;
}

// GET /api/match/moment/{id}/audit (docs/TRUST.md). Never calls a paid model.
interface MomentAudit {
  moment_id: string; kind: MomentKind; match_clock: string; period: number;
  team: string | null; player_ids: string[];
  facts: Record<string, FactValue>; source_event_ids: string[];
  explanation: { moment_id: string; why: string; tactical_tag: string; evidence: Evidence[];
                 produced_by: 'ai' | 'template'; fallback_reason: string | null };
  renderings: {                              // 4 personas x 5 studio languages, then live cards (max 16)
    persona: PersonaType; language: Language; text_language: Language | null;
    source: 'template_sweep' | 'live';       // template-only voicing for the audit, or the live cache
    produced_by: 'ai' | 'template'; fallback_reason: string | null;
    translated_by: 'azure_ai_translator' | null;
    headline: string; body: string; why: string;
    fact_check: { ok: boolean; reasons: string[] };
    claims: Claim[];
  }[];
  parity: {
    ok: boolean; key_facts: string[]; anchors: string[][];
    renderings: number; withheld: number;
    stated: Record<string, string[]>;        // 'persona/language' (' (live)' for live) -> key facts
    problems: string[];
  };
  trace: CrewTrace['steps'];
  not_checked: string[];                     // what the checker does not verify, in words
  retracts: string[];                        // a correction: the moment ids it rules out
  ruled_out_by: string | null;               // a goal VAR later ruled out: the correction's moment id
}
interface TranslatorStatus {
  mode: 'azure' | 'off'; available: boolean; breaker_open: boolean;
  cache_hits: number; translated: number; fallbacks: number; rejections: number;
}
interface CrewTrace {
  moment_id: string; match_clock: string;
  steps: { agent: string; ms: number; status: 'ok' | 'fallback' | 'rejected' | 'error' | 'skipped'; detail: string | null }[];
}

interface AutoEventingStatus {                 // synthetic tracking-to-event benchmark; null if it could not run
  source: 'synthetic_tracking'; label: string; // "Detected from synthetic tracking, not video"
  passes_detected_pct: number; speed_mae_kmh: number; events_checked: number;
  // Optional, added by the benchmark (older clients can ignore them). See docs/AUTO-EVENTING.md.
  name?: string;                               // "Synthetic tracking-to-event benchmark"
  match_id?: string | null;
  speed_mae_ci_kmh?: [number, number] | null;  // 95% bootstrap interval for speed_mae_kmh
  classes?: BenchmarkClassRow[] | null;        // pass, shot, clearance, tackle, interception, recovery
  pressure?: BenchmarkClassRow | null;         // pressure on kicks vs the event data's under_pressure flag
  confusion?: { rows: string[]; columns: string[]; counts: number[][] } | null;
                                               // rows: true kinds + 'spurious'; columns: detected kinds + 'missed'
  baseline?: { name: string; classes: BenchmarkClassRow[] } | null;  // naive detector, same scoring
  pixel_path?: PixelPathRow | null;            // first 30 s only: a smoke check, not the benchmark
  caveat?: string | null;                      // the circularity caveat, in plain words
}
interface BenchmarkClassRow {
  kind: 'pass' | 'shot' | 'clearance' | 'tackle' | 'interception' | 'recovery' | 'pressure';
  support: number; detected: number; matched: number;   // support = true events of this kind
  precision: number; recall: number; f1: number;        // 0-1
  precision_ci: [number, number] | null; recall_ci: [number, number] | null;  // 95% Wilson
}
interface PixelPathRow {                       // label: "Rendered synthetic top-down video, not broadcast footage; no real-video model"
  label: string; window_s: number; frames: number; width_px: number; height_px: number;
  player_error_m: number | null; ball_error_m: number | null; ball_found_pct: number;
  coordinate: BenchmarkClassRow[]; pixels: BenchmarkClassRow[];   // same frames, both paths (last row: pressure)
  speed_mae_kmh_coordinate: number | null; speed_mae_kmh_pixels: number | null;
}
```

## WebSocket `/ws/match`

Server -> client. Every message is `{ "type": ..., "data": ... }`.

| type | data | when |
|---|---|---|
| `INITIAL_SNAPSHOT` | `{ match_id, clock, period, home_score, away_score, teams: { home: TeamInfo, away: TeamInfo }, state: MatchState, control_chaos: ControlChaosState, profile: ViewerProfile, playback: Playback, recent_cards: OverlayCard[], bookmarks: Bookmark[], players: PlayerStats[], crew: CrewStatus, languages: LanguageInfo[], auto_eventing: AutoEventingStatus \| null, cue_sheet: CueSheetState }` | on connect, after `MATCH_RESET`, after a seek |
| `MATCH_TICK` | `{ event: MatchEvent, clock, period, score: { home, away }, state: MatchState, control_chaos: ControlChaosState, cards: OverlayCard[], players_changed: PlayerStats[] }` | every event as it is played |
| `CUES` | `{ sheet_id, cues: Cue[], active?: Cue[] }` | after a `MATCH_TICK` that produced cues for this viewer; `active` (what is on air now) is present when a new sheet starts, e.g. after `set_view` |
| `PLAYBACK_CONTROL` | `Playback` | play, pause, speed change |
| `MATCH_RESET` | `{}` | reset (followed by `INITIAL_SNAPSHOT`) |
| `PROFILE_CHANGED` | `ViewerProfile` | after this connection's `set_view` |
| `PERSONA_CHANGED` | `{ persona }` | kept for the old frontend; sent with `PROFILE_CHANGED` |
| `MATCH_END` | `{ recap: Recap }` | full time, for this connection's persona and language |
| `ERROR` | `{ message }` | invalid action (plain words, no stack traces) |

```ts
interface Playback {
  is_running: boolean; speed_multiplier: 1 | 10 | 60;
  clock_s: number; match_clock: string; period: number;   // of the last event played
  ended: boolean;
}
```

Speed: one real second plays `10 x speed_multiplier` match seconds (the base
rate of 10 can be changed with `MATCHMIND_BASE_RATE`). So 1x plays the match in
about 9 minutes, 10x (the default) in about 54 seconds and 60x in about 9
seconds. The half-time break is skipped. Playback only moves while at least
one viewer is connected.

Seek: `clock_s` is the match clock, which restarts at 2700 (45:00) for the
second half while first-half stoppage time runs past 2700. Pass `period` (1 or
2) to be exact, as bookmarks do; without it, any time from 2700 on means the
second half. Seeking to the start of a half includes its kick-off. A time after
the last event, or `toggle_pause` after full time, gets `ERROR` (use `reset` or
`seek`). After `MATCH_END` the server also sends `PLAYBACK_CONTROL` with
`ended: true`.

Seek and reset are shared, so they are throttled for everyone: at most one
every 0.5 s across WebSocket and REST together. A seek or reset inside that
window is refused (WebSocket `ERROR` "Jumping around too fast. Wait a moment
and try again.", REST 429 with the same `detail`); nothing is queued.

Client -> server. `{ "action": ..., ... }` as JSON text, max 4 KB, unknown
actions, unknown fields and bad values get `ERROR`. Each connection may send
about 10 actions a second (bursts of 20). Browsers must connect from an origin
in `MATCHMIND_ALLOWED_ORIGINS`, or, when this server serves the built frontend
itself, from `MATCHMIND_PUBLIC_ORIGIN`. The `Host` header is never trusted for
this. A refused origin, a full server (`MATCHMIND_MAX_CONNECTIONS`) or too many
connections from one IP (`MATCHMIND_MAX_CONN_PER_IP`) closes with code 1008. A
viewer that falls more than 4 MB behind on messages is disconnected with code
1013 (try again later); reconnecting gets a fresh `INITIAL_SNAPSHOT`.

| action | fields | effect |
|---|---|---|
| `toggle_pause` | | shared |
| `set_speed` | `speed_multiplier: 1 \| 10 \| 60` | shared |
| `reset` | | shared |
| `seek` | `clock_s: number`, `period?: 1 \| 2` | shared; replays stats to that point (no cards on the way), then `INITIAL_SNAPSHOT` with the moments before that point as `recent_cards` |
| `set_view` | any subset of `ViewerProfile` | this connection only; `PROFILE_CHANGED`, cards from now on follow it. `null` clears `favourite_team`, `focus_player_id` or `focus_metric`; the club and player must be in this match |
| `set_persona` | `persona`, `spotlight_player_id?` | old alias for `set_view` (`spotlight_player_id` sets `focus_player_id`) |

Cards in `MATCH_TICK` are already filtered and ordered for the connection's
profile: persona and language applied, club heart for the favourite club
(its moments boosted, rival minor moments dropped, fan's-side framing: see
docs/PERSONALISATION.md), `focus_player_id` moments always kept, `focus_metric` changes sent as
`slot: 'metric_alert'`, speed and distance tags as `slot: 'pitch_tag'`.
The server gets these from the crew: `render(bundle, profile)` for each moment,
plus, when the crew provides it, `metric_alerts(snapshot, players, profile)` for
the focus metric (one place in `MatchSession.cards_for`).

### Corrections and the cue sheet

A VAR review that overturns a goal arrives as a `var_review` event, a
`correction` moment and a card with `retracts: [goal moment id]`. From then on
the server never sends the ruled-out goal as live: not in `MATCH_TICK` cards,
`recent_cards`, `cue_sheet.active` or the recap, also after a seek or a
reconnect. Clients should drop any card whose `moment_id` a correction
retracts, even if it arrives late.

`CUES` carries this viewer's broadcast cues (`show`, `update`, `retract`,
`supersede`, `clear`) in `seq` order. Apply each `cue_id` once; ignore
repeats. `INITIAL_SNAPSHOT.cue_sheet` is `{ sheet_id, last_seq, active: Cue[] }`:
replace local cue state with it. Older clients can ignore `CUES` and
`cue_sheet`; every other message is unchanged. The cue shape, timing model and
collision rules are in [CUE-SHEET.md](CUE-SHEET.md) and
`backend/schema/cue.schema.json`.

## REST

| route | returns |
|---|---|
| `GET /api/health` | `{ status: 'ok' }` |
| `GET /api/teams` | `{ home: TeamInfo, away: TeamInfo }` |
| `GET /api/match/snapshot` | `INITIAL_SNAPSHOT.data` for the default profile |
| `GET /api/match/players` | `PlayerStats[]` |
| `GET /api/match/bookmarks` | `Bookmark[]` for the whole match (leaves out `speed_burst`, `rocket_shot`, `distance_milestone` and `hard_pass`, which still arrive as tick cards; same list in `INITIAL_SNAPSHOT.bookmarks`) |
| `GET /api/match/moment/{moment_id}?persona=&lang=&favourite_team=` | `OverlayCard` (for "jump to moment" and replays) |
| `GET /api/match/moment/{moment_id}/audit` | `MomentAudit`: facts, source events, evidence, every rendering's claims and fact-check, parity, trace (docs/TRUST.md) |
| `GET /api/match/recap?persona=&lang=` | `Recap` (so far, or full match after the end; the same after a seek as after watching straight through) |
| `GET /api/match/cue-sheet?persona=&lang=&favourite_team=&since_seq=0&limit=500` | `CueSheetPage`: the compiled cue sheet up to the current position, cues with `seq > since_seq`, at most `limit` (1-500); page with `next_since_seq` while `has_more` (see CUE-SHEET.md). Same rate limit as `/api/match/moment` |
| `POST /api/match/seek` `{ clock_s, period? }` | `Playback` |
| `POST /api/match/speed` `{ speed_multiplier }` | `Playback` |
| `POST /api/match/reset` | `Playback` |
| `GET /api/crew/status` | `CrewStatus` |
| `GET /api/languages` | `{ languages: LanguageInfo[], translator: TranslatorStatus }`: every language, its source (studio pack or Azure AI Translator) and whether it can be shown now |
| `GET /api/crew/trace?limit=20` | `CrewTrace[]` (newest first) |
| `GET /api/auto-eventing` | `AutoEventingStatus` (computed once per match when the session loads, then served from memory) or 404 if it could not run |
| `GET /api/source` | `MatchSource`: where the match comes from (file or the live Event Hubs stream) and the stream counters |
| `GET /api/dataset` | `DatasetIndex`: every downloadable synthetic match with its scenario and seed (docs/DATASET.md) |
| `GET /api/dataset/export?match_id=&format=jsonl\|csv\|zip[&tracking_period=&tracking_from=&tracking_to=]` | a file download (streamed, `Content-Disposition: attachment`): events as JSON lines (byte for byte as bundled), events as CSV, or a zip with metadata, rosters, schema, data dictionary and, with the three tracking parameters, a 25 Hz synthetic tracking sample of at most 60 s (zip only) |

```ts
interface DatasetMatch {
  match_id: string;                         // allow-listed: bundled ids and MM-GEN-01000..MM-GEN-01019
  kind: 'bundled' | 'seeded';
  scenario: 'demo_storyline' | 'chance_model' | 'chance_model_with_beats';
  seed: number; home: string; away: string;
  score: string | null;                     // bundled only, e.g. '2-3'
  events: number | null;                    // bundled only
}
interface DatasetIndex {
  synthetic: true; note: string; schema_version: string;
  pitch: { length_m: 105; width_m: 68; home_attacks: '+x' };
  formats: ('jsonl' | 'csv' | 'zip')[];
  tracking: { hz: 25; max_window_s: 60; formats: ['zip'] };
  scenarios: Record<string, string>;
  seeded: { seed_start: number; seed_end: number; match_id: string };
  matches: DatasetMatch[];
}
interface MatchSource {
  source: 'file' | 'eventhubs';
  format?: 'jsonl' | 'csv';                 // file source
  requested?: 'eventhubs'; note?: string;   // live mode was asked for but no match started in time
  starting_position?: string;               // eventhubs source
  match_id: string; events_loaded: number;
  complete: boolean;                        // false while a live match is still arriving
  stream?: {                                // eventhubs source only: counts, never event content
    state: 'waiting_for_match_start' | 'live' | 'ended' | 'stopped';
    match_id: string | null; queued: number; backpressure_waits: number; error: string | null;
    received: number; accepted: number; duplicates: number; conflicts: number; rejected: number;
    too_big: number; before_start: number; other_match: number; after_end: number;
    reordered: number; skipped: number; last_problem: string | null;
  };
}
```

Errors: `{ "detail": "plain words" }` with 400 or 404 (429 for a seek or reset
inside the 0.5 s throttle, or more than about 2 POSTs a second, bursts of 10,
from one client IP, or more than about 3 `GET /api/match/moment` and
`GET /api/match/recap` requests a second, bursts of 30, from one client IP, a bucket the
moment audit shares; 503 while the match is still loading, 500 with a generic
message if something breaks on our side).
`GET /api/dataset/export` allows about one request every 5 s per client IP
(bursts of 6) and at most two exports built at once (429 "Downloads are busy");
an unknown `match_id` is 404 and a malformed one 400.
API responses carry `Cache-Control: no-store`, except successful `/api/dataset`
responses (synthetic, the same for everyone), which carry
`Cache-Control: public, max-age=3600`. There is no upload route: external feeds
are played from disk (docs/DATASET.md).

## MCP

`POST /mcp` serves the same reads as typed, read-only Model Context Protocol
tools (Streamable HTTP, stateless, JSON responses), on the same live session.
Each tool returns exactly the REST payload above (or the engine's, for tools
with no REST route); a parity test holds them byte-identical. The endpoint has
its own per-IP bucket (about 3 POSTs a second, bursts of 30), 16 KB bodies, one
JSON-RPC request per POST, and checks `Origin` against the allow-list and `Host`
against DNS rebinding. Tools, inputs, outputs and how to attach a client:
[MCP.md](MCP.md). The stdio form is `matchmind-mcp`.

## Server settings

| env | default | meaning |
|---|---|---|
| `MATCHMIND_ALLOWED_ORIGINS` | `http://localhost:5173,http://localhost:3000` | comma-separated CORS and WebSocket origins; `*` is ignored |
| `MATCHMIND_MATCH_FILE` | `backend/data/matches/MM-DEMO-001.jsonl` | the match to play: `.jsonl` in our event schema or `.csv` with a mapping file, both checked strictly by `matchmind.ingest` (docs/DATASET.md) |
| `MATCHMIND_FEED_MAPPING` | (none) | mapping file for a generic CSV feed |
| `MATCHMIND_ROSTER_FILE` | (none) | roster of invented clubs and players for a feed that does not use the two bundled clubs |
| `MATCHMIND_SOURCE` | `file` | `eventhubs`: play the live Event Hubs stream instead (keyless, `EVENTHUB_FULLY_QUALIFIED_NAMESPACE` + `EVENTHUB_NAME`, needs the `azure` extra) |
| `MATCHMIND_EVENTHUBS_MATCH_ID` | (none) | follow this match on the hub; default the first match_start seen |
| `MATCHMIND_EVENTHUBS_START` | `@latest` | consumer starting position (`-1` = earliest retained event) |
| `MATCHMIND_EVENTHUBS_WAIT_S` | `90` | how long to wait for a live match_start before replaying the match file |
| `EVENTHUB_CONSUMER_GROUP` | `$Default` | Event Hubs consumer group |
| `MATCHMIND_DATASET_DIR` | `backend/data/matches` | the bundled dataset offered by `/api/dataset` |
| `MATCHMIND_STATIC_DIR` | `./static` (working directory) | built frontend served at `/` when it has an `index.html` |
| `MATCHMIND_BASE_RATE` | `10` | match seconds per real second at 1x |
| `MATCHMIND_AI_ENABLED` | `false` | `true`, `1` or `yes` (any case): live crew uses the paid model client; the whole-match bookmark pass always uses templates. Model recaps are only made at full time, once per persona, language and favourite club |
| `MATCHMIND_LLM_PROVIDER` | `azure_openai` | with `MATCHMIND_AI_ENABLED` on: `azure_openai` (chat completions on `AZURE_OPENAI_DEPLOYMENT`) or `foundry_agents` (Microsoft Foundry Agent Service agents on the project at `MATCHMIND_FOUNDRY_PROJECT_ENDPOINT` or `AZURE_AI_PROJECT_ENDPOINT`; `docs/FOUNDRY.md`). Anything else reads as `azure_openai` |
| `MATCHMIND_FOUNDRY_MODEL` | `AZURE_OPENAI_DEPLOYMENT`, else `gpt-4o-mini` | model deployment the Foundry agents use |
| `MATCHMIND_ORCHESTRATOR` | `in_process` | `agent_framework`: the crew's chains run as Microsoft Agent Framework workflows (free; needs the `agent-framework` extra, otherwise logged and in process) |
| `MATCHMIND_AI_BUDGET` | `300` | most paid model calls per process; then templates with `fallback_reason: 'budget'` |
| `MATCHMIND_AI_RATE_PER_MIN` | `30` | most paid model calls in any 60 s; then templates with `fallback_reason: 'budget'` |
| `MATCHMIND_TRANSLATOR_ENABLED` | `false` | with `MATCHMIND_AI_ENABLED` also on: world languages are translated by Azure AI Translator (keyless, `AZURE_TRANSLATOR_ENDPOINT` custom subdomain); otherwise they are English with `fallback_reason: 'translator_off'` |
| `MATCHMIND_TRANSLATOR_CHAR_BUDGET` | `200000` | most characters sent to Translator per process; then English with `fallback_reason: 'translator_budget'` |
| `MATCHMIND_TRANSLATOR_CHARS_PER_MIN` | `20000` | most characters sent to Translator in any 60 s |
| `MATCHMIND_PUBLIC_ORIGIN` | (none) | this server's own public origin (e.g. `https://pitchpulse.example`), allowed for the WebSocket only when the built frontend is served from `MATCHMIND_STATIC_DIR` |
| `MATCHMIND_MCP_ENABLED` | `true` | `false`, `0`, `no` or `off`: no `/mcp` endpoint (REST and WebSocket unchanged) |
| `MATCHMIND_MCP_ALLOWED_HOSTS` | (none) | extra comma-separated `Host` values `/mcp` answers (beyond localhost and the hosts of the allowed and public origins); `*` is ignored |
| `MATCHMIND_MAX_CONNECTIONS` | `200` | most open WebSockets |
| `MATCHMIND_MAX_CONN_PER_IP` | `20` | most open WebSockets from one client IP |
| `MATCHMIND_HOST`, `PORT` / `MATCHMIND_PORT` | `127.0.0.1`, `8000` | `matchmind-api` / `python -m matchmind.api`; ASGI app `matchmind.api.app:app` |
