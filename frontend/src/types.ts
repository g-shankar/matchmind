export type EventType =
  | 'pass'
  | 'shot'
  | 'tackle'
  | 'interception'
  | 'pressure'
  | 'dribble'
  | 'foul'
  | 'goal'
  | 'turnover'
  | 'corner'
  | 'free_kick'
  | 'save';

export type PersonaType = 'casual' | 'tactical' | 'fantasy' | 'player_spotlight';

export type SupportedLanguage = 'en' | 'es' | 'fr' | 'ar' | 'ja';

export interface Coordinates {
  x: number; // 0 to 105
  y: number; // 0 to 68
}

export interface PlayerRef {
  id: string;
  name: string;
  jersey_number: number;
  position: string;
  team_name: string;
  speed_kmh: number;
  distance_covered_km: number;
}

export interface BallTelemetry {
  speed_kmh: number;
  airborne: boolean;
  distance_meters: number;
}

export interface MatchContext {
  under_pressure: boolean;
  pressure_intensity: number;
  opponents_in_lane: number;
  phase_of_play: string;
  pitch_zone: string;
}

export interface AutoEventDetection {
  model_name: string;
  confidence_score: number;
  inference_latency_ms: number;
  auto_detected: boolean;
}

export interface MatchEvent {
  event_id: string;
  match_id: string;
  match_clock: string;
  timestamp_seconds: number;
  period: number;
  event_type: EventType;
  team: string;
  player: PlayerRef;
  receiver?: PlayerRef;
  location: Coordinates;
  end_location?: Coordinates;
  telemetry: BallTelemetry;
  context: MatchContext;
  pass_difficulty_index?: number;
  pass_completed?: boolean;
  is_line_breaking?: boolean;
  expected_threat_delta?: number;
  speed_milestone_triggered?: boolean;
  speed_milestone_desc?: string;
  auto_detection?: AutoEventDetection;
  commentary?: string;
  translations?: Record<string, string>;
}

export interface ControlChaosState {
  home_control_pct: number;
  away_control_pct: number;
  chaos_index: number;
  current_tempo: string;
  rolling_momentum_home: number;
}

export interface MatchInsight {
  insight_id: string;
  event_id: string;
  match_clock: string;
  timestamp_seconds?: number;
  headline: string;
  why_it_matters: string;
  tactical_explanation: string;
  persona: PersonaType;
  language: SupportedLanguage;
  significance_score: number;
  highlight_player_id?: string;
  translated_versions: Record<string, string>;
  translations?: Record<string, { headline: string; why_it_matters: string; tactical_explanation: string }>;
}

export interface MatchRecap {
  match_id: string;
  title: string;
  headline: string;
  summary_paragraphs: string[];
  tactical_breakdown: string[];
  key_turning_points: string[];
  player_of_the_match: string;
  control_vs_chaos_summary: string;
  persona: PersonaType;
  generated_at_clock: string;
}
