from collections import deque
from typing import List, Tuple
from api.schemas import MatchEvent, EventType, ControlChaosState

class MomentumTracker:
    def __init__(self, window_size: int = 18):
        self.window_size = window_size
        self.events_window: deque[MatchEvent] = deque(maxlen=window_size)
        self.home_team_name = "Manchester Blue"
        self.away_team_name = "North London Red"
        self.current_home_momentum = 0.0 # -100 to +100

    def record_event(self, event: MatchEvent) -> ControlChaosState:
        self.events_window.append(event)
        return self.compute_state()

    def compute_state(self) -> ControlChaosState:
        if not self.events_window:
            return ControlChaosState(
                home_control_pct=50.0,
                away_control_pct=50.0,
                chaos_index=0.0,
                current_tempo="Methodical",
                rolling_momentum_home=0.0
            )

        events: List[MatchEvent] = list(self.events_window)
        total_events = len(events)
        
        home_events = [e for e in events if e.team == self.home_team_name]
        away_events = [e for e in events if e.team == self.away_team_name]
        
        # 1. Turnover frequency & rapid possession changes (Chaos driver)
        turnovers = sum(1 for e in events if e.event_type in [EventType.TURNOVER, EventType.TACKLE, EventType.INTERCEPTION])
        turnover_rate = turnovers / total_events if total_events > 0 else 0.0
        
        # 2. High-speed direct transitions (Chaos driver)
        high_speed_actions = sum(1 for e in events if e.telemetry.speed_kmh > 65.0)
        directness_ratio = high_speed_actions / total_events if total_events > 0 else 0.0
        
        # 3. Passing continuity (Control driver)
        consecutive_passes = 0
        max_consecutive_passes = 0
        current_streak = 0
        last_team = None
        for e in events:
            if e.event_type == EventType.PASS and e.pass_completed:
                if e.team == last_team:
                    current_streak += 1
                else:
                    current_streak = 1
                    last_team = e.team
                max_consecutive_passes = max(max_consecutive_passes, current_streak)
            else:
                current_streak = 0
                last_team = None

        # Chaos score: -1.0 (End-to-End Chaos) to +1.0 (Pure Positional Control)
        raw_chaos = (turnover_rate * 0.5) + (directness_ratio * 0.5) - (min(1.0, max_consecutive_passes / 8.0) * 0.6)
        # Normalize to [-1.0, 1.0]
        chaos_index = round(max(-1.0, min(1.0, 0.4 - (raw_chaos * 1.8))), 2)

        # Tempo classification
        if chaos_index < -0.4:
            tempo = "Furious Chaos"
        elif chaos_index < 0.1:
            tempo = "High-Tempo Transition"
        elif chaos_index < 0.5:
            tempo = "Methodical Control"
        else:
            tempo = "Total Positional Suffocation"

        # Field tilt / Possession weighting
        home_raw_weight = sum(1.5 if e.location.x > 52.5 else 1.0 for e in home_events)
        away_raw_weight = sum(1.5 if e.location.x < 52.5 else 1.0 for e in away_events)
        total_weight = home_raw_weight + away_raw_weight
        
        if total_weight > 0:
            home_pct = round((home_raw_weight / total_weight) * 100.0, 1)
            away_pct = round(100.0 - home_pct, 1)
        else:
            home_pct, away_pct = 50.0, 50.0

        # Momentum calculation: smooth rolling trajectory towards -100 (Away) to +100 (Home)
        target_momentum = (home_pct - 50.0) * 2.0 # -100 to +100
        # Add bonus for shots and goals in window
        home_shots = sum(1 for e in home_events if e.event_type in [EventType.SHOT, EventType.GOAL])
        away_shots = sum(1 for e in away_events if e.event_type in [EventType.SHOT, EventType.GOAL])
        target_momentum += (home_shots * 15.0) - (away_shots * 15.0)
        target_momentum = max(-100.0, min(100.0, target_momentum))

        # Exponential moving average for momentum
        self.current_home_momentum = round((self.current_home_momentum * 0.7) + (target_momentum * 0.3), 1)

        return ControlChaosState(
            home_control_pct=home_pct,
            away_control_pct=away_pct,
            chaos_index=chaos_index,
            current_tempo=tempo,
            rolling_momentum_home=self.current_home_momentum
        )
