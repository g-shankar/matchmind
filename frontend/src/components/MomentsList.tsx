import React, { useMemo } from 'react';
import { Award, Clock, History } from 'lucide-react';
import { useI18n } from '../i18n';
import type { ViewProps } from '../views/types';
import { Panel, cx } from './ui';
import { KIND_ICON, isSpecialKind } from './NarrativeFeed';

/** Where a jump lands: a few seconds of build-up before the moment. */
export const seekTarget = (clockS: number) => Math.max(0, clockS - 8);

type WithPeriod = { period?: number; clock_s: number };

// Bookmarks and playback carry a period; older payloads without one fall back to the clock.
const periodOf = (x: WithPeriod) => x.period ?? (x.clock_s >= 2700 ? 2 : 1);

/** Orders by (period, clock_s) so a second-half moment always comes after the first half. */
export const compareMoments = (a: WithPeriod, b: WithPeriod) => periodOf(a) - periodOf(b) || a.clock_s - b.clock_s;

export const MomentsList: React.FC<ViewProps> = ({ match, actions }) => {
  const { t } = useI18n();
  const now: WithPeriod = { clock_s: match.playback.clock_s, period: match.playback.period };
  const bookmarks = useMemo(() => match.bookmarks.slice().sort(compareMoments), [match.bookmarks]);

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
      {bookmarks.length === 0 ? (
        <p className="py-3 text-center text-sm text-pp-mute">{t('studio.moments.empty')}</p>
      ) : (
        <ul className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 sm:flex-wrap sm:overflow-visible">
          {bookmarks.map((b) => {
            const past = compareMoments(b, now) <= 0;
            const special = isSpecialKind(b.kind);
            // Upcoming moments stay spoiler-free (no goal or card titles), except the "should he have passed?" specials.
            const hidden = !past && !special;
            const Icon = hidden ? Clock : KIND_ICON[b.kind] ?? Award;
            const kindLabel = t(`kind.${b.kind}`);
            const title = hidden ? t('studio.moments.upcoming') : b.title;
            return (
              <li key={b.moment_id} className="shrink-0">
                <button
                  type="button"
                  onClick={() => actions.seek(seekTarget(b.clock_s), b.period)}
                  aria-label={t('studio.moments.jump', { clock: b.match_clock, title })}
                  title={past || hidden ? title : `${t('studio.moments.upcoming')}: ${title}`}
                  className={cx(
                    'flex min-h-[40px] max-w-[260px] items-center gap-2 rounded-xl border px-2.5 py-1.5 text-start text-xs transition hover:border-pp-pulse',
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
                  {!hidden && (
                  <span className="min-w-0">
                    {special && kindLabel !== b.title && <span className="block text-[10px] font-bold uppercase tracking-wider">{kindLabel}</span>}
                    <span className="line-clamp-1 block">{title}</span>
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
