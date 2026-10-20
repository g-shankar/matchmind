import React, { useState, useMemo } from 'react';
import { MatchInsight, MatchEvent, SupportedLanguage } from '../types';
import {
  Sparkles,
  Globe2,
  BrainCircuit,
  Award,
  Clock,
  Radio,
  Zap,
  Activity,
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

const UI_STRINGS: Record<SupportedLanguage, {
  feed_title: string;
  stream: string;
  all_updates: string;
  ai_insights: string;
  play_by_play: string;
  why_it_matters: string;
  tactical_prefix: string;
  just_now: string;
  speed: string;
  empty_insights: string;
}> = {
  en: {
    feed_title: "Live Match Intelligence Feed",
    stream: "Stream:",
    all_updates: "All Updates",
    ai_insights: "AI Insights",
    play_by_play: "Play-by-Play",
    why_it_matters: "WHY IT MATTERS:",
    tactical_prefix: "TACTICAL INSIGHT",
    just_now: "JUST NOW",
    speed: "km/h",
    empty_insights: "Synthesizing deep tactical moments..."
  },
  fr: {
    feed_title: "Flux d'Intelligence du Match en Direct",
    stream: "Flux :",
    all_updates: "Toutes les Mises à Jour",
    ai_insights: "Analyses IA",
    play_by_play: "Direct Commenté",
    why_it_matters: "POURQUOI C'EST DÉCISIF :",
    tactical_prefix: "ANALYSE TACTIQUE",
    just_now: "À L'INSTANT",
    speed: "km/h",
    empty_insights: "Synthèse des moments tactiques décisifs..."
  },
  es: {
    feed_title: "Transmisión de Inteligencia en Vivo",
    stream: "Transmisión:",
    all_updates: "Todas las Actualizaciones",
    ai_insights: "Análisis IA",
    play_by_play: "Minuto a Minuto",
    why_it_matters: "¿POR QUÉ ES CLAVE? :",
    tactical_prefix: "ANÁLISIS TÁCTICO",
    just_now: "AHORA MISMO",
    speed: "km/h",
    empty_insights: "Sintetizando momentos tácticos clave..."
  },
  ar: {
    feed_title: "بث تحليلات المباراة المباشر",
    stream: "البث المباشر:",
    all_updates: "كافة التحديثات",
    ai_insights: "تحليلات الذكاء الاصطناعي",
    play_by_play: "وصف تفصيلي",
    why_it_matters: "لماذا هذا مهم؟ :",
    tactical_prefix: "التحليل التكتيكي",
    just_now: "الآن",
    speed: "كم/س",
    empty_insights: "جاري تحليل اللحظات التكتيكية الحاسمة..."
  },
  ja: {
    feed_title: "ライブ試合インテリジェンス",
    stream: "タイムライン:",
    all_updates: "全アップデート",
    ai_insights: "AI戦術インサイト",
    play_by_play: "実況テキスト",
    why_it_matters: "勝負の分かれ目 :",
    tactical_prefix: "戦術分析",
    just_now: "たった今",
    speed: "km/h",
    empty_insights: "戦術的なキーモーメントを分析中..."
  }
};

interface StackItem {
  id: string;
  type: 'insight' | 'commentary';
  clock: string;
  timestamp: number;
  event?: MatchEvent;
  insight?: MatchInsight;
}

export const NarrativeFeed: React.FC<NarrativeFeedProps> = ({
  insights,
  recentEvents,
  currentLanguage,
  onLanguageChange,
}) => {
  const [filterMode, setFilterMode] = useState<'all' | 'insights' | 'commentary'>('all');
  const t = UI_STRINGS[currentLanguage] || UI_STRINGS.en;

  // Build a true Stack: Newest Items ALWAYS at the Top (LIFO stack ordering)
  const stackItems = useMemo<StackItem[]>(() => {
    const items: StackItem[] = [];

    // Add commentary events
    recentEvents.forEach((ev) => {
      items.push({
        id: `ev-${ev.event_id}`,
        type: 'commentary',
        clock: ev.match_clock,
        timestamp: ev.timestamp_seconds,
        event: ev,
      });
    });

    // Add AI insights with slight timestamp advantage (+0.001) so an insight for a moment sits ABOVE its commentary
    insights.forEach((ins) => {
      // Find matching event timestamp or estimate from clock
      const parentEvent = recentEvents.find((e) => e.event_id === ins.event_id);
      const baseTs = parentEvent ? parentEvent.timestamp_seconds : 0;
      items.push({
        id: `ins-${ins.insight_id}`,
        type: 'insight',
        clock: ins.match_clock,
        timestamp: baseTs + 0.001,
        insight: ins,
      });
    });

    // Sort strictly descending by timestamp: Newest (latest) at the very top!
    items.sort((a, b) => b.timestamp - a.timestamp);

    return items;
  }, [recentEvents, insights]);

  // Filter based on active tab
  const filteredItems = useMemo(() => {
    if (filterMode === 'insights') {
      return stackItems.filter((item) => item.type === 'insight');
    }
    if (filterMode === 'commentary') {
      return stackItems.filter((item) => item.type === 'commentary');
    }
    return stackItems;
  }, [stackItems, filterMode]);

  return (
    <div className="bg-slate-900/80 backdrop-blur-md rounded-xl p-5 border border-slate-800 shadow-xl flex flex-col h-full max-h-[640px]">
      {/* Header with Multi-Language Switcher */}
      <div className="flex flex-wrap items-center justify-between border-b border-slate-800/80 pb-3 gap-2">
        <div className="flex items-center space-x-2">
          <BrainCircuit className="w-5 h-5 text-emerald-400" />
          <h3 className="font-display font-semibold text-white tracking-wide text-sm uppercase">
            {t.feed_title}
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
        <span className="text-slate-500 text-[11px] uppercase tracking-wider font-mono">
          {t.stream}
        </span>
        <button
          onClick={() => setFilterMode('all')}
          className={`px-2.5 py-1 rounded-md transition ${
            filterMode === 'all'
              ? 'bg-slate-800 text-white font-bold'
              : 'text-slate-400 hover:text-slate-300'
          }`}
        >
          {t.all_updates} ({stackItems.length})
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
          <span>{t.ai_insights} ({insights.length})</span>
        </button>
        <button
          onClick={() => setFilterMode('commentary')}
          className={`px-2.5 py-1 rounded-md transition ${
            filterMode === 'commentary'
              ? 'bg-slate-800 text-white font-bold'
              : 'text-slate-400 hover:text-slate-300'
          }`}
        >
          {t.play_by_play}
        </button>
      </div>

      {/* Narrative Stream: LIFO Stack with Most Recent at Top */}
      <div className="flex-1 overflow-y-auto space-y-2.5 pt-3 pr-1">
        {filteredItems.length === 0 ? (
          <div className="h-48 flex flex-col items-center justify-center text-center text-slate-500 space-y-2">
            <Sparkles className="w-8 h-8 text-slate-600 animate-pulse" />
            <p className="text-sm">{t.empty_insights}</p>
          </div>
        ) : (
          filteredItems.map((item, index) => {
            const isTopItem = index === 0;

            if (item.type === 'insight' && item.insight) {
              return (
                <InsightCard
                  key={item.id}
                  insight={item.insight}
                  currentLanguage={currentLanguage}
                  isTop={isTopItem}
                  justNowLabel={t.just_now}
                  whyItMattersLabel={t.why_it_matters}
                />
              );
            }

            if (item.type === 'commentary' && item.event) {
              return (
                <CommentaryItem
                  key={item.id}
                  event={item.event}
                  currentLanguage={currentLanguage}
                  isTop={isTopItem}
                  speedUnit={t.speed}
                  justNowLabel={t.just_now}
                />
              );
            }

            return null;
          })
        )}
      </div>
    </div>
  );
};

// Sub-Component: Play-by-Play Commentary Item
const CommentaryItem: React.FC<{
  event: MatchEvent;
  currentLanguage: SupportedLanguage;
  isTop: boolean;
  speedUnit: string;
  justNowLabel: string;
}> = ({ event, currentLanguage, isTop, speedUnit, justNowLabel }) => {
  const isHome = event.team === 'Manchester Blue';
  const badgeColor = isHome
    ? 'bg-sky-500/10 text-sky-400 border-sky-500/30'
    : 'bg-rose-500/10 text-rose-400 border-rose-500/30';

  // Localized Commentary text
  const localizedText =
    currentLanguage !== 'en' && event.translations?.[currentLanguage]
      ? event.translations[currentLanguage]
      : event.commentary ??
        `${event.player.name} carries possession in the ${event.context.pitch_zone.toLowerCase()}.`;

  return (
    <div
      className={`p-2.5 rounded-lg border transition-all duration-300 animate-slide-up flex items-start space-x-2.5 text-xs ${
        isTop
          ? 'bg-slate-950/90 border-emerald-500/50 shadow-md ring-1 ring-emerald-500/20'
          : 'bg-slate-950/70 border-slate-800/80 hover:border-slate-700'
      }`}
    >
      {/* Match Clock Pill */}
      <div className="flex flex-col items-center shrink-0 space-y-1">
        <span className="font-mono font-bold text-slate-400 bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800 text-[11px]">
          {event.match_clock}
        </span>
        {isTop && (
          <span className="text-[9px] font-mono font-extrabold text-emerald-400 animate-pulse tracking-tighter">
            {justNowLabel}
          </span>
        )}
      </div>

      {/* Main Commentary Text & Telemetry Badges */}
      <div className="flex-1 space-y-1">
        <div className="flex items-center justify-between">
          <span className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${badgeColor}`}>
            {event.team}
          </span>

          <div className="flex items-center space-x-1.5 text-[10px] font-mono text-slate-400">
            <span>{event.telemetry.speed_kmh.toFixed(0)} {speedUnit}</span>
            {event.pass_difficulty_index !== undefined && (
              <span className="text-amber-400">PDR {(event.pass_difficulty_index * 100).toFixed(0)}%</span>
            )}
          </div>
        </div>

        <p className="text-slate-200 leading-snug">
          {localizedText}
        </p>
      </div>
    </div>
  );
};

// Sub-Component: Full AI Insight Card
const InsightCard: React.FC<{
  insight: MatchInsight;
  currentLanguage: SupportedLanguage;
  isTop: boolean;
  justNowLabel: string;
  whyItMattersLabel: string;
}> = ({ insight, currentLanguage, isTop, justNowLabel, whyItMattersLabel }) => {
  // Retrieve comprehensive localized translation
  const localizedData =
    currentLanguage !== 'en' && insight.translations?.[currentLanguage]
      ? insight.translations[currentLanguage]
      : null;

  const localizedHeadline =
    localizedData?.headline ||
    (currentLanguage !== 'en' && insight.translated_versions?.[currentLanguage]) ||
    insight.headline;

  const localizedWhy = localizedData?.why_it_matters || insight.why_it_matters;
  const localizedTactical = localizedData?.tactical_explanation || insight.tactical_explanation;

  const isHighSignificance = insight.significance_score >= 8;

  return (
    <div
      className={`p-3.5 rounded-xl border transition-all duration-300 animate-slide-up ${
        isTop
          ? 'ring-2 ring-emerald-500/40 shadow-lg'
          : ''
      } ${
        isHighSignificance
          ? 'bg-gradient-to-br from-slate-900 via-slate-900 to-emerald-950/60 border-emerald-500/60 shadow-md'
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
          {isTop && (
            <span className="text-[9px] font-mono font-extrabold bg-emerald-500 text-black px-1.5 py-0.5 rounded uppercase tracking-wider animate-pulse">
              {justNowLabel}
            </span>
          )}
        </div>

        <div className="flex items-center space-x-1 text-xs font-mono">
          <Award className={`w-3.5 h-3.5 ${isHighSignificance ? 'text-amber-400' : 'text-slate-400'}`} />
          <span className={`font-bold ${isHighSignificance ? 'text-amber-400' : 'text-slate-400'}`}>
            {insight.significance_score}/10
          </span>
        </div>
      </div>

      <h4 className="font-display font-bold text-white text-base tracking-wide leading-tight mb-2">
        {localizedHeadline}
      </h4>

      <div className="bg-slate-950/90 rounded-lg p-2.5 border border-slate-800/80 mb-2">
        <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider block mb-0.5">
          {whyItMattersLabel}
        </span>
        <p className="text-xs text-slate-200 leading-relaxed">
          {localizedWhy}
        </p>
      </div>

      <p className="text-[11px] text-slate-400 leading-relaxed italic">
        💡 {localizedTactical}
      </p>
    </div>
  );
};
