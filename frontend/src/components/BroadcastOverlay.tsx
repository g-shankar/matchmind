import React, { useEffect, useState } from 'react';
import { MatchEvent, MatchInsight, ControlChaosState } from '../types';
import { Flame, Sparkles, Zap, ShieldCheck } from 'lucide-react';

interface BroadcastOverlayProps {
  currentEvent: MatchEvent | null;
  latestInsight: MatchInsight | null;
  controlState: ControlChaosState | null;
  homeScore: number;
  awayScore: number;
  clock: string;
  period: number;
}

export const BroadcastOverlay: React.FC<BroadcastOverlayProps> = ({
  currentEvent,
  latestInsight,
  controlState,
  homeScore,
  awayScore,
  clock,
  period,
}) => {
  const [showLowerThird, setShowLowerThird] = useState(false);
  const [activeBanner, setActiveBanner] = useState<{
    headline: string;
    subtext: string;
    metric?: string;
    isGoal?: boolean;
    isRocket?: boolean;
  } | null>(null);

  // Trigger broadcast lower third on notable moments
  useEffect(() => {
    if (!currentEvent) return;

    if (currentEvent.event_type === 'goal') {
      setActiveBanner({
        headline: `GOAL! ${currentEvent.player.name.toUpperCase()}`,
        subtext: latestInsight?.why_it_matters ?? 'A devastating strike alters match momentum completely.',
        metric: `${currentEvent.telemetry.speed_kmh.toFixed(1)} km/h Strike`,
        isGoal: true,
      });
      setShowLowerThird(true);
    } else if (currentEvent.speed_milestone_triggered) {
      setActiveBanner({
        headline: currentEvent.speed_milestone_desc ?? 'HIGH-VELOCITY MOMENT',
        subtext: latestInsight?.why_it_matters ?? 'Top tier velocity recorded by synthetic telemetry.',
        metric: `${currentEvent.telemetry.speed_kmh.toFixed(1)} km/h`,
        isRocket: true,
      });
      setShowLowerThird(true);
    } else if (currentEvent.is_line_breaking) {
      setActiveBanner({
        headline: `LINE-BREAKING PASS: ${currentEvent.player.name}`,
        subtext: latestInsight?.why_it_matters ?? 'Bypassed defensive structure with pinpoint precision.',
        metric: `PDR: ${((currentEvent.pass_difficulty_index ?? 0.7) * 100).toFixed(0)}%`,
      });
      setShowLowerThird(true);
    }

    const timer = setTimeout(() => {
      setShowLowerThird(false);
    }, 6000);

    return () => clearTimeout(timer);
  }, [currentEvent, latestInsight]);

  return (
    <div className="relative w-full h-full min-h-[500px] flex flex-col justify-between p-6 pointer-events-none select-none">
      {/* TOP BAR: Official Premier League Style Scorebug */}
      <div className="flex items-start justify-between">
        <div className="flex flex-col shadow-2xl filter drop-shadow-xl">
          {/* Main Scoreboard Box */}
          <div className="flex items-stretch bg-[#111625] rounded-t-lg border-t-2 border-l border-r border-[#00ff87] overflow-hidden">
            {/* Clock & Period */}
            <div className="bg-[#38003c] text-white px-3.5 py-2 flex flex-col justify-center items-center font-mono font-bold text-xs">
              <span className="text-white text-sm">{clock}</span>
              <span className="text-[10px] text-emerald-400 font-sans tracking-wider uppercase font-semibold">
                {period === 1 ? '1ST' : '2ND'}
              </span>
            </div>

            {/* Home Team (Manchester Blue) */}
            <div className="flex items-center space-x-2 px-3 py-2 bg-[#1a2238] border-r border-slate-700">
              <div className="w-3 h-5 bg-[#6CABDD] rounded-sm" />
              <span className="font-display font-bold text-white text-base tracking-wider">MCI</span>
              <span className="font-mono font-extrabold text-white text-lg ml-1">{homeScore}</span>
            </div>

            {/* Away Team (North London Red) */}
            <div className="flex items-center space-x-2 px-3 py-2 bg-[#1a2238]">
              <span className="font-mono font-extrabold text-white text-lg mr-1">{awayScore}</span>
              <span className="font-display font-bold text-white text-base tracking-wider">ARS</span>
              <div className="w-3 h-5 bg-[#EF0107] rounded-sm" />
            </div>
          </div>

          {/* Under-Scorebug Momentum & Control Bar */}
          <div className="bg-black/90 px-3 py-1 rounded-b-lg border-b border-l border-r border-slate-700 flex items-center justify-between text-[10px] font-mono">
            <span className="text-slate-400">TEMPO:</span>
            <span className="text-emerald-400 font-bold ml-1">
              {controlState?.current_tempo ?? 'Methodical'}
            </span>
            <span className="text-slate-600 mx-1">|</span>
            <span className="text-slate-300">
              CHAOS: <strong className={controlState && controlState.chaos_index < 0 ? 'text-rose-400' : 'text-cyan-400'}>
                {controlState?.chaos_index ? (controlState.chaos_index > 0 ? `+${controlState.chaos_index.toFixed(1)}` : controlState.chaos_index.toFixed(1)) : '0.0'}
              </strong>
            </span>
          </div>
        </div>

        {/* TOP RIGHT: Real-time Auto-Eventing Computer Vision Status */}
        <div className="bg-black/80 backdrop-blur-md px-3 py-1.5 rounded-lg border border-white/10 flex items-center space-x-2 text-xs font-mono shadow-lg">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span className="text-slate-300">
            AUTO-EVENTING: <strong className="text-emerald-400">ACTIVE (16ms)</strong>
          </span>
        </div>
      </div>

      {/* BOTTOM THIRD: Dynamic Broadcast Narrative Graphic */}
      <div className="w-full flex justify-center pb-4">
        {showLowerThird && activeBanner && (
          <div className="w-full max-w-2xl bg-gradient-to-r from-[#38003c] via-[#1a2238] to-[#111625] text-white p-4 rounded-xl border-l-4 border-[#00ff87] shadow-2xl animate-slide-up filter drop-shadow-2xl">
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center space-x-2">
                {activeBanner.isGoal ? (
                  <Sparkles className="w-5 h-5 text-amber-300 animate-spin" />
                ) : activeBanner.isRocket ? (
                  <Zap className="w-5 h-5 text-amber-400 animate-bounce" />
                ) : (
                  <ShieldCheck className="w-5 h-5 text-emerald-400" />
                )}
                <span className="font-display font-bold text-base tracking-wide text-white uppercase">
                  {activeBanner.headline}
                </span>
              </div>

              {activeBanner.metric && (
                <span className="bg-[#00ff87] text-black font-mono font-extrabold text-xs px-2.5 py-0.5 rounded-md shadow">
                  {activeBanner.metric}
                </span>
              )}
            </div>

            <p className="text-xs text-slate-200 leading-relaxed font-sans pl-7">
              {activeBanner.subtext}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
