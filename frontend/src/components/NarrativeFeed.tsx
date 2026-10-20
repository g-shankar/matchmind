import React, { useState } from 'react';
import { MatchInsight, MatchEvent, SupportedLanguage } from '../types';
import {
  Sparkles,
  Globe2,
  BrainCircuit,
  Award,
  Clock,
  Radio,
  Zap,
  ChevronRight,
  ShieldAlert,
} from 'lucide-react';

interface NarrativeFeedProps {
  insights: MatchInsight[];
  recentEvents: MatchEvent[];
  currentLanguage: SupportedLanguage;
  onLanguageChange: (lang: SupportedLanguage) => void;
}

const LANGUAGES: { code: SupportedLanguage; label: string; flag: string }[] = [
  { code: 'en', label: 'English', flag: '🇬🇧' },
  { code: 'es', label: 'Español', flag: '🇪🇸' },
  { code: 'fr', label: 'Français', flag: '🇫🇷' },
  { code: 'ar', label: 'العربية', flag: '🇸🇦' },
  { code: 'ja', label: '日本語', flag: '🇯🇵' },
];

export const NarrativeFeed: React.FC<NarrativeFeedProps> = ({
  insights,
  recentEvents,
  currentLanguage,
  onLanguageChange,
}) => {
  const [filterMode, setFilterMode] = useState<'all' | 'insights' | 'commentary'>('all');

  // Map of event_id -> insight for quick lookup
  const insightsMap = new Map<string, MatchInsight>();
  insights.forEach((ins) => insightsMap.set(ins.event_id, ins));

  return (
    <div className="bg-slate-900/80 backdrop-blur-md rounded-xl p-5 border border-slate-800 shadow-xl flex flex-col h-full max-h-[640px]">
      {/* Header with Multi-Language Switcher */}
      <div className="flex flex-wrap items-center justify-between border-b border-slate-800/80 pb-3 gap-2">
        <div className="flex items-center space-x-2">
          <BrainCircuit className="w-5 h-5 text-emerald-400" />
          <h3 className="font-display font-semibold text-white tracking-wide text-sm uppercase">
            Live Match Intelligence Feed
          </h3>
          <span className="flex items-center text-[10px] bg-emerald-500/10 text-emerald-300 font-mono px-2 py-0.5 rounded-full border border-emerald-500/20">
            <Radio className="w-2.5 h-2.5 mr-1 animate-pulse text-emerald-400" />
            LIVE
          </span>
        </div>

        {/* Language Tabs */}
        <div className="flex items-center space-x-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
          <Globe2 className="w-3.5 h-3.5 text-slate-400 ml-1.5 mr-0.5" />
          {LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              onClick={() => onLanguageChange(lang.code)}
              className={`px-2 py-1 rounded text-xs font-medium transition-all ${
                currentLanguage === lang.code
                  ? 'bg-emerald-600 text-white font-bold shadow'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <span className="mr-1">{lang.flag}</span>
              <span>{lang.code.toUpperCase()}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Sub-Header: Feed Filter Tabs */}
      <div className="flex items-center space-x-2 pt-2.5 pb-2 text-xs font-medium border-b border-slate-800/50">
        <span className="text-slate-500 text-[11px] uppercase tracking-wider font-mono">Stream:</span>
        <button
          onClick={() => setFilterMode('all')}
          className={`px-2.5 py-1 rounded-md transition ${
            filterMode === 'all'
              ? 'bg-slate-800 text-white font-bold'
              : 'text-slate-400 hover:text-slate-300'
          }`}
        >
          All Updates ({recentEvents.length})
        </button>
        <button
          onClick={() => setFilterMode('insights')}
          className={`px-2.5 py-1 rounded-md transition flex items-center space-x-1 ${
            filterMode === 'insights'
              ? 'bg-emerald-950 text-emerald-300 border border-emerald-500/40 font-bold'
              : 'text-slate-400 hover:text-slate-300'
          }`}
        >
          <Sparkles className="w-3 h-3 text-emerald-400" />
          <span>AI Insights ({insights.length})</span>
        </button>
        <button
          onClick={() => setFilterMode('commentary')}
          className={`px-2.5 py-1 rounded-md transition ${
            filterMode === 'commentary'
              ? 'bg-slate-800 text-white font-bold'
              : 'text-slate-400 hover:text-slate-300'
          }`}
        >
          Play-by-Play
        </button>
      </div>

      {/* Narrative Stream */}
      <div className="flex-1 overflow-y-auto space-y-2.5 pt-3 pr-1">
        {filterMode === 'insights' ? (
          // Insights Only View
          insights.length === 0 ? (
            <div className="h-48 flex flex-col items-center justify-center text-center text-slate-500 space-y-2">
              <Sparkles className="w-8 h-8 text-slate-600 animate-pulse" />
              <p className="text-sm">Synthesizing deep tactical moments...</p>
            </div>
          ) : (
            insights.slice().reverse().map((insight) => (
              <InsightCard
                key={insight.insight_id}
                insight={insight}
                currentLanguage={currentLanguage}
              />
            ))
          )
        ) : filterMode === 'commentary' ? (
          // Commentary Only View
          recentEvents.slice().reverse().map((ev) => (
            <CommentaryItem key={ev.event_id} event={ev} />
          ))
        ) : (
          // Unified Feed (All Events + Expanded Insights as people play!)
          recentEvents.slice().reverse().map((ev) => {
            const linkedInsight = insightsMap.get(ev.event_id);
            return (
              <div key={ev.event_id} className="space-y-1.5 animate-slide-up">
                <CommentaryItem event={ev} />
                {linkedInsight && (
                  <InsightCard
                    insight={linkedInsight}
                    currentLanguage={currentLanguage}
                  />
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

// Sub-Component: Play-by-Play Commentary Item
const CommentaryItem: React.FC<{ event: MatchEvent }> = ({ event }) => {
  const isHome = event.team === 'Manchester Blue';
  const badgeColor = isHome ? 'bg-sky-500/10 text-sky-400 border-sky-500/30' : 'bg-rose-500/10 text-rose-400 border-rose-500/30';

  return (
    <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80 hover:border-slate-700 transition flex items-start space-x-2.5 text-xs">
      {/* Match Clock Pill */}
      <span className="font-mono font-bold text-slate-400 bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800 shrink-0">
        {event.match_clock}
      </span>

      {/* Main Commentary Text & Telemetry Badges */}
      <div className="flex-1 space-y-1">
        <div className="flex items-center justify-between">
          <span className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${badgeColor}`}>
            {event.team}
          </span>

          <div className="flex items-center space-x-1.5 text-[10px] font-mono text-slate-400">
            <span>{event.telemetry.speed_kmh.toFixed(0)} km/h</span>
            {event.pass_difficulty_index !== undefined && (
              <span className="text-amber-400">PDR {(event.pass_difficulty_index * 100).toFixed(0)}%</span>
            )}
          </div>
        </div>

        <p className="text-slate-200 leading-snug">
          {event.commentary ?? `${event.player.name} carries possession in the ${event.context.pitch_zone.toLowerCase()}.`}
        </p>
      </div>
    </div>
  );
};

// Sub-Component: Full AI Insight Card
const InsightCard: React.FC<{ insight: MatchInsight; currentLanguage: SupportedLanguage }> = ({
  insight,
  currentLanguage,
}) => {
  const localizedHeadline =
    currentLanguage !== 'en' && insight.translated_versions?.[currentLanguage]
      ? insight.translated_versions[currentLanguage]
      : insight.headline;

  const isHighSignificance = insight.significance_score >= 8;

  return (
    <div
      className={`p-3.5 rounded-xl border transition-all duration-300 animate-slide-up ${
        isHighSignificance
          ? 'bg-gradient-to-br from-slate-900 to-emerald-950/50 border-emerald-500/50 shadow-md'
          : 'bg-slate-900/90 border-slate-800'
      }`}
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center space-x-2">
          <span className="flex items-center text-xs font-mono font-bold text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-500/30">
            <Clock className="w-3 h-3 mr-1" />
            {insight.match_clock}
          </span>
          <span className="text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
            {insight.persona.replace('_', ' ')}
          </span>
        </div>

        <div className="flex items-center space-x-1 text-xs font-mono">
          <Award className={`w-3.5 h-3.5 ${isHighSignificance ? 'text-amber-400' : 'text-slate-400'}`} />
          <span className={`font-bold ${isHighSignificance ? 'text-amber-400' : 'text-slate-400'}`}>
            {insight.significance_score}/10
          </span>
        </div>
      </div>

      <h4 className="font-display font-bold text-white text-sm tracking-wide leading-tight mb-1.5">
        {localizedHeadline}
      </h4>

      <div className="bg-slate-950/90 rounded-lg p-2 border border-slate-800/80 mb-1.5">
        <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider block mb-0.5">
          WHY IT MATTERS:
        </span>
        <p className="text-xs text-slate-200 leading-relaxed">
          {insight.why_it_matters}
        </p>
      </div>

      <p className="text-[11px] text-slate-400 leading-relaxed italic">
        💡 {insight.tactical_explanation}
      </p>
    </div>
  );
};
