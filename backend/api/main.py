import asyncio
import json
import logging
from typing import Set, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from api.schemas import (
    MatchEvent, MatchSnapshot, MatchInsight, MatchRecap,
    PersonaType, SupportedLanguage, ControlChaosState
)
from simulation.match_generator import SyntheticMatchSimulator
from simulation.teams_data import TEAMS_DATA
from analytics.momentum_tracker import MomentumTracker
from ai.narrative_engine import MatchNarrativeEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pitchpulse.api")

app = FastAPI(
    title="PitchPulse AI - Synthetic Match Insights Engine",
    description="Azure-powered explainable intelligence & broadcast narrative engine for Premier League Studio",
    version="1.0.0"
)

# Enable CORS for local and cloud frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singleton State
simulator = SyntheticMatchSimulator()
momentum_tracker = MomentumTracker()
narrative_engine = MatchNarrativeEngine()

active_persona: PersonaType = PersonaType.CASUAL
active_spotlight_player_id: Optional[str] = "MCI_09"  # Default Haaland
is_running: bool = True
simulation_speed_multiplier: float = 1.0  # 1.0 = normal, 2.0 = fast

connected_clients: Set[WebSocket] = set()
background_task: Optional[asyncio.Task] = None

class PersonaUpdateRequest(BaseModel):
    persona: PersonaType
    spotlight_player_id: Optional[str] = None

class SimulationSpeedRequest(BaseModel):
    speed_multiplier: float
    is_running: bool

@app.on_event("startup")
async def startup_event():
    global background_task
    logger.info("PitchPulse AI engine initializing...")
    background_task = asyncio.create_task(run_simulation_loop())

@app.on_event("shutdown")
async def shutdown_event():
    if background_task:
        background_task.cancel()

async def broadcast_payload(payload: dict):
    """Broadcasts a JSON payload to all connected WebSockets."""
    if not connected_clients:
        return
    disconnected = set()
    message = json.dumps(jsonable_encoder(payload))
    for ws in connected_clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)
    for ws in disconnected:
        connected_clients.discard(ws)

async def run_simulation_loop():
    """Continuous background loop generating match events and broadcasting insights."""
    global is_running, active_persona, active_spotlight_player_id
    while True:
        try:
            if is_running:
                event = simulator.generate_next_event()
                control_state = momentum_tracker.record_event(event)

                # Generate AI Narrative Insight if notable
                insight = await narrative_engine.evaluate_event_for_narrative(
                    event=event,
                    control_state=control_state,
                    active_persona=active_persona
                )

                payload = {
                    "type": "MATCH_TICK",
                    "data": {
                        "event": event.model_dump(),
                        "score": {
                            "home": simulator.home_score,
                            "away": simulator.away_score,
                        },
                        "control_chaos": control_state.model_dump(),
                        "insight": insight.model_dump() if insight else None,
                        "clock": event.match_clock,
                        "period": event.period,
                    }
                }
                await broadcast_payload(payload)

            # Sleep interval governed by speed multiplier (base 2.2 seconds per event)
            sleep_time = max(0.4, 2.2 / simulation_speed_multiplier) if is_running else 1.0
            await asyncio.sleep(sleep_time)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in simulation loop: {e}", exc_info=True)
            await asyncio.sleep(2.0)

# REST Endpoints
@app.get("/api/health")
async def get_health():
    return {
        "status": "healthy",
        "engine": "PitchPulse AI",
        "azure_openai_configured": bool(narrative_engine.ai_client.client),
        "azure_translator_configured": bool(narrative_engine.translator.api_key),
        "clients_connected": len(connected_clients),
        "current_match_clock": f"{int(simulator.clock_seconds // 60):02d}:{int(simulator.clock_seconds % 60):02d}"
    }

@app.get("/api/teams")
async def get_teams():
    return TEAMS_DATA

@app.get("/api/match/snapshot")
async def get_snapshot():
    control_state = momentum_tracker.compute_state()
    mins = int(simulator.clock_seconds // 60)
    secs = int(simulator.clock_seconds % 60)
    return MatchSnapshot(
        match_id=simulator.match_id,
        clock=f"{mins:02d}:{secs:02d}",
        period=simulator.period,
        home_team=simulator.home_team_name,
        away_team=simulator.away_team_name,
        home_score=simulator.home_score,
        away_score=simulator.away_score,
        control_chaos=control_state,
        recent_insights=narrative_engine.cached_insights[-10:]
    )

@app.post("/api/match/reset")
async def reset_match():
    simulator.reset()
    momentum_tracker.__init__()
    narrative_engine.cached_insights.clear()
    narrative_engine.key_events_history.clear()
    await broadcast_payload({"type": "MATCH_RESET"})
    return {"status": "reset_successful"}

@app.post("/api/match/persona")
async def update_persona(req: PersonaUpdateRequest):
    global active_persona, active_spotlight_player_id
    active_persona = req.persona
    if req.spotlight_player_id:
        active_spotlight_player_id = req.spotlight_player_id
    await broadcast_payload({
        "type": "PERSONA_CHANGED",
        "persona": active_persona,
        "spotlight_player_id": active_spotlight_player_id
    })
    return {"active_persona": active_persona, "spotlight_player_id": active_spotlight_player_id}

@app.post("/api/match/speed")
async def update_speed(req: SimulationSpeedRequest):
    global simulation_speed_multiplier, is_running
    simulation_speed_multiplier = req.speed_multiplier
    is_running = req.is_running
    await broadcast_payload({
        "type": "PLAYBACK_CONTROL",
        "speed_multiplier": simulation_speed_multiplier,
        "is_running": is_running
    })
    return {"speed_multiplier": simulation_speed_multiplier, "is_running": is_running}

@app.get("/api/match/recap")
async def get_match_recap(persona: PersonaType = PersonaType.CASUAL):
    mins = int(simulator.clock_seconds // 60)
    secs = int(simulator.clock_seconds % 60)
    control_state = momentum_tracker.compute_state()
    recap = narrative_engine.generate_automated_recap(
        match_id=simulator.match_id,
        current_clock=f"{mins:02d}:{secs:02d}",
        home_team=simulator.home_team_name,
        away_team=simulator.away_team_name,
        home_score=simulator.home_score,
        away_score=simulator.away_score,
        control_state=control_state,
        persona=persona
    )
    return recap

# Streaming WebSocket Endpoint
@app.websocket("/ws/match")
async def websocket_match_feed(websocket: WebSocket):
    global active_persona, simulation_speed_multiplier, is_running
    await websocket.accept()
    connected_clients.add(websocket)
    logger.info(f"Client connected to WebSocket. Total active: {len(connected_clients)}")

    # Send initial snapshot immediately upon connection
    control_state = momentum_tracker.compute_state()
    mins = int(simulator.clock_seconds // 60)
    secs = int(simulator.clock_seconds % 60)
    initial_snapshot = {
        "type": "INITIAL_SNAPSHOT",
        "data": {
            "match_id": simulator.match_id,
            "clock": f"{mins:02d}:{secs:02d}",
            "period": simulator.period,
            "home_score": simulator.home_score,
            "away_score": simulator.away_score,
            "control_chaos": control_state.model_dump(),
            "teams": jsonable_encoder(TEAMS_DATA),
            "active_persona": active_persona,
            "active_spotlight_player_id": active_spotlight_player_id,
            "recent_insights": [i.model_dump() for i in narrative_engine.cached_insights[-8:]]
        }
    }
    await websocket.send_text(json.dumps(jsonable_encoder(initial_snapshot)))

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")
            
            if action == "set_persona":
                active_persona = PersonaType(msg.get("persona", PersonaType.CASUAL))
                await broadcast_payload({
                    "type": "PERSONA_CHANGED",
                    "persona": active_persona
                })
            elif action == "set_speed":
                simulation_speed_multiplier = float(msg.get("speed_multiplier", 1.0))
            elif action == "toggle_pause":
                is_running = not is_running
                await broadcast_payload({"type": "PLAYBACK_CONTROL", "is_running": is_running})
            elif action == "reset":
                simulator.reset()
                momentum_tracker.__init__()
                await broadcast_payload({"type": "MATCH_RESET"})
    except WebSocketDisconnect:
        connected_clients.discard(websocket)
        logger.info(f"Client disconnected. Remaining active: {len(connected_clients)}")
    except Exception as e:
        logger.error(f"WebSocket client error: {e}")
        connected_clients.discard(websocket)
