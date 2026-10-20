import React, { useEffect, useState, useRef } from 'react';
import {
  MatchEvent,
  MatchInsight,
  ControlChaosState,
  PersonaType,
  SupportedLanguage,
  MatchRecap,
} from './types';
import { Pitch2D } from './components/Pitch2D';
import { ControlChaosGauge } from './components/ControlChaosGauge';
import { NarrativeFeed } from './components/NarrativeFeed';
import { BroadcastOverlay } from './components/BroadcastOverlay';
import { PlayerSpotlight } from './components/PlayerSpotlight';
import { RecapModal } from './components/RecapModal';
import {
  Radio,
  Play,
  Pause,
  RotateCcw,
  FastForward,
  Sparkles,
  Tv,
  Layers,
  Users,
  Compass,
  FileText,
  Activity,
} from 'lucide-react';

export const App: React.FC = () => {
  // Navigation View
  const [viewMode, setViewMode] = useState<'studio' | 'overlay' | 'fan'>('studio');

  // Match State
  const [clock, setClock] = useState<string>('00:00');
  const [period, setPeriod] = useState<number>(1);
  const [homeScore, setHomeScore] = useState<number>(0);
  const [awayScore, setAwayScore] = useState<number>(0);
  const [currentEvent, setCurrentEvent] = useState<MatchEvent | null>(null);
  const [recentEvents, setRecentEvents] = useState<MatchEvent[]>([]);
  const [controlState, setControlState] = useState<ControlChaosState | null>(null);
  const [insights, setInsights] = useState<MatchInsight[]>([]);
  const [teamsData, setTeamsData] = useState<any>(null);

  // Playback & Controls
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [speedMultiplier, setSpeedMultiplier] = useState<number>(1.0);
  const [activePersona, setActivePersona] = useState<PersonaType>('casual');
  const [activeLanguage, setActiveLanguage] = useState<SupportedLanguage>('en');
  const [selectedPlayerId, setSelectedPlayerId] = useState<string>('MCI_09');

  // Recap Modal
  const [recapModalOpen, setRecapModalOpen] = useState<boolean>(false);
  const [recapData, setRecapData] = useState<MatchRecap | null>(null);
  const [isRecapLoading, setIsRecapLoading] = useState<boolean>(false);

  const socketRef = useRef<WebSocket | null>(null);

  // WebSocket Connection Lifecycle
  useEffect(() => {
    const wsUrl = `ws://${window.location.hostname}:8000/ws/match`;
    let ws: WebSocket;

    const connect = () => {
      ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'INITIAL_SNAPSHOT') {
            const d = payload.data;
            setClock(d.clock);
            setPeriod(d.period);
            setHomeScore(d.home_score);
            setAwayScore(d.away_score);
            setControlState(d.control_chaos);
            setTeamsData(d.teams);
            setActivePersona(d.active_persona);
            setSelectedPlayerId(d.active_spotlight_player_id || 'MCI_09');
            if (d.recent_insights) {
              setInsights(d.recent_insights);
            }
          } else if (payload.type === 'MATCH_TICK') {
            const d = payload.data;
            setClock(d.clock);
            setPeriod(d.period);
            setHomeScore(d.score.home);
            setAwayScore(d.score.away);
            setControlState(d.control_chaos);
            if (d.event) {
              setCurrentEvent(d.event);
              setRecentEvents((prev) => [...prev.slice(-30), d.event]);
            }
            if (d.insight) {
              setInsights((prev) => [...prev, d.insight]);
            }
          } else if (payload.type === 'MATCH_RESET') {
            setClock('00:00');
            setPeriod(1);
            setHomeScore(0);
            setAwayScore(0);
            setCurrentEvent(null);
            setRecentEvents([]);
            setInsights([]);
          } else if (payload.type === 'PLAYBACK_CONTROL') {
            setIsPlaying(payload.is_running);
            if (payload.speed_multiplier) setSpeedMultiplier(payload.speed_multiplier);
          } else if (payload.type === 'PERSONA_CHANGED') {
            setActivePersona(payload.persona);
          }
        } catch (err) {
          console.error('Error parsing WebSocket message:', err);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        setTimeout(connect, 2000);
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();

    return () => {
      if (ws) ws.close();
    };
  }, []);

  // Control Actions
  const handleTogglePlay = () => {
    if (socketRef.current && isConnected) {
      socketRef.current.send(JSON.stringify({ action: 'toggle_pause' }));
    }
  };

  const handleSpeedChange = (mult: number) => {
    setSpeedMultiplier(mult);
    if (socketRef.current && isConnected) {
      socketRef.current.send(
        JSON.stringify({ action: 'set_speed', speed_multiplier: mult })
      );
    }
  };

  const handleReset = () => {
    if (socketRef.current && isConnected) {
      socketRef.current.send(JSON.stringify({ action: 'reset' }));
    }
  };

  const handlePersonaChange = (persona: PersonaType) => {
    setActivePersona(persona);
    if (socketRef.current && isConnected) {
      socketRef.current.send(
        JSON.stringify({ action: 'set_persona', persona })
      );
    }
  };

  const handleTriggerRecap = async () => {
    setRecapModalOpen(true);
    setIsRecapLoading(true);
    try {
      const res = await fetch(`http://${window.location.hostname}:8000/api/match/recap?persona=${activePersona}`);
      const data = await res.json();
      setRecapData(data);
    } catch (err) {
      console.error('Failed to fetch recap:', err);
    } finally {
      setIsRecapLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#07090e] text-slate-100 flex flex-col font-sans">
      {/* GLOBAL NAVBAR */}
      <header className="bg-[#0b0e17] border-b border-slate-800/80 sticky top-0 z-40 px-6 py-3">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
          {/* Logo & Live Status */}
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-[#38003c] to-emerald-500 flex items-center justify-center font-bold text-white shadow-lg shadow-emerald-500/20">
              ⚽
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="font-display font-extrabold text-xl text-white tracking-wide">
                  PITCHPULSE <span className="text-emerald-400">AI</span>
                </h1>
                <span className="text-[10px] bg-slate-800 text-slate-300 font-mono px-2 py-0.5 rounded border border-slate-700">
                  PL STUDIO
                </span>
              </div>
              <p className="text-[11px] text-slate-400">
                Synthetic Match Insights & Explainable Narrative Engine
              </p>
            </div>

            {/* Connection Indicator */}
            <div className="ml-4 pl-4 border-l border-slate-800 flex items-center space-x-1.5 text-xs font-mono">
              <span
                className={`w-2 h-2 rounded-full ${
                  isConnected ? 'bg-emerald-400 animate-ping' : 'bg-rose-500'
                }`}
              />
              <span className={isConnected ? 'text-emerald-400 font-bold' : 'text-rose-400'}>
                {isConnected ? 'LIVE FEED' : 'RECONNECTING...'}
              </span>
            </div>
          </div>

          {/* VIEW MODE SWITCHER (Studio, Overlay, Fan) */}
          <div className="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800">
            <button
              onClick={() => setViewMode('studio')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                viewMode === 'studio'
                  ? 'bg-emerald-600 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Tv className="w-3.5 h-3.5" />
              <span>Studio Director</span>
            </button>
            <button
              onClick={() => setViewMode('overlay')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                viewMode === 'overlay'
                  ? 'bg-purple-700 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Broadcast Overlay</span>
            </button>
            <button
              onClick={() => setViewMode('fan')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                viewMode === 'fan'
                  ? 'bg-sky-600 text-white shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Users className="w-3.5 h-3.5" />
              <span>Fan Personalizer</span>
            </button>
          </div>

          {/* PLAYBACK CONTROLS & RECAP BUTTON */}
          <div className="flex items-center space-x-2">
            <button
              onClick={handleTogglePlay}
              className={`p-2 rounded-lg text-xs font-bold flex items-center space-x-1.5 transition ${
                isPlaying
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
              }`}
              title={isPlaying ? 'Pause Simulation' : 'Resume Simulation'}
            >
              {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
            </button>

            {/* Speed Multiplier Pills */}
            <div className="flex items-center space-x-1 bg-slate-950 px-2 py-1 rounded-lg border border-slate-800 text-xs font-mono">
              {[1.0, 2.0, 5.0].map((s) => (
                <button
                  key={s}
                  onClick={() => handleSpeedChange(s)}
                  className={`px-1.5 py-0.5 rounded transition ${
                    speedMultiplier === s
                      ? 'bg-emerald-500 text-black font-extrabold'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {s}x
                </button>
              ))}
            </div>

            <button
              onClick={handleReset}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition"
              title="Reset Match to 00:00"
            >
              <RotateCcw className="w-4 h-4" />
            </button>

            {/* Automated Recap Trigger */}
            <button
              onClick={handleTriggerRecap}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold shadow-lg shadow-emerald-950 transition"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Studio Recap</span>
            </button>
          </div>
        </div>
      </header>

      {/* PERSONA SWITCHER STRIP (Visible across views) */}
      <div className="bg-[#0e1320] border-b border-slate-800/60 px-6 py-2">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center space-x-2 text-slate-400 font-mono">
            <Compass className="w-4 h-4 text-emerald-400" />
            <span className="font-semibold text-slate-300">ACTIVE AUDIENCE PERSONA:</span>
          </div>

          <div className="flex items-center space-x-2">
            {[
              { id: 'casual', label: 'Casual Fan (Story & Drama)', desc: 'Simplified terms & high emotion' },
              { id: 'tactical', label: 'Tactical Analyst (The Chalkboard)', desc: 'PPDA, line-breaking & xT' },
              { id: 'fantasy', label: 'Fantasy Scout (FPL Lens)', desc: 'BPS, attacking returns & cleansheet odds' },
              { id: 'player_spotlight', label: 'Player Cam (Spotlight Mode)', desc: 'Single-star tracking' },
            ].map((p) => (
              <button
                key={p.id}
                onClick={() => handlePersonaChange(p.id as PersonaType)}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                  activePersona === p.id
                    ? 'bg-emerald-500 text-black font-extrabold shadow-md'
                    : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800'
                }`}
                title={p.desc}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* MAIN CONTENT AREA */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6">
        {viewMode === 'studio' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left Column: 2D Pitch + Control/Chaos Gauge (7 Cols) */}
            <div className="lg:col-span-7 space-y-6">
              {/* Pitch 2D */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-display font-bold text-white text-sm uppercase tracking-wider flex items-center space-x-2">
                    <Activity className="w-4 h-4 text-emerald-400" />
                    <span>Live Synthetic Pitch Trajectory</span>
                  </h3>
                  <span className="text-xs text-slate-400 font-mono">
                    Clock: <strong className="text-white">{clock}</strong> | Match ID: SYNTH-PL-2026
                  </span>
                </div>
                <Pitch2D currentEvent={currentEvent} />
              </div>

              {/* Control vs Chaos Gauge */}
              <ControlChaosGauge
                state={controlState}
                homeTeamName="Manchester Blue"
                awayTeamName="North London Red"
              />
            </div>

            {/* Right Column: Explainable AI Narrative Feed (5 Cols) */}
            <div className="lg:col-span-5 h-full">
              <NarrativeFeed
                insights={insights}
                recentEvents={recentEvents}
                currentLanguage={activeLanguage}
                onLanguageChange={setActiveLanguage}
              />
            </div>
          </div>
        )}

        {viewMode === 'overlay' && (
          <div className="relative w-full h-[640px] bg-gradient-to-b from-slate-900/60 to-black/80 rounded-2xl border-2 border-dashed border-purple-500/40 overflow-hidden shadow-2xl backdrop-blur-sm">
            {/* Simulation of a Live Match Stream with Overlay Layered */}
            <div className="absolute inset-0 flex items-center justify-center opacity-10 pointer-events-none">
              <span className="font-display text-9xl font-extrabold text-white">4K BROADCAST FEED</span>
            </div>
            <BroadcastOverlay
              currentEvent={currentEvent}
              latestInsight={insights[insights.length - 1] ?? null}
              controlState={controlState}
              homeScore={homeScore}
              awayScore={awayScore}
              clock={clock}
              period={period}
            />
          </div>
        )}

        {viewMode === 'fan' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left: Player Spotlight Mode (6 Cols) */}
            <div className="lg:col-span-6 space-y-6">
              <PlayerSpotlight
                teamsData={teamsData}
                selectedPlayerId={selectedPlayerId}
                onSelectPlayer={setSelectedPlayerId}
                recentEvents={recentEvents}
              />
              <ControlChaosGauge
                state={controlState}
                homeTeamName="Manchester Blue"
                awayTeamName="North London Red"
              />
            </div>

            {/* Right: Personalized Narrative Stream (6 Cols) */}
            <div className="lg:col-span-6">
              <NarrativeFeed
                insights={insights}
                recentEvents={recentEvents}
                currentLanguage={activeLanguage}
                onLanguageChange={setActiveLanguage}
              />
            </div>
          </div>
        )}
      </main>

      {/* RECAP MODAL */}
      <RecapModal
        isOpen={recapModalOpen}
        onClose={() => setRecapModalOpen(false)}
        recap={recapData}
        isLoading={isRecapLoading}
      />
    </div>
  );
};

export default App;
