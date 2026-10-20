import random
import uuid
import math
from typing import Optional, Dict, Any, Tuple
from api.schemas import (
    MatchEvent, EventType, Coordinates, PlayerRef, BallTelemetry,
    MatchContext, MatchSnapshot, ControlChaosState
)
from simulation.teams_data import TEAMS_DATA
from simulation.auto_eventer import AutoEventVisionPipeline
from ai.translator import AzureMultilingualTranslator
from analytics.metrics_engine import (
    calculate_pass_difficulty, check_line_breaking_pass,
    evaluate_speed_milestones, get_xt_value
)

class SyntheticMatchSimulator:
    """
    Advanced Markov-state synthetic football simulator.
    Simulates high-fidelity Premier League match events, spatial vectors,
    player fatigue/speed telemetry, and momentum swings.
    """
    def __init__(self, match_id: str = "PL-SYNTH-2026-MCI-ARS"):
        self.match_id = match_id
        self.clock_seconds: float = 0.0
        self.period: int = 1
        self.home_team_name = "Manchester Blue"
        self.away_team_name = "North London Red"
        self.possession_team = self.home_team_name
        self.ball_x: float = 52.5
        self.ball_y: float = 34.0
        self.home_score = 0
        self.away_score = 0
        self.vision_pipeline = AutoEventVisionPipeline()
        self.translator = AzureMultilingualTranslator()
        self.sequence_pass_count = 0

    def reset(self):
        self.clock_seconds = 0.0
        self.period = 1
        self.home_score = 0
        self.away_score = 0
        self.ball_x = 52.5
        self.ball_y = 34.0
        self.possession_team = self.home_team_name
        self.sequence_pass_count = 0

    def generate_next_event(self) -> MatchEvent:
        """Generates the next sequential match event."""
        # 1. Advance clock by 3.5 to 8.5 seconds
        delta_t = round(random.uniform(3.5, 8.5), 1)
        self.clock_seconds += delta_t
        if self.clock_seconds > 2700.0 and self.period == 1:
            self.period = 2
            self.clock_seconds = 2700.0

        mins = int(self.clock_seconds // 60)
        secs = int(self.clock_seconds % 60)
        clock_str = f"{mins:02d}:{secs:02d}"

        is_home = (self.possession_team == self.home_team_name)
        active_team_data = TEAMS_DATA[self.possession_team]
        defending_team_name = self.away_team_name if is_home else self.home_team_name
        defending_team_data = TEAMS_DATA[defending_team_name]

        # 2. Determine Pitch Zone
        # Home attacks left-to-right (0 -> 105), Away attacks right-to-left (105 -> 0)
        norm_attack_x = self.ball_x if is_home else (105.0 - self.ball_x)
        if norm_attack_x < 35.0:
            pitch_zone = "Defensive Third"
            phase_of_play = "Build-up"
        elif norm_attack_x < 70.0:
            pitch_zone = "Middle Third"
            phase_of_play = "High Press" if random.random() < 0.4 else "Controlled Possession"
        elif norm_attack_x < 90.0:
            pitch_zone = "Attacking Third"
            phase_of_play = "Creation & Overload"
        else:
            pitch_zone = "Penalty Box"
            phase_of_play = "Chance Creation"

        # 3. Determine Event Type via Tactical Probabilities
        rand = random.random()
        if pitch_zone == "Penalty Box":
            if rand < 0.55:
                event_type = EventType.SHOT
            elif rand < 0.75:
                event_type = EventType.PASS
            else:
                event_type = EventType.TACKLE
        elif pitch_zone == "Attacking Third":
            if rand < 0.28:
                event_type = EventType.SHOT
            elif rand < 0.72:
                event_type = EventType.PASS
            elif rand < 0.88:
                event_type = EventType.DRIBBLE
            else:
                event_type = EventType.TURNOVER
        else:
            if rand < 0.78:
                event_type = EventType.PASS
            elif rand < 0.88:
                event_type = EventType.PRESSURE
            elif rand < 0.95:
                event_type = EventType.TACKLE
            else:
                event_type = EventType.TURNOVER

        # 4. Select Passer and Receiver
        players = active_team_data["players"]
        outfield_players = [p for p in players if p.position != "GK"]

        # Select contextual player based on pitch location
        if pitch_zone in ["Defensive Third"]:
            eligible = [p for p in players if p.position in ["GK", "CB", "LB", "RB", "DM"]]
        elif pitch_zone in ["Middle Third"]:
            eligible = [p for p in outfield_players if p.position in ["DM", "CM", "CAM", "LB", "RB"]]
        else:
            eligible = [p for p in outfield_players if p.position in ["CAM", "LW", "RW", "ST"]]

        primary_player = random.choice(eligible if eligible else outfield_players)
        
        # Update player physical stats
        primary_player.distance_covered_km += round(delta_t * 0.0028, 3)
        primary_player.speed_kmh = round(random.uniform(22.0, 34.5), 1)

        start_x, start_y = self.ball_x, self.ball_y
        under_pressure = random.random() < (0.65 if pitch_zone in ["Attacking Third", "Penalty Box"] else 0.35)
        pressure_intensity = round(random.uniform(0.65, 0.95), 2) if under_pressure else round(random.uniform(0.1, 0.4), 2)
        opponents_in_lane = random.randint(1, 3) if under_pressure else random.randint(0, 1)

        # 5. Resolve Action Trajectory
        pass_completed = True
        receiver = None
        speed_milestone_desc = None
        is_line_breaking = False

        if event_type == EventType.PASS:
            self.sequence_pass_count += 1
            other_players = [p for p in outfield_players if p.id != primary_player.id]
            receiver = random.choice(other_players)
            receiver.speed_kmh = round(random.uniform(18.0, 31.0), 1)
            receiver.distance_covered_km += round(delta_t * 0.002, 3)

            # Directional vector
            progression = random.uniform(6.0, 28.0) * (1.0 if is_home else -1.0)
            lateral = random.uniform(-18.0, 18.0)
            end_x = max(2.0, min(103.0, start_x + progression))
            end_y = max(2.0, min(66.0, start_y + lateral))

            # Auto-event vision processing
            vision_result = self.vision_pipeline.process_frame(
                event_type, Coordinates(x=start_x, y=start_y), Coordinates(x=end_x, y=end_y), delta_t
            )
            telemetry = vision_result["telemetry"]
            auto_detection = vision_result["detection"]

            # Calculate PDR
            pdr = calculate_pass_difficulty(
                Coordinates(x=start_x, y=start_y),
                Coordinates(x=end_x, y=end_y),
                pressure_intensity,
                opponents_in_lane,
                telemetry.airborne
            )

            # Did the pass succeed? (Realistic 80-92% completion probability)
            completion_prob = max(0.68, min(0.95, 1.0 - (pdr * 0.32)))
            if random.random() < completion_prob:
                # Pass completed!
                pass_completed = True
                self.ball_x, self.ball_y = end_x, end_y
                is_line_breaking = check_line_breaking_pass(
                    Coordinates(x=start_x, y=start_y), Coordinates(x=end_x, y=end_y), is_home, opponents_in_lane
                )
            else:
                # Interception or failed reception
                pass_completed = False
                event_type = EventType.INTERCEPTION
                self.possession_team = defending_team_name
                self.sequence_pass_count = 0
                self.ball_x, self.ball_y = end_x, end_y

            has_milestone, milestone_desc = evaluate_speed_milestones(EventType.PASS, telemetry.speed_kmh)
            speed_milestone_desc = milestone_desc

        elif event_type == EventType.SHOT:
            self.sequence_pass_count = 0
            goal_x = 105.0 if is_home else 0.0
            goal_y = 34.0
            end_x, end_y = goal_x, goal_y + random.uniform(-5.0, 5.0)

            vision_result = self.vision_pipeline.process_frame(
                event_type, Coordinates(x=start_x, y=start_y), Coordinates(x=end_x, y=end_y), 0.7
            )
            telemetry = vision_result["telemetry"]
            telemetry.speed_kmh = round(random.uniform(92.0, 118.5), 1)
            auto_detection = vision_result["detection"]
            pdr = None

            # Calculate goal probability (xG proxy based on distance & angle)
            dist_to_goal = math.sqrt((goal_x - start_x)**2 + (34.0 - start_y)**2)
            xg = max(0.04, min(0.75, 1.0 - (dist_to_goal / 30.0)))
            
            if random.random() < xg:
                event_type = EventType.GOAL
                if is_home:
                    self.home_score += 1
                else:
                    self.away_score += 1
                # Reset to center spot for kickoff
                self.ball_x, self.ball_y = 52.5, 34.0
                self.possession_team = defending_team_name
            else:
                # Save or miss
                self.possession_team = defending_team_name
                self.ball_x = 5.0 if is_home else 100.0
                self.ball_y = 34.0

            has_milestone, speed_milestone_desc = evaluate_speed_milestones(EventType.SHOT, telemetry.speed_kmh)

        else: # TACKLE, TURNOVER, PRESSURE, DRIBBLE
            self.sequence_pass_count = 0
            end_x = start_x + random.uniform(-4.0, 4.0)
            end_y = start_y + random.uniform(-4.0, 4.0)
            vision_result = self.vision_pipeline.process_frame(
                event_type, Coordinates(x=start_x, y=start_y), Coordinates(x=end_x, y=end_y), 1.0
            )
            telemetry = vision_result["telemetry"]
            auto_detection = vision_result["detection"]
            pdr = None
            if event_type in [EventType.TACKLE, EventType.TURNOVER]:
                self.possession_team = defending_team_name
                self.ball_x, self.ball_y = end_x, end_y
            has_milestone = False

        # 6. Expected Threat Delta (xT)
        start_xt = get_xt_value(start_x, start_y, is_home)
        end_xt = get_xt_value(end_x, end_y, is_home)
        xt_delta = round(end_xt - start_xt, 4)

        # 7. Generate Live Play-by-Play Natural Language Commentary
        if event_type == EventType.GOAL:
            commentary = f"GOAL! {primary_player.name} fires into the net ({telemetry.speed_kmh:.1f} km/h) for {active_team_data['name']}!"
        elif event_type == EventType.SHOT:
            commentary = f"{primary_player.name} takes aim from {dist_to_goal:.1f}m! Ferocious strike ({telemetry.speed_kmh:.1f} km/h) directed towards goal."
        elif event_type == EventType.PASS:
            if is_line_breaking:
                commentary = f"Pinpoint line-breaking pass! {primary_player.name} cuts through the block to find {receiver.name} ({telemetry.distance_meters:.1f}m)."
            elif telemetry.speed_kmh > 70:
                commentary = f"High-velocity delivery by {primary_player.name} ({telemetry.speed_kmh:.1f} km/h) into {receiver.name} in the {pitch_zone.lower()}."
            else:
                commentary = f"{primary_player.name} circulates possession with a {telemetry.distance_meters:.1f}m pass to {receiver.name}."
        elif event_type == EventType.INTERCEPTION:
            commentary = f"{defending_team_name} defensive block steps up to intercept the forward ball from {primary_player.name}."
        elif event_type == EventType.TACKLE:
            commentary = f"Firm tackle by {primary_player.name} dispossessing the attack in the {pitch_zone.lower()}."
        elif event_type == EventType.PRESSURE:
            commentary = f"{primary_player.name} applies suffocating high pressure ({int(pressure_intensity*100)}% intensity)."
        elif event_type == EventType.DRIBBLE:
            commentary = f"{primary_player.name} carries the ball forward with progressive dribble ({telemetry.speed_kmh:.1f} km/h)."
        else:
            commentary = f"Turnover in the {pitch_zone.lower()} as {primary_player.name} loses control under defensive press."

        # Category for translations
        cat = (
            "goal" if event_type == EventType.GOAL else
            "shot" if event_type == EventType.SHOT else
            "line_break" if is_line_breaking else
            "tackle" if event_type in [EventType.TACKLE, EventType.INTERCEPTION] else
            "routine"
        )
        commentary_translations = {}
        for lang in ["fr", "es", "ar", "ja"]:
            commentary_translations[lang] = self.translator.get_commentary_translation(
                cat, primary_player.name, active_team_data["name"], telemetry.speed_kmh, telemetry.distance_meters, lang
            )

        return MatchEvent(
            event_id=str(uuid.uuid4())[:8],
            match_id=self.match_id,
            match_clock=clock_str,
            timestamp_seconds=round(self.clock_seconds, 1),
            period=self.period,
            event_type=event_type,
            team=active_team_data["name"],
            player=primary_player,
            receiver=receiver,
            location=Coordinates(x=round(start_x, 1), y=round(start_y, 1)),
            end_location=Coordinates(x=round(end_x, 1), y=round(end_y, 1)),
            telemetry=telemetry,
            context=MatchContext(
                under_pressure=under_pressure,
                pressure_intensity=pressure_intensity,
                opponents_in_lane=opponents_in_lane,
                phase_of_play=phase_of_play,
                pitch_zone=pitch_zone
            ),
            pass_difficulty_index=pdr,
            pass_completed=pass_completed,
            is_line_breaking=is_line_breaking,
            expected_threat_delta=xt_delta,
            speed_milestone_triggered=bool(speed_milestone_desc),
            speed_milestone_desc=speed_milestone_desc,
            auto_detection=auto_detection,
            commentary=commentary,
            translations=commentary_translations
        )
