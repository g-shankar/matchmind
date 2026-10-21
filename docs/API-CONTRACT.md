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
type Language = 'en' | 'es' | 'fr' | 'ar' | 'ja';          // 'ar' is right-to-left
type PersonaType = 'casual' | 'tactical' | 'fantasy' | 'player_spotlight';
type FocusMetric = 'pressure' | 'xg' | 'pass_difficulty' | 'top_speed' | 'momentum';
type MomentKind =
  | 'goal' | 'card' | 'big_chance' | 'better_option' | 'unfound_run'
  | 'momentum_swing' | 'pressure_spell' | 'speed_burst' | 'rocket_shot'
  | 'distance_milestone' | 'hard_pass' | 'milestone';
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
```

## Events and stats

```ts
// One match event, already enriched with its metrics. Coordinates absolute.
interface MatchEvent {
  event_id: string; seq: number; match_clock: string; clock_s: number; period: 1 | 2;
  type: 'pass' | 'carry' | 'dribble' | 'shot' | 'run' | 'interception' | 'tackle'
      | 'clearance' | 'recovery' | 'foul' | 'card' | 'milestone'
      | 'match_start' | 'period_start' | 'period_end' | 'match_end';
  team: string | null; player_id: string | null; receiver_id: string | null;
  start: XY | null; end: XY | null;
  outcome: string | null;                     // complete, incomplete, goal, saved, ...
  under_pressure: boolean;
  details: Record<string, FactValue>;         // e.g. pass_type, card colour
  metrics: EventMetrics;
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

interface Bookmark { moment_id: string; kind: MomentKind; match_clock: string; clock_s: number; period: 1 | 2; title: string }

interface Recap {
  match_id: string; persona: PersonaType; language: Language; rtl: boolean;
  title: string; headline: string; summary_paragraphs: string[];
  key_moments: { match_clock: string; kind: MomentKind; headline: string; moment_id: string }[];
  player_of_the_match_id: string | null; player_of_the_match: string | null;
  stats: Record<string, FactValue>; generated_at_clock: string;
  produced_by: 'ai' | 'template'; fact_check: { ok: boolean; reasons: string[] };
}

interface CrewStatus {
  mode: 'ai' | 'template'; model: string | null; breakers_open: string[];
  moments: number; fallbacks: number; rejections: number;
}
interface CrewTrace {
  moment_id: string; match_clock: string;
  steps: { agent: string; ms: number; status: 'ok' | 'fallback' | 'rejected' | 'error' | 'skipped'; detail: string | null }[];
}

interface AutoEventingStatus {                 // filled by the auto-eventing work; null until then
  source: 'synthetic_tracking'; label: string; // "Detected from synthetic tracking, not video"
  passes_detected_pct: number; speed_mae_kmh: number; events_checked: number;
}
```

## WebSocket `/ws/match`

Server -> client. Every message is `{ "type": ..., "data": ... }`.

| type | data | when |
|---|---|---|
| `INITIAL_SNAPSHOT` | `{ match_id, clock, period, home_score, away_score, teams: { home: TeamInfo, away: TeamInfo }, state: MatchState, control_chaos: ControlChaosState, profile: ViewerProfile, playback: Playback, recent_cards: OverlayCard[], bookmarks: Bookmark[], players: PlayerStats[], crew: CrewStatus, auto_eventing: AutoEventingStatus \| null }` | on connect, after `MATCH_RESET`, after a seek |
| `MATCH_TICK` | `{ event: MatchEvent, clock, period, score: { home, away }, state: MatchState, control_chaos: ControlChaosState, cards: OverlayCard[], players_changed: PlayerStats[] }` | every event as it is played |
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
profile: persona and language applied, favourite club's moments boosted,
`focus_player_id` moments always kept, `focus_metric` changes sent as
`slot: 'metric_alert'`, speed and distance tags as `slot: 'pitch_tag'`.
The server gets these from the crew: `render(bundle, profile)` for each moment,
plus, when the crew provides it, `metric_alerts(snapshot, players, profile)` for
the focus metric (one place in `MatchSession.cards_for`).

## REST

| route | returns |
|---|---|
| `GET /api/health` | `{ status: 'ok' }` |
| `GET /api/teams` | `{ home: TeamInfo, away: TeamInfo }` |
| `GET /api/match/snapshot` | `INITIAL_SNAPSHOT.data` for the default profile |
| `GET /api/match/players` | `PlayerStats[]` |
| `GET /api/match/bookmarks` | `Bookmark[]` for the whole match (leaves out `speed_burst`, `rocket_shot`, `distance_milestone` and `hard_pass`, which still arrive as tick cards; same list in `INITIAL_SNAPSHOT.bookmarks`) |
| `GET /api/match/moment/{moment_id}?persona=&lang=&favourite_team=` | `OverlayCard` (for "jump to moment" and replays) |
| `GET /api/match/recap?persona=&lang=` | `Recap` (so far, or full match after the end; the same after a seek as after watching straight through) |
| `POST /api/match/seek` `{ clock_s, period? }` | `Playback` |
| `POST /api/match/speed` `{ speed_multiplier }` | `Playback` |
| `POST /api/match/reset` | `Playback` |
| `GET /api/crew/status` | `CrewStatus` |
| `GET /api/crew/trace?limit=20` | `CrewTrace[]` (newest first) |
| `GET /api/auto-eventing` | `AutoEventingStatus` or 404 until built |

Errors: `{ "detail": "plain words" }` with 400 or 404 (429 for a seek or reset
inside the 0.5 s throttle, or more than about 2 POSTs a second, bursts of 10,
from one client IP; 503 while the match is still loading, 500 with a generic
message if something breaks on our side).
API responses carry `Cache-Control: no-store`.

## Server settings

| env | default | meaning |
|---|---|---|
| `MATCHMIND_ALLOWED_ORIGINS` | `http://localhost:5173,http://localhost:3000` | comma-separated CORS and WebSocket origins; `*` is ignored |
| `MATCHMIND_MATCH_FILE` | `backend/data/matches/MM-DEMO-001.jsonl` | the match to play |
| `MATCHMIND_STATIC_DIR` | `./static` (working directory) | built frontend served at `/` when it has an `index.html` |
| `MATCHMIND_BASE_RATE` | `10` | match seconds per real second at 1x |
| `MATCHMIND_AI_ENABLED` | `false` | `true`, `1` or `yes` (any case): live crew uses the paid model client; the whole-match bookmark pass always uses templates. Model recaps are only made at full time, once per persona, language and favourite club |
| `MATCHMIND_AI_BUDGET` | `300` | most paid model calls per process; then templates with `fallback_reason: 'budget'` |
| `MATCHMIND_AI_RATE_PER_MIN` | `30` | most paid model calls in any 60 s; then templates with `fallback_reason: 'budget'` |
| `MATCHMIND_PUBLIC_ORIGIN` | (none) | this server's own public origin (e.g. `https://pitchpulse.example`), allowed for the WebSocket only when the built frontend is served from `MATCHMIND_STATIC_DIR` |
| `MATCHMIND_MAX_CONNECTIONS` | `200` | most open WebSockets |
| `MATCHMIND_MAX_CONN_PER_IP` | `20` | most open WebSockets from one client IP |
| `MATCHMIND_HOST`, `PORT` / `MATCHMIND_PORT` | `127.0.0.1`, `8000` | `matchmind-api` / `python -m matchmind.api`; ASGI app `matchmind.api.app:app` |
