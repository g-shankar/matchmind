// The moment rail above the pitch: goals and shots so far as marks on the match's length.
// A mark seeks playback through the studio's own jump (the same one the moments list uses).
// In catch-up mode every mark is withheld (no marks, shapes or count), because a missing
// mark, a gap or a goal's own shape would give the result away; the momentum ribbon is
// withheld as well, since a swing around a kick-off can hint at a goal.
import React, { useMemo } from 'react';
import type { Bookmark, MomentKind } from '../api/contract';
import type { MetricSample } from '../state/matchStore';
import { useI18n } from '../i18n';
import { compareMoments } from './MomentsList';
import { cx } from './ui';

export const GOAL_KINDS = new Set<MomentKind>(['goal']);
export const SHOT_KINDS = new Set<MomentKind>(['big_chance', 'rocket_shot']);
const FULL_MATCH_S = 90 * 60;
const HALF_S = 45 * 60;

export interface RailMark {
  b: Bookmark;
  type: 'goal' | 'shot';
  /** 0..100, along the match. */
  at: number;
}

/** The marks to draw, or null when the rail must stay hidden (catch-up mode). */
export function railMarks(bookmarks: Bookmark[], spoilers: boolean, now?: { clock_s: number; period?: number }): RailMark[] | null {
  if (!spoilers) return null;
  const picked = bookmarks
    .filter((b) => (!now || compareMoments(b, now) <= 0) && !b.ruled_out && (GOAL_KINDS.has(b.kind) || SHOT_KINDS.has(b.kind)))
    .sort(compareMoments);
  const span = Math.max(FULL_MATCH_S, ...picked.map((b) => b.clock_s + 60));
  return picked.map((b) => ({ b, type: GOAL_KINDS.has(b.kind) ? 'goal' : 'shot', at: Math.min(100, (b.clock_s / span) * 100) }));
}

export interface RibbonBar {
  x: number;
  w: number;
  /** -100..100: positive is the home side on top. */
  m: number;
}

/** The engine's momentum over match time, never past the playback clock. */
export function ribbonBars(history: Pick<MetricSample, 'clock_s' | 'momentum'>[], nowS: number, span: number): RibbonBar[] {
  const pts = history.filter((h) => h.clock_s <= nowS && Number.isFinite(h.momentum)).sort((a, b) => a.clock_s - b.clock_s);
  return pts.map((h, i) => {
    const next = pts[i + 1]?.clock_s ?? Math.min(nowS, h.clock_s + 30);
    return {
      x: (h.clock_s / span) * 100,
      w: Math.max(0.15, ((Math.max(next, h.clock_s) - h.clock_s) / span) * 100),
      m: Math.max(-100, Math.min(100, h.momentum)),
    };
  });
}

export const MomentRail: React.FC<{
  bookmarks: Bookmark[];
  spoilers: boolean;
  nowS: number;
  nowPeriod?: number;
  history?: Pick<MetricSample, 'clock_s' | 'momentum'>[];
  colors?: { home: string; away: string };
  onJump: (b: Bookmark) => void;
}> = ({ bookmarks, spoilers, nowS, nowPeriod, history = [], colors, onJump }) => {
  const { t } = useI18n();
  const marks = useMemo(() => railMarks(bookmarks, spoilers, { clock_s: nowS, period: nowPeriod }), [bookmarks, spoilers, nowS, nowPeriod]);
  const shown = marks ?? [];
  const span = Math.max(FULL_MATCH_S, nowS + 60, ...shown.map((m) => m.b.clock_s + 60));
  // Catch-up mode withholds the ribbon too: a momentum swing can hint at a goal.
  const bars = marks === null ? [] : ribbonBars(history, nowS, span);
  const now = Math.min(100, (nowS / span) * 100);
  const half = (HALF_S / span) * 100;
  return (
    <section aria-labelledby="moment-rail-title" data-testid={marks === null ? 'moment-rail-hidden' : 'moment-rail'} className="flex items-center gap-3 border border-pp-line bg-pp-panel px-3">
      <div className="flex shrink-0 flex-col justify-center">
        <h2 id="moment-rail-title" title={marks === null ? t('rail.hidden') : marks.length ? t('rail.hint') : t('rail.empty')} className="font-display text-[11px] font-extrabold uppercase italic leading-none tracking-broadcast text-pp-chalk">
          {t('rail.title')}
        </h2>
        {marks !== null && <span className="sr-only">{marks.length ? t('rail.hint') : t('rail.empty')}</span>}
        {marks === null ? (
          <span className="mt-0.5 max-w-[9rem] text-[9px] leading-tight text-pp-mute">{t('rail.hidden')}</span>
        ) : (
          <span aria-hidden className="mt-1 flex items-center gap-2 text-[9px] font-bold uppercase tracking-wider text-pp-mute">
            <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-pp-pulse" />{t('rail.legend.goal')}</span>
            <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rotate-45 bg-pp-signal" />{t('rail.legend.shot')}</span>
          </span>
        )}
      </div>
      {/* The match runs left to right on every page, like the scoreboard. */}
      <div dir="ltr" className="relative h-11 min-w-0 flex-1">
        {/* Momentum ribbon: the engine's value per sample, home above the line, away below. */}
        {bars.length > 0 && colors && (
          <svg aria-hidden data-testid="momentum-ribbon" viewBox="0 -100 100 200" preserveAspectRatio="none" className="absolute inset-x-0 top-1/2 h-8 w-full -translate-y-1/2 opacity-60">
            {bars.map((b, i) => (
              <rect key={i} x={b.x} width={b.w} y={b.m >= 0 ? -b.m : 0} height={Math.abs(b.m)} fill={b.m >= 0 ? colors.home : colors.away} />
            ))}
          </svg>
        )}
        <div aria-hidden className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 bg-pp-raised" />
        <div aria-hidden className="absolute start-0 top-1/2 h-1 -translate-y-1/2 bg-pp-turfLine/70" style={{ width: `${now}%` }} />
        <div aria-hidden className="absolute top-1 bottom-1 w-px bg-pp-line" style={{ left: `${half}%` }}>
          <span className="absolute -top-1 left-1 text-[9px] font-bold text-pp-mute">{t('rail.ht')}</span>
        </div>
        <ol className="contents">
          {shown.map((m) => {
            const label = t(m.type === 'goal' ? 'rail.goal' : 'rail.shot', { clock: m.b.match_clock });
            return (
              <li key={m.b.moment_id} className="contents">
                <button
                  type="button"
                  onClick={() => onJump(m.b)}
                  aria-label={label}
                  title={`${label}: ${m.b.title}`}
                  data-mark={m.type}
                  className="group absolute top-1/2 flex h-11 w-11 -translate-x-1/2 -translate-y-1/2 items-center justify-center focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
                  style={{ left: `${m.at}%` }}
                >
                  <span
                    aria-hidden
                    className={cx(
                      'block ring-2 ring-pp-night transition group-hover:scale-125 motion-reduce:transition-none motion-reduce:group-hover:scale-100',
                      m.type === 'goal' ? 'h-3.5 w-3.5 rounded-full bg-pp-pulse' : 'h-2.5 w-2.5 rotate-45 bg-pp-signal',
                    )}
                  />
                </button>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
};
