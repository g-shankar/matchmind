import React from 'react';
import { MatchEvent } from '../types';

interface Pitch2DProps {
  currentEvent: MatchEvent | null;
}

export const Pitch2D: React.FC<Pitch2DProps> = ({ currentEvent }) => {
  // SVG coordinates: 105m length x 68m width
  // ViewBox: 0 0 105 68
  const startX = currentEvent?.location.x ?? 52.5;
  const startY = currentEvent?.location.y ?? 34.0;
  const endX = currentEvent?.end_location?.x ?? startX;
  const endY = currentEvent?.end_location?.y ?? startY;

  const isHome = currentEvent?.team === 'Manchester Blue';
  const playerColor = isHome ? '#38bdf8' : '#ef4444'; // Sky blue vs Red
  const isLineBreak = currentEvent?.is_line_breaking;
  const isShot = currentEvent?.event_type === 'shot' || currentEvent?.event_type === 'goal';
  const isGoal = currentEvent?.event_type === 'goal';

  return (
    <div className="relative w-full aspect-[105/68] bg-[#0f2415] rounded-xl overflow-hidden shadow-2xl border border-emerald-900/40 select-none">
      {/* Background Grass Stripes Pattern */}
      <div className="absolute inset-0 grid grid-cols-12 opacity-30 pointer-events-none">
        {Array.from({ length: 12 }).map((_, i) => (
          <div key={i} className={i % 2 === 0 ? 'bg-emerald-950/40' : 'bg-transparent'} />
        ))}
      </div>

      <svg
        viewBox="0 0 105 68"
        className="w-full h-full relative z-10"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <radialGradient id="ballGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="1" />
            <stop offset="60%" stopColor="#fef08a" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#eab308" stopOpacity="0" />
          </radialGradient>
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="0.8" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Outer Boundary & Touchlines */}
        <rect x="2" y="2" width="101" height="64" fill="none" stroke="#2e7d48" strokeWidth="0.6" />

        {/* Halfway Line & Center Circle */}
        <line x1="52.5" y1="2" x2="52.5" y2="66" stroke="#2e7d48" strokeWidth="0.6" />
        <circle cx="52.5" cy="34" r="9.15" fill="none" stroke="#2e7d48" strokeWidth="0.6" />
        <circle cx="52.5" cy="34" r="0.8" fill="#2e7d48" />

        {/* Left Penalty Area (Home) */}
        <rect x="2" y="13.84" width="16.5" height="40.32" fill="none" stroke="#2e7d48" strokeWidth="0.6" />
        <rect x="2" y="24.84" width="5.5" height="18.32" fill="none" stroke="#2e7d48" strokeWidth="0.6" />
        <circle cx="11" cy="34" r="0.8" fill="#2e7d48" />
        <path d="M 18.5 28.5 A 9.15 9.15 0 0 1 18.5 39.5" fill="none" stroke="#2e7d48" strokeWidth="0.6" />

        {/* Right Penalty Area (Away) */}
        <rect x="86.5" y="13.84" width="16.5" height="40.32" fill="none" stroke="#2e7d48" strokeWidth="0.6" />
        <rect x="97.5" y="24.84" width="5.5" height="18.32" fill="none" stroke="#2e7d48" strokeWidth="0.6" />
        <circle cx="94" cy="34" r="0.8" fill="#2e7d48" />
        <path d="M 86.5 28.5 A 9.15 9.15 0 0 0 86.5 39.5" fill="none" stroke="#2e7d48" strokeWidth="0.6" />

        {/* Corner Arcs */}
        <path d="M 2 3 A 1 1 0 0 0 3 2" fill="none" stroke="#2e7d48" strokeWidth="0.6" />
        <path d="M 2 65 A 1 1 0 0 1 3 66" fill="none" stroke="#2e7d48" strokeWidth="0.6" />
        <path d="M 103 2 A 1 1 0 0 0 102 3" fill="none" stroke="#2e7d48" strokeWidth="0.6" />
        <path d="M 103 66 A 1 1 0 0 1 102 65" fill="none" stroke="#2e7d48" strokeWidth="0.6" />

        {/* Goal Boxes */}
        <rect x="0.2" y="30.34" width="1.8" height="7.32" fill="none" stroke="#ffffff" strokeWidth="0.5" opacity="0.7" />
        <rect x="103" y="30.34" width="1.8" height="7.32" fill="none" stroke="#ffffff" strokeWidth="0.5" opacity="0.7" />

        {/* ACTION VECTOR (Pass / Shot Trajectory) */}
        {currentEvent && (
          <g>
            {/* Trajectory Line */}
            <line
              x1={startX}
              y1={startY}
              x2={endX}
              y2={endY}
              stroke={
                isGoal ? '#22c55e' :
                isShot ? '#f43f5e' :
                isLineBreak ? '#f59e0b' : '#38bdf8'
              }
              strokeWidth={isLineBreak || isShot ? '1.2' : '0.8'}
              strokeDasharray={currentEvent.telemetry.airborne ? '2 1' : 'none'}
              filter="url(#glow)"
              className="transition-all duration-500 ease-out"
            />

            {/* Target Reticle / Landing Spot */}
            <circle
              cx={endX}
              cy={endY}
              r="1.8"
              fill="none"
              stroke={isLineBreak ? '#f59e0b' : '#38bdf8'}
              strokeWidth="0.5"
              strokeDasharray="1 1"
              className="animate-spin"
            />

            {/* Active Ball Position */}
            <circle
              cx={endX}
              cy={endY}
              r="2.2"
              fill="url(#ballGlow)"
              className="transition-all duration-300"
            />
            <circle cx={endX} cy={endY} r="1.1" fill="#ffffff" />

            {/* Passer Node */}
            <g transform={`translate(${startX}, ${startY})`}>
              <circle r="2.2" fill={playerColor} stroke="#ffffff" strokeWidth="0.5" />
              <text
                y="-3.5"
                textAnchor="middle"
                fill="#ffffff"
                fontSize="2.4"
                fontWeight="bold"
                className="drop-shadow"
              >
                {currentEvent.player.name.split(' ').pop()} (#{currentEvent.player.jersey_number})
              </text>
            </g>

            {/* Receiver Node (if pass) */}
            {currentEvent.receiver && (
              <g transform={`translate(${endX}, ${endY})`}>
                <circle r="1.9" fill={playerColor} stroke="#ffffff" strokeWidth="0.4" opacity="0.9" />
                <text
                  y="4.5"
                  textAnchor="middle"
                  fill="#cbd5e1"
                  fontSize="2.1"
                  fontWeight="600"
                >
                  {currentEvent.receiver.name.split(' ').pop()}
                </text>
              </g>
            )}
          </g>
        )}
      </svg>

      {/* Floating HUD Overlay on Pitch */}
      <div className="absolute top-3 left-3 flex items-center space-x-2 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-lg border border-white/10 text-xs">
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
        <span className="text-slate-300 font-mono font-medium">
          ZONE: <strong className="text-white">{currentEvent?.context.pitch_zone ?? 'Middle Third'}</strong>
        </span>
        <span className="text-slate-600">|</span>
        <span className="text-slate-300 font-mono">
          PHASE: <strong className="text-white">{currentEvent?.context.phase_of_play ?? 'Build-up'}</strong>
        </span>
      </div>

      {/* Floating Telemetry Badge on Pitch (Bottom Right) */}
      {currentEvent && (
        <div className="absolute bottom-3 right-3 flex items-center space-x-2 bg-black/75 backdrop-blur-md px-3 py-1.5 rounded-lg border border-white/15 text-xs font-mono">
          <div className="flex items-center space-x-1 text-slate-300">
            <span>SPEED:</span>
            <strong className="text-emerald-400 font-bold">{currentEvent.telemetry.speed_kmh.toFixed(1)} km/h</strong>
          </div>
          {currentEvent.pass_difficulty_index !== undefined && currentEvent.pass_difficulty_index !== null && (
            <>
              <span className="text-slate-600">|</span>
              <div className="flex items-center space-x-1 text-slate-300">
                <span>PDR:</span>
                <strong className={`font-bold ${currentEvent.pass_difficulty_index > 0.7 ? 'text-rose-400' : 'text-amber-300'}`}>
                  {(currentEvent.pass_difficulty_index * 100).toFixed(0)}%
                </strong>
              </div>
            </>
          )}
          {currentEvent.is_line_breaking && (
            <span className="ml-1 bg-amber-500/20 text-amber-300 border border-amber-500/40 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider">
              Line Break
            </span>
          )}
        </div>
      )}
    </div>
  );
};
