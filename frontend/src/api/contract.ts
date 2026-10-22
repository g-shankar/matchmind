// TypeScript view of the PitchPulse API contract (docs/API-CONTRACT.md, v1).
// Keep in step with backend/src/matchmind/crew/contracts.py and stats/models.py.

// Studio languages have hand-written phrase packs. World languages are written in
// English by the crew, translated by Azure AI Translator and fact-checked again;
// with the translator off they arrive in English (docs/LANGUAGES.md).
export type StudioLanguage = 'en' | 'es' | 'fr' | 'ar' | 'ja';
export type WorldLanguage = 'pt' | 'de' | 'hi' | 'zh-Hans' | 'sw' | 'id' | 'tr' | 'ko';
export type Language = StudioLanguage | WorldLanguage;
export type TranslatedBy = 'azure_ai_translator';

export interface LanguageInfo {
  code: Language;
  /** The language's own name, e.g. 'Português'. */
  name: string;
  english_name: string;
  source: 'studio' | 'translator';
  available: boolean;
  rtl: boolean;
  /** Why it cannot be shown now. 'not_in_demo' only comes from the offline demo. */
  reason: 'translator_off' | 'not_in_demo' | null;
}

export interface TranslatorStatus {
  mode: 'azure' | 'off';
  available: boolean;
  breaker_open: boolean;
  cache_hits: number;
  translated: number;
  fallbacks: number;
  rejections: number;
}
export type PersonaType = 'casual' | 'tactical' | 'fantasy' | 'player_spotlight';
export type FocusMetric = 'pressure' | 'xg' | 'pass_difficulty' | 'top_speed' | 'momentum';
export type MomentKind =
  | 'goal'
  | 'card'
  | 'big_chance'
  | 'better_option'
  | 'unfound_run'
  | 'momentum_swing'
  | 'pressure_spell'
  | 'speed_burst'
  | 'rocket_shot'
  | 'distance_milestone'
  | 'hard_pass'
  | 'key_tackle'
  | 'milestone';
export type Slot = 'lower_third' | 'side_panel' | 'pitch_tag' | 'metric_alert' | 'full_screen';
export type FactValue = string | number | boolean;
export type ProducedBy = 'ai' | 'template';

export interface XY {
  x: number;
  y: number;
}

export interface PlayerInfo {
  player_id: string;
  name: string;
  number: number;
  position: string;
  line: 'GK' | 'DEF' | 'MID' | 'FWD';
}

/** A player's resolved identity on moments and cards (server: crew.contracts.PlayerRef). */
export interface PlayerIdentity {
  player_id: string;
  name: string;
  number: number;
  team: string;
  position: string;
}

export interface TeamInfo {
  team_id: string;
  name: string;
  short_name: string;
  primary_color: string;
  secondary_color: string;
  formation: string;
  style: string;
  players: PlayerInfo[];
}

export interface Teams {
  home: TeamInfo;
  away: TeamInfo;
}

export interface ViewerProfile {
  persona: PersonaType;
  language: Language;
  favourite_team: string | null;
  focus_player_id: string | null;
  focus_metric: FocusMetric | null;
}

export interface Evidence {
  /** Stable fact key, e.g. times_better (the label itself is already in the card's language). */
  label_key?: string;
  label: string;
  value: FactValue;
  unit: string | null;
  source_event_id: string | null;
}

export type EventType =
  | 'pass'
  | 'carry'
  | 'dribble'
  | 'shot'
  | 'run'
  | 'interception'
  | 'tackle'
  | 'clearance'
  | 'recovery'
  | 'foul'
  | 'card'
  | 'milestone'
  | 'match_start'
  | 'period_start'
  | 'period_end'
  | 'match_end';

export interface EventMetrics {
  pass_distance_m: number | null;
  pass_difficulty: number | null;
  progressive: boolean;
  ball_speed_kmh: number | null;
  player_speed_kmh: number | null;
  sprint: boolean;
  fast_shot: boolean;
  chance_quality: number | null;
  distance_to_goal_m: number | null;
  pitch_zone: string | null;
  xt_delta: number | null;
}

export interface MatchEvent {
  event_id: string;
  seq: number;
  match_clock: string;
  clock_s: number;
  period: 1 | 2;
  type: EventType;
  team: string | null;
  player_id: string | null;
  receiver_id: string | null;
  start: XY | null;
  end: XY | null;
  outcome: string | null;
  under_pressure: boolean;
  details: Record<string, FactValue>;
  metrics: EventMetrics;
}

export interface TeamWindow {
  possession_pct: number;
  field_tilt_pct: number;
  pressure_index: number;
  shots: number;
  xg: number;
  final_third_passes: number;
  box_entries: number;
}

export interface MatchState {
  match_id: string;
  clock_s: number;
  match_clock: string;
  period: number;
  home_id: string;
  away_id: string;
  score_home: number;
  score_away: number;
  home: TeamWindow;
  away: TeamWindow;
  momentum: number;
  control_chaos: number;
  tempo: string;
  events_per_min: number;
  turnovers_per_min: number;
  avg_chain_passes: number;
  xg_home: number;
  xg_away: number;
  shots_home: number;
  shots_away: number;
}

export interface ControlChaosState {
  home_control_pct: number;
  away_control_pct: number;
  chaos_index: number;
  current_tempo: string;
  rolling_momentum_home: number;
}

/** Where distance, speed bands, sprints and top speed came from (docs/METRICS.md). */
export type PhysicalSource = 'synthetic_tracking' | 'event_estimate';

export interface PlayerStats {
  player_id: string;
  team: string;
  /** Identity from the squads (sent by the server; optional in older fixtures). */
  name?: string | null;
  number?: number | null;
  position?: string | null;
  touches: number;
  passes: number;
  passes_completed: number;
  pass_accuracy: number;
  key_passes: number;
  shots: number;
  shots_on_target?: number;
  goals: number;
  assists: number;
  xg: number;
  xa: number;
  tackles_won: number;
  /** Dribbled past by the ball carrier. */
  tackles_lost?: number;
  tackles_attempted?: number;
  tackle_success_pct?: number;
  interceptions: number;
  top_speed_kmh: number;
  sprints: number;
  distance_km: number;
  walk_km?: number;
  jog_km?: number;
  run_km?: number;
  sprint_km?: number;
  physical_source?: PhysicalSource;
  carry_distance_m: number;
}

/** GET /api/match/stats/basic */
export interface BasicTeamStats {
  team_id: string;
  name: string;
  possession_pct: number;
  passes_completed: number;
  passes_attempted: number;
  pass_accuracy_pct: number | null;
  shots: number;
  shots_on_target: number;
  goals: number;
  tackles_won: number;
  tackles_attempted: number;
  interceptions: number;
  fouls: number;
  ppda: number | null;
  ppda_opponent_passes: number;
  ppda_defensive_actions: number;
  distance_km: number;
  top_speed_kmh: number;
}

export interface BasicPlayerStats {
  player_id: string;
  team: string;
  name: string | null;
  number: number | null;
  position: string | null;
  passes_completed: number;
  passes_attempted: number;
  pass_accuracy_pct: number | null;
  shots: number;
  shots_on_target: number;
  goals: number;
  tackles_won: number;
  tackles_attempted: number;
  interceptions: number;
  distance_km: number;
  sprints: number;
  top_speed_kmh: number;
}

export interface BasicStats {
  match_id: string;
  clock: string;
  period: number;
  pass_accuracy_denominator: string;
  physical_source: PhysicalSource;
  physical_label: string;
  teams: Record<string, BasicTeamStats>;
  players: BasicPlayerStats[];
}

export type MetricQuality = 'counted' | 'calibrated' | 'heuristic' | 'estimated_from_synthetic_tracking';

/** GET /api/metrics: the metric registry. */
export interface MetricRegistry {
  quality_flags: Record<MetricQuality, string>;
  metrics: {
    id: string;
    name: string;
    scope: 'event' | 'window' | 'player' | 'team' | 'moment';
    formula: string;
    symbols: string;
    units: string;
    source_events: string[];
    window: string;
    range: string;
    quality: MetricQuality;
    limitations: string;
    edge_cases: string;
    fields: string[];
  }[];
  not_computed: { id: string; name: string; reason: string }[];
}

export interface BetterOptionReplay {
  shot_event_id: string;
  shooter_id: string;
  teammate_id: string;
  shot_chance_quality: number;
  alt_chance_quality: number;
  pass_success: number;
  alt_value: number;
  times_better: number;
  pass_distance_m: number;
  nearest_marker_m: number;
  shooter_pos: XY;
  teammate_pos: XY;
  defenders: XY[];
  keeper: XY | null;
}

export interface UnfoundRunReplay {
  run_event_id: string;
  runner_id: string;
  carrier_id: string;
  found: boolean;
  pass_on_at_s: number;
  pass_on_clock: string;
  clear_of_line_m: number;
  projected_chance_quality: number;
  one_on_one: boolean;
  carrier_pos: XY;
  runner_path: XY[];
  target: XY;
  defenders_at_pass: XY[];
}

export type Replay = BetterOptionReplay | UnfoundRunReplay;

export const isBetterOption = (r: Replay | null | undefined): r is BetterOptionReplay =>
  !!r && 'shot_event_id' in r;
export const isUnfoundRun = (r: Replay | null | undefined): r is UnfoundRunReplay =>
  !!r && 'run_event_id' in r;

export interface OverlayCard {
  card_id: string;
  moment_id: string;
  kind: MomentKind;
  slot: Slot;
  priority: number;
  show_at_s: number;
  duration_s: number;
  persona: PersonaType;
  language: Language;
  rtl: boolean;
  headline: string;
  body: string;
  why: string;
  tactical_tag: string;
  evidence: Evidence[];
  player_ids: string[];
  /** Identity of each player in player_ids, same order. */
  players?: PlayerIdentity[];
  team: string | null;
  favourite_side: boolean | null;
  produced_by: ProducedBy;
  fallback_reason: string | null;
  replay: Replay | null;
  /** Language the text is really in: `language`, or 'en' when a world language could not be translated. */
  text_language?: Language | null;
  translated_by?: TranslatedBy | null;
}

export interface Bookmark {
  moment_id: string;
  kind: MomentKind;
  match_clock: string;
  clock_s: number;
  period: number;
  title: string;
}

export interface Recap {
  match_id: string;
  persona: PersonaType;
  language: Language;
  rtl: boolean;
  title: string;
  headline: string;
  summary_paragraphs: string[];
  key_moments: { match_clock: string; kind: MomentKind; headline: string; moment_id: string }[];
  player_of_the_match_id: string | null;
  player_of_the_match: string | null;
  stats: Record<string, FactValue>;
  generated_at_clock: string;
  produced_by: ProducedBy;
  fact_check: { ok: boolean; reasons: string[] };
  text_language?: Language | null;
  translated_by?: TranslatedBy | null;
  fallback_reason?: string | null;
}

export interface CrewStatus {
  mode: ProducedBy;
  model: string | null;
  breakers_open: string[];
  moments: number;
  fallbacks: number;
  rejections: number;
  translator?: TranslatorStatus;
  /** Who runs the model steps: "templates", Azure OpenAI, or Foundry Agent Service agents. */
  provider?: "templates" | "azure_openai" | "foundry_agents";
  /** Who chains the agents: in process, or Microsoft Agent Framework workflows. */
  orchestrator?: "in_process" | "agent_framework";
}

export interface CrewTrace {
  moment_id: string;
  match_clock: string;
  steps: {
    agent: string;
    ms: number;
    status: 'ok' | 'fallback' | 'rejected' | 'error' | 'skipped';
    detail: string | null;
  }[];
}

export interface AutoEventingStatus {
  source: 'synthetic_tracking';
  label: string;
  passes_detected_pct: number;
  speed_mae_kmh: number;
  events_checked: number;
  // Added by the synthetic tracking-to-event benchmark. All optional, so older servers still type-check.
  name?: string;
  match_id?: string | null;
  speed_mae_ci_kmh?: [number, number] | null;
  classes?: BenchmarkClassRow[] | null;
  pressure?: BenchmarkClassRow | null;
  confusion?: BenchmarkConfusion | null;
  baseline?: { name: string; classes: BenchmarkClassRow[] } | null;
  pixel_path?: PixelPathRow | null;
  caveat?: string | null;
}

export type BenchmarkKind = 'pass' | 'shot' | 'clearance' | 'tackle' | 'interception' | 'recovery' | 'pressure';

export interface BenchmarkClassRow {
  kind: BenchmarkKind;
  support: number; // true events of this kind
  detected: number;
  matched: number;
  precision: number; // 0-1
  recall: number; // 0-1
  f1: number;
  precision_ci: [number, number] | null; // 95% Wilson interval
  recall_ci: [number, number] | null;
}

// Rows: true kinds then 'spurious'; columns: detected kinds then 'missed'.
export interface BenchmarkConfusion {
  rows: string[];
  columns: string[];
  counts: number[][];
}

// Rendered synthetic top-down video, not broadcast footage; no real-video model.
export interface PixelPathRow {
  label: string;
  window_s: number;
  frames: number;
  width_px: number;
  height_px: number;
  player_error_m: number | null;
  ball_error_m: number | null;
  ball_found_pct: number;
  coordinate: BenchmarkClassRow[];
  pixels: BenchmarkClassRow[];
  speed_mae_kmh_coordinate: number | null;
  speed_mae_kmh_pixels: number | null;
}

export type SpeedMultiplier = 1 | 10 | 60;

// Clock is not monotonic: first-half stoppage runs past 2700 s and the second half restarts at 2700 s.
// 1 real second = 10 x speed_multiplier match seconds.
export interface Playback {
  is_running: boolean;
  speed_multiplier: SpeedMultiplier;
  clock_s: number;
  match_clock: string;
  period: number;
  ended: boolean;
}

export interface SnapshotData {
  match_id: string;
  clock: string;
  period: number;
  home_score: number;
  away_score: number;
  teams: Teams;
  state: MatchState;
  control_chaos: ControlChaosState;
  profile: ViewerProfile;
  playback: Playback;
  recent_cards: OverlayCard[];
  bookmarks: Bookmark[];
  players: PlayerStats[];
  crew: CrewStatus;
  /** Every language the viewer can pick, and whether it can be shown now. */
  languages?: LanguageInfo[];
  auto_eventing: AutoEventingStatus | null;
}

export interface TickData {
  event: MatchEvent;
  clock: string;
  period: number;
  score: { home: number; away: number };
  state: MatchState;
  control_chaos: ControlChaosState;
  cards: OverlayCard[];
  players_changed: PlayerStats[];
}

export type ServerMessage =
  | { type: 'INITIAL_SNAPSHOT'; data: SnapshotData }
  | { type: 'MATCH_TICK'; data: TickData }
  | { type: 'PLAYBACK_CONTROL'; data: Playback }
  | { type: 'MATCH_RESET'; data: Record<string, never> }
  | { type: 'PROFILE_CHANGED'; data: ViewerProfile }
  | { type: 'PERSONA_CHANGED'; data: { persona: PersonaType } }
  | { type: 'MATCH_END'; data: { recap: Recap } }
  | { type: 'ERROR'; data: { message: string } };

export type ClientAction =
  | { action: 'toggle_pause' }
  | { action: 'set_speed'; speed_multiplier: SpeedMultiplier }
  | { action: 'reset' }
  | { action: 'seek'; clock_s: number; period?: number }
  | ({ action: 'set_view' } & { [K in keyof ViewerProfile]?: ViewerProfile[K] | null })
  | { action: 'set_persona'; persona: PersonaType; spotlight_player_id?: string | null };
