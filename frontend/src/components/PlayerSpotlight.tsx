import React from 'react';
import { PlayerRef, MatchEvent } from '../types';
import { UserCheck, Zap, Navigation, Award, Activity } from 'lucide-react';

interface PlayerSpotlightProps {
  teamsData: any;
  selectedPlayerId: string;
  onSelectPlayer: (playerId: string) => void;
  recentEvents: MatchEvent[];
}

export const PlayerSpotlight: React.FC<PlayerSpotlightProps> = ({
  teamsData,
  selectedPlayerId,
  onSelectPlayer,
  recentEvents,
}) => {
  // Find selected player across teams
  let selectedPlayer: PlayerRef | null = null;
  const allPlayers: PlayerRef[] = [];

  if (teamsData) {
    Object.values(teamsData).forEach((team: any) => {
      team.players.forEach((p: PlayerRef) => {
        allPlayers.push(p);
        if (p.id === selectedPlayerId) {
          selectedPlayer = p;
        }
      });
    });
  }

  // Fallback default
  if (!selectedPlayer && allPlayers.length > 0) {
    selectedPlayer = allPlayers[0];
  }

  // Filter events involving this player
  const playerEvents = recentEvents.filter(
    (e) => e.player.id === selectedPlayer?.id || e.receiver?.id === selectedPlayer?.id
  );

  const isSpeedBurst = selectedPlayer ? selectedPlayer.speed_kmh > 31.0 : false;

  return (
    <div className="bg-slate-900/80 backdrop-blur-md rounded-xl p-5 border border-slate-800 shadow-xl space-y-4">
      {/* Header & Selector */}
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div className="flex items-center space-x-2">
          <UserCheck className="w-5 h-5 text-emerald-400" />
          <h3 className="font-display font-semibold text-white tracking-wide text-sm uppercase">
            Player Spotlight Cam
          </h3>
        </div>

        {/* Player Selector Dropdown */}
        <select
          value={selectedPlayer?.id ?? ''}
          onChange={(e) => onSelectPlayer(e.target.value)}
          className="bg-slate-950 border border-slate-700 text-xs text-white rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-emerald-500 font-mono"
        >
          {allPlayers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.team_name.split(' ')[0]}: #{p.jersey_number} {p.name} ({p.position})
            </option>
          ))}
        </select>
      </div>

      {selectedPlayer ? (
        <>
          {/* Player Bio Hero Box */}
          <div className="bg-gradient-to-r from-slate-950 via-slate-900 to-slate-950 p-4 rounded-xl border border-slate-800/80 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center font-display font-extrabold text-xl text-emerald-400 shadow-inner">
                #{selectedPlayer.jersey_number}
              </div>
              <div>
                <h4 className="font-display font-bold text-white text-lg tracking-wide">
                  {selectedPlayer.name}
                </h4>
                <div className="flex items-center space-x-2 text-xs text-slate-400 font-mono">
                  <span className="text-slate-300 font-semibold">{selectedPlayer.position}</span>
                  <span>•</span>
                  <span>{selectedPlayer.team_name}</span>
                </div>
              </div>
            </div>

            {/* Speed Burst Badge */}
            {isSpeedBurst && (
              <div className="flex items-center space-x-1.5 bg-amber-500/20 text-amber-300 border border-amber-500/40 px-3 py-1 rounded-full text-xs font-mono font-bold animate-pulse">
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>SPEED BURST</span>
              </div>
            )}
          </div>

          {/* Real-time Physical Telemetry Grid */}
          <div className="grid grid-cols-2 gap-3">
            {/* Live Speed */}
            <div className="bg-slate-950/70 p-3.5 rounded-xl border border-slate-800">
              <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                <span>CURRENT VELOCITY</span>
                <Activity className="w-3.5 h-3.5 text-emerald-400" />
              </div>
              <div className="flex items-baseline space-x-1">
                <span className="font-mono font-extrabold text-2xl text-white">
                  {selectedPlayer.speed_kmh.toFixed(1)}
                </span>
                <span className="text-xs text-slate-400 font-mono">km/h</span>
              </div>
              <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                <div
                  className="bg-emerald-400 h-full transition-all duration-500"
                  style={{ width: `${Math.min(100, (selectedPlayer.speed_kmh / 36.0) * 100)}%` }}
                />
              </div>
            </div>

            {/* Distance Covered */}
            <div className="bg-slate-950/70 p-3.5 rounded-xl border border-slate-800">
              <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                <span>TOTAL DISTANCE</span>
                <Navigation className="w-3.5 h-3.5 text-sky-400" />
              </div>
              <div className="flex items-baseline space-x-1">
                <span className="font-mono font-extrabold text-2xl text-sky-400">
                  {selectedPlayer.distance_covered_km.toFixed(2)}
                </span>
                <span className="text-xs text-slate-400 font-mono">km</span>
              </div>
              <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                <div
                  className="bg-sky-400 h-full transition-all duration-500"
                  style={{ width: `${Math.min(100, (selectedPlayer.distance_covered_km / 12.0) * 100)}%` }}
                />
              </div>
            </div>
          </div>

          {/* Recent Involvements Feed */}
          <div className="space-y-2">
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">
              LIVE ACTIONS & INVOLVEMENTS ({playerEvents.length})
            </span>
            <div className="max-h-40 overflow-y-auto space-y-1.5 pr-1 text-xs font-mono">
              {playerEvents.length === 0 ? (
                <p className="text-slate-600 text-[11px] py-2">
                  Awaiting player touches in current sequence...
                </p>
              ) : (
                playerEvents.slice(-4).reverse().map((ev) => (
                  <div
                    key={ev.event_id}
                    className="p-2 bg-slate-950/60 rounded-lg border border-slate-800/80 flex items-center justify-between"
                  >
                    <div className="flex items-center space-x-2">
                      <span className="text-emerald-400 font-bold">[{ev.match_clock}]</span>
                      <span className="text-white uppercase font-bold">{ev.event_type}</span>
                      {ev.is_line_breaking && (
                        <span className="text-[10px] bg-amber-500/20 text-amber-300 px-1.5 rounded">LINE BREAK</span>
                      )}
                    </div>
                    <span className="text-slate-400 text-[11px]">
                      {ev.telemetry.speed_kmh.toFixed(0)} km/h
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
};
