from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum

class EventType(str, Enum):
    PASS = "pass"
    SHOT = "shot"
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    PRESSURE = "pressure"
    DRIBBLE = "dribble"
    FOUL = "foul"
    GOAL = "goal"
    TURNOVER = "turnover"
    CORNER = "corner"
    FREE_KICK = "free_kick"
    SAVE = "save"

class PersonaType(str, Enum):
    CASUAL = "casual"
    TACTICAL = "tactical"
    FANTASY = "fantasy"
    PLAYER_SPOTLIGHT = "player_spotlight"

class SupportedLanguage(str, Enum):
    EN = "en"
    ES = "es"
    FR = "fr"
    AR = "ar"
    JA = "ja"

class Coordinates(BaseModel):
    x: float = Field(..., description="Pitch X coordinate (0.0 to 105.0 meters)")
    y: float = Field(..., description="Pitch Y coordinate (0.0 to 68.0 meters)")

class PlayerRef(BaseModel):
    id: str
    name: str
    jersey_number: int
    position: str  # GK, CB, LB, RB, DM, CM, CAM, LW, RW, ST
    team_name: str
    speed_kmh: float = 0.0
    distance_covered_km: float = 0.0

class BallTelemetry(BaseModel):
    speed_kmh: float = Field(..., description="Ball speed in km/h")
    airborne: bool = False
    distance_meters: float

class MatchContext(BaseModel):
    under_pressure: bool
    pressure_intensity: float = Field(..., ge=0.0, le=1.0) # 0.0 to 1.0
    opponents_in_lane: int = 0
    phase_of_play: str # "Build-up", "High Press", "Counter-Attack", "Settled Defence", "Set Piece"
    pitch_zone: str # "Defensive Third", "Middle Third", "Attacking Third", "Penalty Box"

class AutoEventDetection(BaseModel):
    model_name: str = "Azure-Vision-YOLO-PitchTrack"
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    inference_latency_ms: float
    auto_detected: bool = True

class MatchEvent(BaseModel):
    event_id: str
    match_id: str
    match_clock: str  # e.g. "23:45"
    timestamp_seconds: float
    period: int  # 1 or 2
    event_type: EventType
    team: str
    player: PlayerRef
    receiver: Optional[PlayerRef] = None
    location: Coordinates
    end_location: Optional[Coordinates] = None
    telemetry: BallTelemetry
    context: MatchContext
    
    # Calculated Real-time Analytics
    pass_difficulty_index: Optional[float] = None # 0.0 to 1.0
    pass_completed: Optional[bool] = None
    is_line_breaking: Optional[bool] = False
    expected_threat_delta: Optional[float] = 0.0
    speed_milestone_triggered: Optional[bool] = False
    speed_milestone_desc: Optional[str] = None
    
    # Auto-eventing metadata
    auto_detection: Optional[AutoEventDetection] = None
    
    # Natural language live play-by-play commentary
    commentary: Optional[str] = None

class ControlChaosState(BaseModel):
    home_control_pct: float # 0 to 100
    away_control_pct: float # 0 to 100
    chaos_index: float # -1.0 (pure chaos) to +1.0 (pure control)
    current_tempo: str # "Slow", "Methodical", "High Intensity", "Furious Chaos"
    rolling_momentum_home: float # -100 to +100

class MatchInsight(BaseModel):
    insight_id: str
    event_id: str
    match_clock: str
    headline: str
    why_it_matters: str
    tactical_explanation: str
    persona: PersonaType
    language: SupportedLanguage = SupportedLanguage.EN
    significance_score: int = Field(..., ge=1, le=10) # 1 to 10
    highlight_player_id: Optional[str] = None
    translated_versions: Dict[str, str] = Field(default_factory=dict) # lang_code -> headline/text

class MatchRecap(BaseModel):
    match_id: str
    title: str
    headline: str
    summary_paragraphs: List[str]
    tactical_breakdown: List[str]
    key_turning_points: List[str]
    player_of_the_match: str
    control_vs_chaos_summary: str
    persona: PersonaType
    generated_at_clock: str

class MatchSnapshot(BaseModel):
    match_id: str
    clock: str
    period: int
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    latest_event: Optional[MatchEvent] = None
    control_chaos: ControlChaosState
    recent_insights: List[MatchInsight] = []
    active_recap: Optional[MatchRecap] = None
