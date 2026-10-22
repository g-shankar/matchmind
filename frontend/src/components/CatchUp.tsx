// Catch-up mode (docs/PERSONALISATION.md, "Spoiler-safe catch-up"): the viewer
// joins late and keeps the result hidden until they reveal it. The server (or
// the offline demo) leaves the score, goals and VAR outcomes out of every
// payload; these components show that state and the ways out of it.
import React, { useEffect, useRef, useState } from 'react';
import { BookOpen, Eye, EyeOff, Radio, SkipForward, Square, Tv } from 'lucide-react';
import type { Bookmark } from '../api/contract';
import { useI18n } from '../i18n';
import type { MatchViewState } from '../state/matchStore';
import type { MatchActions } from '../state/useMatch';
import { seekTarget } from './MomentsList';
import { cx } from './ui';

/** One side of a score, or a marked placeholder while it is hidden. */
export const ScoreValue: React.FC<{ value: number | null | undefined }> = ({ value }) => {
  const { t } = useI18n();
  if (value !== null && value !== undefined) return <>{value}</>;
  return (
    <span title={t('catchup.hiddenScore')} data-testid="score-hidden">
      <span aria-hidden>?</span>
      <span className="sr-only">{t('catchup.hiddenValue')}</span>
    </span>
  );
};

/** Header switch into catch-up mode (shown while the result is visible). */
export const CatchUpButton: React.FC<{ match: MatchViewState; actions: MatchActions }> = ({ match, actions }) => {
  const { t } = useI18n();
  if (!match.profile.spoilers) return null;
  return (
    <button
      type="button"
      onClick={() => actions.setSpoilers(false)}
      title={t('catchup.openHint')}
      className="flex min-h-[44px] items-center gap-1.5 border border-pp-line bg-pp-deep px-2.5 font-display text-xs font-bold uppercase tracking-broadcast text-pp-chalk hover:border-pp-signal"
    >
      <EyeOff className="h-4 w-4 text-pp-signal" aria-hidden />
      {t('catchup.open')}
    </button>
  );
};

const KEY_KINDS = new Set(['big_chance', 'better_option', 'unfound_run', 'card', 'momentum_swing', 'pressure_spell']);
const AUTO_NEXT_MS = 15000;
const MAX_KEY_MOMENTS = 6;

const before = (b: { period: number; clock_s: number }, at: { period: number; clock_s: number }) =>
  b.period < at.period || (b.period === at.period && b.clock_s <= at.clock_s);

/** The moments worth replaying so far, oldest first, none that gives the result away. */
export function keyMoments(bookmarks: Bookmark[], at: { period: number; clock_s: number }): Bookmark[] {
  return bookmarks
    .filter((b) => KEY_KINDS.has(b.kind) && !b.ruled_out && before(b, at))
    .sort((a, b) => a.period - b.period || a.clock_s - b.clock_s)
    .slice(-MAX_KEY_MOMENTS);
}

/** Banner under the header in catch-up mode: reveal, story so far, key moments, back to live. */
export const CatchUpBanner: React.FC<{ match: MatchViewState; actions: MatchActions; onStory: () => void }> = ({
  match,
  actions,
  onStory,
}) => {
  const { t } = useI18n();
  const [tour, setTour] = useState<{ list: Bookmark[]; index: number; live: { clock_s: number; period: number } } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const spoilers = match.profile.spoilers;

  const stopTimer = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };
  useEffect(() => stopTimer, []);
  // Revealing ends the tour where it is.
  useEffect(() => {
    if (spoilers) {
      stopTimer();
      setTour(null);
    }
  }, [spoilers]);

  const play = (list: Bookmark[], index: number, live: { clock_s: number; period: number }) => {
    stopTimer();
    if (index >= list.length) return backToLive(live);
    const b = list[index];
    actions.seek(seekTarget(b.clock_s), b.period);
    setTour({ list, index, live });
    timer.current = setTimeout(() => play(list, index + 1, live), AUTO_NEXT_MS);
  };

  const backToLive = (live: { clock_s: number; period: number }) => {
    stopTimer();
    setTour(null);
    actions.seek(live.clock_s, live.period);
  };

  if (spoilers) return null;
  const at = { clock_s: match.playback.clock_s, period: match.playback.period };
  const moments = keyMoments(match.bookmarks, tour?.live ?? at);
  const btn =
    'flex min-h-[40px] items-center gap-1.5 px-3 font-display text-xs font-bold uppercase tracking-broadcast transition';

  return (
    <section
      aria-label={t('catchup.open')}
      data-testid="catchup-banner"
      className="border-b border-pp-signal/40 bg-pp-signal/10 px-4 py-2 text-sm text-pp-chalk"
    >
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2">
          <EyeOff className="h-4 w-4 shrink-0 text-pp-signal" aria-hidden />
          <span>{t('catchup.banner')}</span>
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={onStory} className={cx(btn, 'border border-pp-line bg-pp-deep hover:border-pp-signal')}>
            <BookOpen className="h-4 w-4" aria-hidden />
            {t('catchup.story')}
          </button>
          {tour ? (
            <>
              <span role="status" aria-live="polite" className="ltr-nums text-xs text-pp-signal">
                {t('catchup.watching', { n: tour.index + 1, total: tour.list.length })} · {tour.list[tour.index].match_clock}
              </span>
              <button type="button" onClick={() => play(tour.list, tour.index + 1, tour.live)} className={cx(btn, 'border border-pp-line bg-pp-deep hover:border-pp-signal')}>
                <SkipForward className="h-4 w-4" aria-hidden />
                {t('catchup.next')}
              </button>
              <button type="button" onClick={() => backToLive(tour.live)} className={cx(btn, 'bg-pp-pulse text-white hover:bg-pp-chalk hover:text-pp-night')}>
                <Radio className="h-4 w-4" aria-hidden />
                {t('catchup.jumpLive')}
              </button>
              <button type="button" onClick={() => { stopTimer(); setTour(null); }} aria-label={t('catchup.stop')} className={cx(btn, 'border border-pp-line bg-pp-deep')}>
                <Square className="h-3.5 w-3.5" aria-hidden />
              </button>
            </>
          ) : (
            <button
              type="button"
              disabled={!moments.length}
              title={moments.length ? t('catchup.sharedNote') : t('catchup.noMoments')}
              onClick={() => play(moments, 0, at)}
              className={cx(btn, 'border border-pp-line bg-pp-deep hover:border-pp-signal disabled:opacity-40')}
            >
              <Tv className="h-4 w-4" aria-hidden />
              {t('catchup.watch')}
            </button>
          )}
          <button type="button" onClick={() => actions.setSpoilers(true)} className={cx(btn, 'bg-pp-signal text-pp-night hover:bg-pp-chalk')}>
            <Eye className="h-4 w-4" aria-hidden />
            {t('catchup.reveal')}
          </button>
        </div>
      </div>
    </section>
  );
};
