// The studio tour: five stops for a first-time visitor (or a judge), each one a button that
// opens the real screen. A docked panel, so the screen it opens stays usable behind it.
import React, { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Compass, ExternalLink, PlayCircle, X } from 'lucide-react';
import type { Bookmark, MomentKind } from '../api/contract';
import { compareMoments } from './MomentsList';
import { useI18n } from '../i18n';
import { cx } from './ui';

export const REPO_ARCHITECTURE_URL = 'https://github.com/g-shankar/matchmind/blob/main/docs/ARCHITECTURE.md';
export const TOUR_STOPS = 5;

/** Each stop's action; returns false when the screen has nothing to show yet. */
export interface TourActions {
  studio: () => boolean;
  decision: () => boolean;
  fanArabic: () => boolean;
  audit: () => boolean;
}

// The engine's own ranking of what matters most, by moment kind.
const KEY_RANK: Partial<Record<MomentKind, number>> = { goal: 0, better_option: 1, unfound_run: 2, correction: 3, big_chance: 4, card: 5, momentum_swing: 6 };

/** The tour's key moments: up to `n` of the highest-ranked bookmarks, in match order. */
export function keyMoments(bookmarks: Bookmark[], n = 5): Bookmark[] {
  return bookmarks
    .filter((b) => KEY_RANK[b.kind] !== undefined && !b.ruled_out)
    .map((b, i) => ({ b, i }))
    .sort((x, y) => KEY_RANK[x.b.kind]! - KEY_RANK[y.b.kind]! || x.i - y.i)
    .slice(0, n)
    .map((x) => x.b)
    .sort(compareMoments);
}

/** The key-moment run inside stop 1: where it is and how to move on. */
export interface KeyRun {
  index: number;
  total: number;
  current: Bookmark;
  paused: boolean;
}

const NONE_KEY: Record<number, string | undefined> = { 1: 'tour.s2.none', 3: 'tour.s4.none' };

export const StudioTour: React.FC<{
  open: boolean;
  onClose: () => void;
  go: TourActions;
  run?: KeyRun | null;
  onPlayKeys?: () => void;
  onNextKey?: () => void;
}> = ({ open, onClose, go, run = null, onPlayKeys, onNextKey }) => {
  const { t, dir } = useI18n();
  const [stop, setStop] = useState(0);
  const [visited, setVisited] = useState<Set<number>>(new Set());
  const [note, setNote] = useState<string | null>(null);
  const headRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (open) headRef.current?.focus();
  }, [open, stop]);
  useEffect(() => setNote(null), [stop]);
  if (!open) return null;

  const runStop = () => {
    const fns = [go.studio, go.decision, go.fanArabic, go.audit];
    const ok = stop < 4 ? fns[stop]() : true;
    setNote(ok ? null : t(NONE_KEY[stop] ?? 'tour.s2.none'));
    if (ok) setVisited((v) => new Set(v).add(stop));
  };
  const n = stop + 1;
  const done = visited.size === TOUR_STOPS;
  const btn =
    'inline-flex min-h-[44px] items-center gap-1.5 border px-3 font-display text-sm font-bold uppercase tracking-broadcast focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal';

  return (
    <aside
      dir={dir}
      role="region"
      aria-label={t('tour.label')}
      data-testid="studio-tour"
      onKeyDown={(e) => e.key === 'Escape' && onClose()}
      className="fixed inset-x-4 bottom-4 z-[55] mx-auto max-w-md border-t-4 lg:end-auto lg:mx-0 lg:w-[24rem] border-pp-signal bg-pp-panel shadow-2xl"
    >
      <div className="flex items-center gap-2 border-b border-pp-line bg-pp-deep ps-3">
        <Compass className="h-4 w-4 shrink-0 text-pp-signal" aria-hidden />
        <span className="font-display text-xs font-extrabold uppercase italic tracking-broadcast text-pp-chalk">{t('tour.open')}</span>
        <span className="ltr-nums ms-auto text-[11px] font-bold text-pp-mute" aria-live="polite">
          {t('tour.progress', { n, total: TOUR_STOPS })}
        </span>
        <button type="button" onClick={onClose} aria-label={t('tour.close')} className="flex h-11 w-11 shrink-0 items-center justify-center text-pp-mute hover:text-white">
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>
      {/* Progress: one segment per stop; filled once visited, outlined for the current one. */}
      <ol className="flex gap-1 px-3 pt-2" aria-label={t('tour.progress', { n, total: TOUR_STOPS })}>
        {Array.from({ length: TOUR_STOPS }, (_, i) => (
          <li key={i} className="flex-1">
            <button
              type="button"
              onClick={() => setStop(i)}
              aria-label={`${i + 1}. ${t(`tour.s${i + 1}.title`)}`}
              aria-current={i === stop ? 'step' : undefined}
              data-visited={visited.has(i) || undefined}
              className="flex h-6 w-full items-center focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
            >
              <span
                aria-hidden
                className={cx(
                  'block h-1.5 w-full',
                  visited.has(i) ? 'bg-pp-signal' : 'bg-pp-raised',
                  i === stop && 'outline outline-2 outline-offset-1 outline-pp-chalk',
                )}
              />
            </button>
          </li>
        ))}
      </ol>
      <div className="px-3 pb-3 pt-1">
        <h2 ref={headRef} tabIndex={-1} className="font-display text-lg font-extrabold uppercase italic tracking-broadcast text-pp-signal focus:outline-none">
          <span className="ltr-nums me-2 bg-pp-chalk px-1.5 not-italic text-pp-night">{String(n).padStart(2, '0')}</span>
          {t(`tour.s${n}.title`)}
        </h2>
        <p className="mt-1 text-sm text-slate-300">{t(`tour.s${n}.body`)}</p>
        {note && <p role="status" className="mt-2 border-s-2 border-pp-gold bg-pp-gold/10 px-2 py-1 text-xs text-pp-gold">{note}</p>}
        {stop === 0 && onPlayKeys && (
          <div className="mt-2 border-s-2 border-pp-signal bg-pp-deep px-2 py-1.5" data-testid="tour-keys">
            {run ? (
              <>
                <p className="ltr-nums text-[11px] font-bold uppercase tracking-wider text-pp-mute" aria-live="polite">
                  {t('tour.keys.progress', { n: run.index + 1, total: run.total })}
                </p>
                <p className="text-sm text-pp-chalk">
                  <span className="ltr-nums me-1 font-bold text-pp-signal">{run.current.match_clock}</span>
                  <bdi>{run.current.title}</bdi>
                </p>
                <p className="text-[11px] text-pp-mute">{t(run.paused ? 'tour.keys.paused' : 'tour.keys.playing')}</p>
                <button type="button" onClick={onNextKey} className={cx(btn, 'mt-1 border-pp-line text-pp-chalk')}>
                  {t(run.index + 1 < run.total ? 'tour.keys.next' : 'tour.keys.finish')}
                  <ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden />
                </button>
              </>
            ) : (
              <button type="button" onClick={onPlayKeys} className={cx(btn, 'border-pp-line text-pp-chalk')}>
                <PlayCircle className="h-4 w-4 text-pp-signal" aria-hidden />
                {t('tour.keys.play')}
              </button>
            )}
          </div>
        )}
        {done && <p role="status" className="mt-2 text-xs text-emerald-300">{t('tour.done')}</p>}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {stop === 4 ? (
            <a
              href={REPO_ARCHITECTURE_URL}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setVisited((v) => new Set(v).add(4))}
              className={cx(btn, 'border-pp-signal bg-pp-signal text-pp-night hover:bg-pp-chalk')}
            >
              {t('tour.go')}
              <ExternalLink className="h-4 w-4" aria-hidden />
            </a>
          ) : (
            <button type="button" onClick={runStop} className={cx(btn, 'border-pp-signal bg-pp-signal text-pp-night hover:bg-pp-chalk')}>
              {t('tour.go')}
            </button>
          )}
          <span className="ms-auto flex gap-1">
            <button type="button" disabled={stop === 0} onClick={() => setStop((s) => s - 1)} aria-label={t('tour.back')} title={t('tour.back')} className={cx(btn, 'w-11 justify-center border-pp-line px-0 text-pp-chalk disabled:opacity-40')}>
              <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden />
            </button>
            <button type="button" disabled={stop === TOUR_STOPS - 1} onClick={() => setStop((s) => s + 1)} className={cx(btn, 'border-pp-line text-pp-chalk disabled:opacity-40')}>
              {t('tour.next')}
              <ArrowRight className="h-4 w-4 rtl:rotate-180" aria-hidden />
            </button>
          </span>
        </div>
      </div>
    </aside>
  );
};
