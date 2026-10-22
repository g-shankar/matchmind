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
  | 'milestone'
  | 'correction';
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
  /** False: catch-up mode. The server leaves out the score, goals, VAR outcomes and
   * anything else that gives the result away until the viewer reveals it. */
  spoilers: boolean;
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
  | 'var_review'
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
  /** Catch-up mode: an opaque id (`ev-…`), the same one cards and answers point at. */
  event_id: string;
  /** Catch-up mode: null (the full feed's numbering would show where events were withheld). */
  seq: number | null;
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
  /** var_review only: the event the review decided on (a goal) and why. */
  reviewed_event_id?: string;
  review_reason?: 'offside' | 'handball' | 'foul' | null;
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
  /** Null for a viewer in catch-up mode (spoilers off). */
  score_home: number | null;
  score_away: number | null;
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
  /** Null for a viewer in catch-up mode (spoilers off). */
  goals: number | null;
  assists: number | null;
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
  /** Null in catch-up mode (`?spoilers=false`): a team's goals are the score. */
  goals: number | null;
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
  /** Null in catch-up mode (`?spoilers=false`): a team's goals are the score. */
  goals: number | null;
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

/** What the machine verified about one shown sentence (docs/TRUST.md). Tone and wording never are. */
export type ClaimCheck = 'verified_numeric' | 'verified_name' | 'unverified_text';
export type ClaimField = 'headline' | 'body' | 'why' | 'title' | 'paragraph' | 'key_moment';

export interface ClaimBinding {
  text: string;
  kind: 'number' | 'name' | 'text';
  fact_key: string | null;
  value: FactValue | null;
  unit: string | null;
  entity_id: string | null;
}

export interface Claim {
  sentence: string;
  field: ClaimField;
  fact_keys: string[];
  numbers: string[];
  source_event_ids: string[];
  check: ClaimCheck;
  reason: string;
  origin?: 'template' | 'matched';
  bindings?: ClaimBinding[];
}

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
  /** Correction cards only: moment ids this card rules out (their cards come down). */
  retracts?: string[];
  /** Each sentence of headline, body and why, tied to its facts and source events. */
  claims?: Claim[];
}

export interface Bookmark {
  moment_id: string;
  kind: MomentKind;
  match_clock: string;
  clock_s: number;
  period: number;
  title: string;
  /** True when a later correction (a VAR review) ruled this moment out. */
  ruled_out?: boolean;
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
  claims?: Claim[];
  /** True for the spoiler-free story so far (catch-up mode): no score, scorers or VAR outcomes. */
  spoiler_free?: boolean;
}

export interface AgentLatency {
  agent: string;
  samples: number;
  p50_ms: number;
  p95_ms: number;
  max_ms: number;
}

/** Rolling-window service levels; counts sit beside every rate. */
export interface CrewHealth {
  window: number;
  latency: AgentLatency[];
  model_steps: number;
  fallback_steps: number;
  fallback_rate: number | null;
  checks: number;
  rejected_checks: number;
  rejection_rate: number | null;
  moments_per_min: number;
}

export interface CrewStatus {
  mode: ProducedBy;
  model: string | null;
  breakers_open: string[];
  moments: number;
  fallbacks: number;
  rejections: number;
  translator?: TranslatorStatus;
  health?: CrewHealth;
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

// --- Cue sheet (docs/CUE-SHEET.md, backend/schema/cue.schema.json) ---------------------------

export type CueOp = 'show' | 'update' | 'retract' | 'supersede' | 'clear';
export type CueLayer = Slot | 'scorebug' | 'momentum_ribbon' | 'telestration';
export type CueCollision = 'replace' | 'queue' | 'stack' | 'latest';
export type CueReason = 'var_offside' | 'var_handball' | 'var_foul' | 'period_end' | 'full_time';

/** One instant on the engine's period-aware match clock. */
export interface CueTime {
  period: number;
  /** Period 2 starts at 2700; first-half stoppage runs past 2700 while period is still 1. */
  clock_s: number;
  match_clock: string;
  /** Seconds of play since kick-off, halves joined end to end: always increases. */
  t_s: number;
}

export interface CueShape {
  kind: 'arrow' | 'line' | 'polyline' | 'circle' | 'marker';
  role:
    | 'shooter'
    | 'shot_taken'
    | 'pass_on'
    | 'open_player'
    | 'defender'
    | 'keeper'
    | 'carrier'
    | 'runner_path'
    | 'through_ball'
    | 'target';
  points: XY[];
  radius_m?: number | null;
  dashed?: boolean;
}

export interface Cue {
  schema_version: '1.0';
  cue_id: string;
  seq: number;
  op: CueOp;
  layer: CueLayer | 'all';
  moment_id: string | null;
  kind: MomentKind | null;
  retracts: string[];
  supersedes: string[];
  clears: CueLayer[];
  reason: CueReason | null;
  start: CueTime;
  duration_s: number | null;
  end: CueTime | null;
  priority: number;
  collision: CueCollision;
  persona: PersonaType;
  language: Language;
  rtl: boolean;
  text: { headline: string; body: string; why: string; text_language: Language; claims?: Claim[] } | null;
  evidence: Evidence[];
  source_event_ids: string[];
  team: string | null;
  player_ids: string[];
  produced_by: ProducedBy | null;
  scorebug: { home_id: string; away_id: string; score_home: number; score_away: number } | null;
  ribbon: { momentum: number; pressure_home: number; pressure_away: number } | null;
  telestration: { frame: 'pitch_105x68'; shapes: CueShape[] } | null;
}

/** Where a viewer's cue sheet stands when a snapshot is sent: start local cue state from `active`. */
export interface CueSheetState {
  sheet_id: string;
  last_seq: number;
  active: Cue[];
}

export interface CuesData {
  sheet_id: string;
  cues: Cue[];
  /** Present when the server started a new sheet for this viewer: replace local cue state with it. */
  active?: Cue[];
}

/** GET /api/match/cue-sheet */
export interface CueSheetPage {
  schema_version: '1.0';
  match_id: string;
  sheet_id: string;
  persona: PersonaType;
  language: Language;
  position: CueTime | null;
  last_seq: number;
  since_seq: number;
  has_more: boolean;
  next_since_seq: number;
  cues: Cue[];
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
  /** Null for a viewer in catch-up mode (spoilers off). */
  home_score: number | null;
  away_score: number | null;
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
  /** This viewer's cue sheet: what is on air now (null on the REST snapshot). */
  cue_sheet?: CueSheetState | null;
  /** The last events played, oldest first, so the pitch is never empty after a jump. */
  recent_events?: MatchEvent[];
}

export interface TickData {
  event: MatchEvent;
  clock: string;
  period: number;
  /** Null for a viewer in catch-up mode (spoilers off). */
  score: { home: number; away: number } | null;
  state: MatchState;
  control_chaos: ControlChaosState;
  cards: OverlayCard[];
  players_changed: PlayerStats[];
}

export type ServerMessage =
  | { type: 'INITIAL_SNAPSHOT'; data: SnapshotData }
  | { type: 'MATCH_TICK'; data: TickData }
  | { type: 'CUES'; data: CuesData }
  | { type: 'PLAYBACK_CONTROL'; data: Playback }
  | { type: 'MATCH_RESET'; data: Record<string, never> }
  | { type: 'PROFILE_CHANGED'; data: ViewerProfile }
  | { type: 'PERSONA_CHANGED'; data: { persona: PersonaType } }
  | { type: 'MATCH_END'; data: { recap: Recap } }
  | { type: 'ERROR'; data: { message: string; code?: string } };

export type ClientAction =
  | { action: 'toggle_pause' }
  | { action: 'set_speed'; speed_multiplier: SpeedMultiplier }
  | { action: 'reset' }
  | { action: 'seek'; clock_s: number; period?: number }
  | ({ action: 'set_view' } & { [K in keyof ViewerProfile]?: ViewerProfile[K] | null })
  | { action: 'set_persona'; persona: PersonaType; spotlight_player_id?: string | null };

// --- Moment audit: GET /api/match/moment/{id}/audit (docs/TRUST.md) ---

export interface FactParity {
  ok: boolean;
  key_facts: string[];
  anchors: string[][];
  renderings: number;
  withheld: number;
  /** 'persona/language' (plus ' (live)' for live cards) -> key facts it states */
  stated: Record<string, string[]>;
  problems: string[];
}

export interface RenderingAudit {
  persona: PersonaType;
  language: Language;
  text_language: Language | null;
  source: 'template_sweep' | 'live';
  produced_by: ProducedBy;
  fallback_reason: string | null;
  translated_by: TranslatedBy | null;
  headline: string;
  body: string;
  why: string;
  fact_check: { ok: boolean; reasons: string[] };
  claims: Claim[];
}

export interface MomentAudit {
  moment_id: string;
  kind: MomentKind;
  match_clock: string;
  period: number;
  team: string | null;
  player_ids: string[];
  facts: Record<string, FactValue>;
  source_event_ids: string[];
  explanation: {
    moment_id: string;
    why: string;
    tactical_tag: string;
    evidence: Evidence[];
    produced_by: ProducedBy;
    fallback_reason: string | null;
  };
  renderings: RenderingAudit[];
  parity: FactParity;
  trace: CrewTrace['steps'];
  not_checked: string[];
  /** A correction: the moment ids it rules out. */
  retracts?: string[];
  /** A goal VAR later ruled out: the correction's moment id. */
  ruled_out_by?: string | null;
}

// --- Dataset index: GET /api/dataset (docs/DATASET.md) ---

export interface DatasetMatch {
  match_id: string;
  kind: 'bundled' | 'seeded';
  scenario: 'demo_storyline' | 'chance_model' | 'chance_model_with_beats';
  seed: number;
  home: string;
  away: string;
  /** Bundled only, e.g. '2-3'. */
  score: string | null;
  /** Bundled only. */
  events: number | null;
}

export type DatasetFormat = 'jsonl' | 'csv' | 'zip';

export interface DatasetIndex {
  synthetic: true;
  note: string;
  schema_version: string;
  pitch: { length_m: number; width_m: number; home_attacks: '+x' };
  formats: DatasetFormat[];
  tracking: { hz: number; max_window_s: number; formats: DatasetFormat[] };
  scenarios: Record<string, string>;
  seeded: { seed_start: number; seed_end: number; match_id: string };
  matches: DatasetMatch[];
}

// --- Ask the studio: POST /api/ask and the ask_studio MCP tool (docs/ASK.md) ---

/** Suggested questions: sent as an id, never as text. */
export type AskChip = 'score' | 'top_xg' | 'furthest' | 'fastest' | 'on_top' | 'better_option' | 'explain_xg';
export const ASK_CHIPS: AskChip[] = ['score', 'top_xg', 'furthest', 'fastest', 'on_top', 'better_option', 'explain_xg'];
export const ASK_MAX_CHARS = 200;

export type AskStatus = 'answered' | 'refused' | 'hidden' | 'clarify' | 'not_yet';
export type AskRefusal =
  | 'empty'
  | 'too_long'
  | 'markup'
  | 'injection'
  | 'off_topic'
  | 'unknown_player'
  | 'real_name'
  | 'fact_check';

export interface AskRequest {
  question?: string;
  chip?: AskChip;
  lang: Language;
  spoilers: boolean;
}

export interface AskAnswer {
  status: AskStatus;
  reason: AskRefusal | null;
  intent: { kind: string; team: string | null; player_id: string | null; metric: string | null } | null;
  understood_by: 'chip' | 'rules' | 'model' | null;
  /** Plain text: render as text, never as HTML. */
  answer: string;
  language: Language;
  text_language: Language;
  rtl: boolean;
  as_of: { clock: string; period: number; clock_s: number; ended: boolean };
  spoilers: boolean;
  facts?: Record<string, FactValue>;
  evidence: Evidence[];
  claims?: Claim[];
  source_event_ids?: string[];
  moment_ids: string[];
  metric: { id: string; name: string; formula: string; quality: string } | null;
  produced_by: 'template';
  fact_check: { ok: boolean; reasons: string[] };
}

/** Why an answer could not be fetched at all (shown as one plain sentence). */
export type AskFailure = 'needs_live' | 'busy' | 'unavailable';
export type AskResult = { ok: true; answer: AskAnswer } | { ok: false; failure: AskFailure };
