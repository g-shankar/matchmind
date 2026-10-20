import os
import json
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from openai import AzureOpenAI
from api.schemas import MatchEvent, MatchInsight, PersonaType, ControlChaosState, EventType
from ai.prompt_templates import SYSTEM_PROMPTS, RECAP_PROMPT

load_dotenv()
logger = logging.getLogger("pitchpulse.azure_ai")

class AzureOpenAIInsightsClient:
    """
    Hybrid Azure OpenAI client.
    Connects to Azure OpenAI Service if configured; otherwise provides
    intelligent local simulation that mirrors real GPT-4o football reasoning.
    """
    def __init__(self):
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
        self.api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
        self.client: Optional[AzureOpenAI] = None

        if self.api_key and self.endpoint and "placeholder" not in self.api_key:
            try:
                self.client = AzureOpenAI(
                    api_key=self.api_key,
                    azure_endpoint=self.endpoint,
                    api_version=self.api_version
                )
                logger.info(f"Connected to Azure OpenAI endpoint: {self.endpoint}")
            except Exception as e:
                logger.warning(f"Could not initialize AzureOpenAI client: {e}. Using intelligent local mode.")
                self.client = None
        else:
            logger.info("Azure OpenAI credentials not provided. Operating in high-fidelity local emulation mode.")

    def generate_explainable_insight(
        self,
        event: MatchEvent,
        control_state: ControlChaosState,
        persona: PersonaType = PersonaType.CASUAL,
        spotlight_player_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generates an explainable 'Why it matters' insight for a key moment."""
        # 1. Try Live Azure OpenAI
        if self.client:
            try:
                prompt_text = f"""
Match Event:
- Clock: {event.match_clock}
- Team: {event.team}
- Event Type: {event.event_type.value}
- Player: {event.player.name} ({event.player.position}, Jersey #{event.player.jersey_number})
- Receiver: {event.receiver.name if event.receiver else 'None'}
- Coordinates: ({event.location.x}, {event.location.y}) -> ({event.end_location.x if event.end_location else 'N/A'}, {event.end_location.y if event.end_location else 'N/A'})
- Pitch Zone: {event.context.pitch_zone}
- Phase of Play: {event.context.phase_of_play}
- Under Pressure: {event.context.under_pressure} (Intensity: {event.context.pressure_intensity})
- Pass Difficulty Rating (PDR): {event.pass_difficulty_index}
- Line Breaking Pass: {event.is_line_breaking}
- Ball Speed: {event.telemetry.speed_kmh} km/h (Milestone: {event.speed_milestone_desc})
- Expected Threat Delta: {event.expected_threat_delta}

Match Control vs Chaos Context:
- Current Tempo: {control_state.current_tempo}
- Chaos Index: {control_state.chaos_index} (-1.0=Chaos, +1.0=Control)
- Home Control: {control_state.home_control_pct}% | Away Control: {control_state.away_control_pct}%
"""
                response = self.client.chat.completions.create(
                    model=self.deployment,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPTS[persona]},
                        {"role": "user", "content": prompt_text}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                    max_tokens=350
                )
                raw_json = response.choices[0].message.content
                return json.loads(raw_json)
            except Exception as ex:
                logger.warning(f"Azure OpenAI call failed ({ex}); falling back to intelligent local generator.")

        # 2. Intelligent Local Rule & Context Generator (Graceful Emulation)
        return self._generate_local_insight(event, control_state, persona)

    def _generate_local_insight(
        self,
        event: MatchEvent,
        control_state: ControlChaosState,
        persona: PersonaType
    ) -> Dict[str, Any]:
        """Football domain logic engine that synthesizes high-quality explainable narratives."""
        player_name = event.player.name
        team = event.team
        speed = event.telemetry.speed_kmh
        pdr = event.pass_difficulty_index or 0.3
        line_break = event.is_line_breaking

        if event.event_type == EventType.GOAL:
            headline = f"GOAL! {player_name.upper()} BREAKTHROUGH"
            score = 10
            if persona == PersonaType.TACTICAL:
                why = f"Exploited an unbalanced defensive rest structure with {team} finding the central overload. The finish came after penetrating the primary line of containment."
                tactical = f"Shot struck at {speed:.1f} km/h following sustained territorial pressure in the {event.context.pitch_zone}."
            elif persona == PersonaType.FANTASY:
                why = f"Massive 6-point goal return for {player_name}! Positions him firmly at maximum 3 bonus points (BPS) if the result holds."
                tactical = f"Clinical conversion from high xG location, boosting underlying attacking returns."
            else: # CASUAL
                why = f"An absolute game-changer! {player_name} sends the stadium into raptures with a devastating finish that completely alters the momentum of this contest."
                tactical = f"Fired home with unbelievable composure under heavy challenge."

        elif event.event_type == EventType.SHOT:
            headline = f"{player_name} Fires Stunner ({speed:.0f} km/h)"
            score = 8
            if persona == PersonaType.TACTICAL:
                why = f"The high shot velocity ({speed:.1f} km/h) bypassed defensive recovery. Highlights the failure of the opposing double pivot to step up and contest the second ball."
                tactical = f"Aggressive vertical strike generating +{event.expected_threat_delta or 0.2:.2f} xT threat."
            elif persona == PersonaType.FANTASY:
                why = f"Crucial attempt on target; adds substantial BPS credit and confirms {player_name} remains the focal point of all attacking transitions."
                tactical = f"Goal threat index peaking with 3 attempts in the opposition box."
            else:
                why = f"Heart-in-mouth moment! A thunderous effort that tests the goalkeeper's reflexes and shows {team}'s intent to break this match wide open."
                tactical = f"Struck with vicious pace from the edge of the box."

        elif line_break:
            headline = f"Line-Breaking Pass by {player_name}"
            score = 7
            if persona == PersonaType.TACTICAL:
                why = f"Bypassed 2 lines of defensive containment with a {pdr*100:.0f}% difficulty pass, transitioning possession directly into the final third before the defence could reset."
                tactical = f"Superb disguise on the pass through the interior channel, completely destabilizing the opponent's mid-block."
            elif persona == PersonaType.FANTASY:
                why = f"Key pass credited! Sets up an immediate chance creation event that directly correlates with expected assist (xA) accumulation."
                tactical = f"Penetrating delivery inside the box territory."
            else:
                why = f"Vision of pure quality! {player_name} threads the needle with pinpoint precision, cracking open the opposition defence."
                tactical = f"Slid the ball right through a crowded midfield."

        elif event.event_type == EventType.INTERCEPTION or event.event_type == EventType.TACKLE:
            headline = f"High-Pressure Turnaround: {player_name}"
            score = 6
            if persona == PersonaType.TACTICAL:
                why = f"Triggered an immediate counter-pressing trap. Disrupts the opponent's build-up phase and converts defensive structure into high-value transition."
                tactical = f"Anticipated the passing lane with intensity ({event.context.pressure_intensity*100:.0f}% press factor)."
            elif persona == PersonaType.FANTASY:
                why = f"Adds to defensive contribution bonus; vital tackle preventing a high-threat conceded chance to protect cleansheet equity."
                tactical = f"Decisive intervention inside the defensive sector."
            else:
                why = f"Superb reading of the play! {player_name} snuffs out the danger just as the opposition looked dangerous, lifting the team's spirit."
                tactical = f"Stepped in front of the attacker to win the ball cleanly."

        else: # Routine pass or possession
            headline = f"{player_name} Orchestrates Rhythm"
            score = 4
            why = f"Maintains tempo under {event.context.phase_of_play.lower()} conditions while testing the opposing block's lateral discipline."
            tactical = f"Ball circulated at {speed:.1f} km/h with {event.context.opponents_in_lane} opponents in passing lane."

        return {
            "headline": headline,
            "why_it_matters": why,
            "tactical_explanation": tactical,
            "significance_score": score
        }
