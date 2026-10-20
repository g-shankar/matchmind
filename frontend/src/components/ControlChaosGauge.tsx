import React from 'react';
import { ControlChaosState } from '../types';
import { Gauge, Activity, ShieldCheck, Flame } from 'lucide-react';

interface ControlChaosGaugeProps {
  state: ControlChaosState | null;
  homeTeamName?: string;
  awayTeamName?: string;
}

export const ControlChaosGauge: React.FC<ControlChaosGaugeProps> = ({
  state,
  homeTeamName = "Manchester Blue",
  awayTeamName = "North London Red"
}) => {
  const chaosVal = state?.chaos_index ?? 0.0; // -1.0 (chaos) to +1.0 (control)
  // Map -1.0..+1.0 to 0%..100%
  const needlePct = Math.min(100, Math.max(0, ((chaosVal + 1.0) / 2.0) * 100));

  const homePct = state?.home_control_pct ?? 50;
  const awayPct = state?.away_control_pct ?? 50;
  const momentum = state?.rolling_momentum_home ?? 0;

  return (
    <div className="bg-slate-900/80 backdrop-blur-md rounded-xl p-5 border border-slate-800 shadow-xl flex flex-col justify-between space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div className="flex items-center space-x-2">
          <Gauge className="w-5 h-5 text-emerald-400" />
          <h3 className="font-display font-semibold text-white tracking-wide text-sm uppercase">
            Control vs. Chaos Index
          </h3>
        </div>
        <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
          <Activity className="w-3.5 h-3.5 animate-pulse text-emerald-400" />
          <span>{state?.current_tempo ?? 'Methodical Control'}</span>
        </div>
      </div>

      {/* Dial / Spectrum Meter */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs font-medium text-slate-400">
          <span className="flex items-center text-rose-400 font-mono">
            <Flame className="w-3.5 h-3.5 mr-1" /> CHAOS (-1.0)
          </span>
          <span className="font-mono text-slate-200 font-bold">
            INDEX: {chaosVal > 0 ? `+${chaosVal.toFixed(2)}` : chaosVal.toFixed(2)}
          </span>
          <span className="flex items-center text-cyan-400 font-mono">
            CONTROL (+1.0) <ShieldCheck className="w-3.5 h-3.5 ml-1" />
          </span>
        </div>

        {/* Gradient Spectrum Bar with Needle */}
        <div className="relative w-full h-4 bg-gradient-to-r from-rose-600 via-amber-500 via-emerald-500 to-cyan-500 rounded-full overflow-hidden p-0.5 shadow-inner">
          <div
            className="absolute top-0 bottom-0 w-2.5 bg-white rounded-full shadow-lg border border-black transition-all duration-700 ease-out -translate-x-1/2"
            style={{ left: `${needlePct}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-slate-500 px-1 font-mono">
          <span>Counter-attack & Frantic Turnovers</span>
          <span>Settled Positional Dominance</span>
        </div>
      </div>

      {/* Possession & Field Tilt Bar */}
      <div className="space-y-1.5 pt-1">
        <div className="flex justify-between text-xs font-medium">
          <span className="text-sky-400 font-bold">{homeTeamName} ({homePct}%)</span>
          <span className="text-slate-400 text-[11px] font-mono">FIELD TILT / WEIGHT</span>
          <span className="text-rose-400 font-bold">{awayTeamName} ({awayPct}%)</span>
        </div>
        <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden flex">
          <div
            className="bg-sky-500 transition-all duration-700 ease-out"
            style={{ width: `${homePct}%` }}
          />
          <div
            className="bg-rose-500 transition-all duration-700 ease-out"
            style={{ width: `${awayPct}%` }}
          />
        </div>
      </div>

      {/* Dynamic Momentum Balance */}
      <div className="bg-slate-950/60 rounded-lg p-3 border border-slate-800/80 flex items-center justify-between text-xs font-mono">
        <span className="text-slate-400">Rolling Momentum:</span>
        <div className="flex items-center space-x-2">
          <div className="w-24 h-2 bg-slate-800 rounded-full relative overflow-hidden">
            <div
              className={`absolute top-0 bottom-0 transition-all duration-700 ${
                momentum > 0 ? 'bg-sky-400 right-1/2' : 'bg-rose-400 left-1/2'
              }`}
              style={{
                width: `${Math.abs(momentum) / 2}%`,
                transform: momentum > 0 ? 'scaleX(-1)' : 'none'
              }}
            />
          </div>
          <span className={`font-bold ${momentum > 15 ? 'text-sky-400' : momentum < -15 ? 'text-rose-400' : 'text-slate-300'}`}>
            {momentum > 0 ? `${homeTeamName.split(' ')[0]} +${momentum.toFixed(0)}` : `${awayTeamName.split(' ')[0]} ${momentum.toFixed(0)}`}
          </span>
        </div>
      </div>
    </div>
  );
};
