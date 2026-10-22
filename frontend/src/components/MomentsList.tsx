import type { Bookmark, MomentKind } from '../api/contract';
import React, { useMemo, useState } from 'react';
import { Award, ChevronDown, Clock, History, Play } from 'lucide-react';
import { useI18n } from '../i18n';
import type { ViewProps } from '../views/types';
import { Panel, cx } from './ui';
import { KIND_ICON, isSpecialKind } from './NarrativeFeed';
import { groupByClock, upcomingLabelKey } from '../lib/labels';

/** Where a jump lands: a few seconds of build-up before the moment. */
export const seekTarget = (clockS: number) => Math.max(0, clockS - 8);

// Small on-pitch tags stay on the pitch; the jump list keeps the story moments.
const MINOR_KINDS = new Set<MomentKind>(['speed_burst', 'rocket_shot', 'distance_milestone', 'hard_pass']);

type WithPeriod = { period?: number; clock_s: number };

// Bookmarks and playback carry a period; older payloads without one fall back to the clock.
const periodOf = (x: WithPeriod) => x.period ?? (x.clock_s >= 2700 ? 2 : 1);

/** Orders by (period, clock_s) so a second-half moment always comes after the first half. */
export const compareMoments = (a: WithPeriod, b: WithPeriod) => periodOf(a) - periodOf(b) || a.clock_s - b.clock_s;

export const MomentsList: React.FC<ViewProps & { onJump?: (b: Bookmark) => void }> = ({ match, actions, onJump }) => {
  const { t } = useI18n();
  const now: WithPeriod = { clock_s: match.playback.clock_s, period: match.playback.period };
  const bookmarks = useMemo(
    () => match.bookmarks.filter((b) => !MINOR_KINDS.has(b.kind)).sort(compareMoments),
    [match.bookmarks],
  );
  const groups = useMemo(() => groupByClock(bookmarks), [bookmarks]);
  const jump = onJump ?? ((b: Bookmark) => actions.seek(seekTarget(b.clock_s), b.period));
  // The moments with a step-by-step replay come first, in their own short row; the long
  // list of every moment folds away under it (open by default only when there are none).
  const keyReplays = useMemo(() => bookmarks.filter((b) => isSpecialKind(b.kind)), [bookmarks]);
  const [showAll, setShowAll] = useState<boolean | null>(null);
  const allOpen = showAll ?? keyReplays.length === 0;
  const listId = useMemo(() => `moments-all-${Math.random().toString(36).slice(2, 8)}`, []);

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <History className="h-4 w-4 text-pp-gold" aria-hidden />
          {t('studio.moments.title')}
        </span>
      }
      actions={<span className="hidden text-[11px] text-pp-mute sm:inline">{t('studio.moments.hint')}</span>}
    >
      {bookmarks.length > 0 && keyReplays.length > 0 && (
        <section aria-labelledby={`${listId}-key`} className="mb-3" data-testid="key-replays">
          <h3 id={`${listId}-key`} className="font-display text-sm font-extrabold uppercase italic tracking-broadcast text-pp-gold">
            {t('guide.moments.key')}
          </h3>
          <p className="mb-2 text-[11px] text-pp-mute">{t('guide.moments.keyHint')}</p>
          <ul className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            {keyReplays.map((b) => {
              const past = compareMoments(b, now) <= 0;
              const title = b.title;
              return (
                <li key={b.moment_id}>
                  <button
                    type="button"
                    onClick={() => jump(b)}
                    aria-label={t('studio.moments.jump', { clock: b.match_clock, title })}
                    className="flex min-h-[44px] w-full items-center gap-2 border border-pp-gold/70 bg-pp-gold/10 px-3 py-1.5 text-start text-sm text-pp-gold hover:border-pp-pulse sm:w-auto sm:max-w-[320px]"
                  >
                    <Play className="h-4 w-4 shrink-0" aria-hidden />
                    <span className="ltr-nums shrink-0 font-bold text-pp-signal">{b.match_clock}</span>
                    <span className="min-w-0">
                      <span className="line-clamp-1 block font-semibold">{title}</span>
                      <span className="block text-[10px] font-bold uppercase tracking-wider text-pp-mute">
                        {t(`kind.${b.kind}`)}
                        {!past && ` · ${t('guide.moments.keyComing')}`}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}
      {bookmarks.length > 0 && keyReplays.length > 0 && (
        <button
          type="button"
          aria-expanded={allOpen}
          aria-controls={listId}
          onClick={() => setShowAll(!allOpen)}
          className="mb-2 inline-flex min-h-[44px] items-center gap-1.5 border border-pp-line bg-pp-deep px-3 font-display text-sm font-bold uppercase tracking-broadcast text-pp-chalk hover:border-pp-signal"
        >
          <ChevronDown className={cx('h-4 w-4 transition', allOpen && 'rotate-180')} aria-hidden />
          {allOpen ? t('guide.moments.hideAll') : t('guide.moments.showAll', { n: groups.length })}
        </button>
      )}
      {bookmarks.length === 0 ? (
        <p className="py-3 text-center text-sm text-pp-mute">{t('studio.moments.empty')}</p>
      ) : !allOpen ? null : (
        <ul id={listId} className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 sm:flex-wrap sm:overflow-visible">
          {groups.map(({ lead: b, count }) => {
            const past = compareMoments(b, now) <= 0;
            const special = isSpecialKind(b.kind);
            // Upcoming moments stay spoiler-free (no goal or card titles), except the "should he have passed?" specials.
            const hidden = !past && !special;
            const Icon = hidden ? Clock : KIND_ICON[b.kind] ?? Award;
            const kindLabel = t(`kind.${b.kind}`);
            // Upcoming: say what sort of moment it is, never what happens.
            const title = hidden ? t(upcomingLabelKey(b.kind)) : b.title;
            // A goal later ruled out by VAR is flagged only once the decision is in the past (no spoilers).
            const ruled =
              !!b.ruled_out &&
              past &&
              (match.cue.ruledOut.includes(b.moment_id) ||
                bookmarks.some((c) => c.kind === 'correction' && compareMoments(c, now) <= 0 && compareMoments(c, b) > 0));
            return (
              <li key={b.moment_id} className="shrink-0">
                <button
                  type="button"
                  onClick={() => jump(b)}
                  aria-label={t('studio.moments.jump', { clock: b.match_clock, title })}
                  title={past || hidden ? title : `${t('studio.moments.upcoming')}: ${title}`}
                  className={cx(
                    'flex min-h-[44px] max-w-[260px] items-center gap-2 rounded-xl border px-2.5 py-1.5 text-start text-xs transition hover:border-pp-pulse',
                    special
                      ? 'border-pp-gold/60 bg-pp-gold/10 text-pp-gold'
                      : past
                        ? 'border-pp-line bg-pp-raised text-slate-100'
                        : 'border-dashed border-pp-line/70 bg-transparent text-pp-mute',
                    !past && 'opacity-70',
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden />
                  <span className="ltr-nums shrink-0 font-bold text-pp-signal">{b.match_clock}</span>
                  {hidden && <span className="text-[11px] uppercase tracking-wider">{title}</span>}
                  {!hidden && (
                  <span className="min-w-0">
                    {special && kindLabel !== b.title && <span className="block text-[10px] font-bold uppercase tracking-wider">{kindLabel}</span>}
                    <span className={cx('line-clamp-1 block', ruled && 'line-through decoration-pp-pulse')}>{title}</span>
                    {count > 1 && <span className="block text-[10px] text-pp-mute">{t('visit.moments.count', { n: count })}</span>}
                    {ruled && (
                      <span data-testid="moment-ruled-out" className="block text-[10px] font-bold uppercase tracking-wider text-pp-pulse">
                        {t('cue.ruledOut')}
                      </span>
                    )}
                  </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
};
