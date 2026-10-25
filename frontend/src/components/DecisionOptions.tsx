import React, { useId, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { BetterOptionReplay, DecisionOption, Teams } from '../api/contract';
import { useI18n } from '../i18n';
import { playerById, shortName } from '../lib/teams';
import { cx } from './ui';

/** Collapsed, the ladder shows the top options plus the action taken (and the one being viewed). */
const TOP = 3;
/** Scores are the engine's values (3 dp), shown as sent: nothing is recomputed here. */
const SCORE_DECIMALS = 3;

export interface DecisionOptionsProps {
  replay: BetterOptionReplay;
  teams: Teams | null;
  selected: number;
  onSelect: (index: number) => void;
}

/** "Every option, ranked by the engine": a stepper plus a compact ranked ladder with score bars.
 * The action the player chose is tagged; the pitch draws the selected option's line. */
export const DecisionOptions: React.FC<DecisionOptionsProps> = ({ replay, teams, selected, onSelect }) => {
  const { t, num, dir } = useI18n();
  const [all, setAll] = useState(false);
  const titleId = `pp-options-${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const options = replay.options ?? [];
  if (options.length === 0) return null;
  const max = Math.max(...options.map((o) => o.score), 1e-9);
  const total = options.length;
  const at = Math.min(Math.max(selected, 0), total - 1);
  const go = (i: number) => onSelect((i + total) % total);

  const label = (o: DecisionOption) => {
    if (o.kind === 'shot') return t('pitch.options.shot');
    const p = playerById(teams, o.player_id);
    return t('pitch.options.pass', { name: p ? shortName(p.name) : o.player_id });
  };
  const score = (o: DecisionOption) => num(o.score, SCORE_DECIMALS);
  const cur = options[at];

  const onKey = (e: React.KeyboardEvent) => {
    const back = dir === 'rtl' ? 'ArrowRight' : 'ArrowLeft';
    const fwd = dir === 'rtl' ? 'ArrowLeft' : 'ArrowRight';
    if (e.key === back || e.key === 'ArrowUp') go(at - 1);
    else if (e.key === fwd || e.key === 'ArrowDown') go(at + 1);
    else if (e.key === 'Home') onSelect(0);
    else if (e.key === 'End') onSelect(total - 1);
    else return;
    e.preventDefault();
  };

  const Prev = dir === 'rtl' ? ChevronRight : ChevronLeft;
  const Next = dir === 'rtl' ? ChevronLeft : ChevronRight;
  const navBtn =
    'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-pp-line text-slate-200 transition hover:border-pp-signal hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal';

  return (
    <section
      className="mt-4 rounded-xl border border-pp-line bg-pp-deep/60 p-3"
      aria-labelledby={titleId}
      onKeyDown={onKey}
      data-testid="decision-options"
    >
      <div className="flex items-center gap-2">
        <h3 id={titleId} className="min-w-0 flex-1 font-display text-sm font-bold uppercase tracking-wide text-white">
          {t('pitch.options.title')}
        </h3>
        <button type="button" className={navBtn} onClick={() => go(at - 1)} aria-label={t('pitch.options.prev')} data-testid="option-prev">
          <Prev className="h-4 w-4" aria-hidden />
        </button>
        <button type="button" className={navBtn} onClick={() => go(at + 1)} aria-label={t('pitch.options.next')} data-testid="option-next">
          <Next className="h-4 w-4" aria-hidden />
        </button>
      </div>
      <p className="sr-only" aria-live="polite" data-testid="option-live">
        {t('pitch.options.showing', { n: at + 1, total, label: label(cur), v: score(cur) })}
      </p>
      <p className="sr-only">{t('pitch.options.keys')}</p>

      <ol className="mt-2 flex flex-col gap-1" aria-label={t('pitch.options.list')}>
        {options.map((o, i) => {
          const active = i === at;
          if (!all && i >= TOP && !o.taken && !active) return null;
          const tags = [o.taken && t('pitch.options.taken'), !o.onside && t('pitch.options.offside'), o.onside && !o.open && t('pitch.options.marked')].filter(Boolean) as string[];
          return (
            <li key={`${o.kind}-${o.player_id}`}>
              <button
                type="button"
                onClick={() => onSelect(i)}
                aria-current={active ? 'true' : undefined}
                aria-label={`${o.rank}. ${label(o)}${tags.length ? ` (${tags.join(', ')})` : ''}, ${t('pitch.options.score', { v: score(o) })}`}
                data-testid="option-row"
                className={cx(
                  'grid min-h-11 w-full grid-cols-[1.5rem_minmax(0,1fr)_3.5rem] items-center gap-2 rounded-lg border px-2 py-1 text-start transition focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal',
                  active ? 'border-pp-signal/70 bg-pp-raised' : 'border-transparent hover:border-pp-line',
                  !o.eligible && 'opacity-70',
                )}
              >
                <span className="ltr-nums text-xs font-bold text-pp-mute">{o.rank}</span>
                <span className="min-w-0">
                  <span className="flex flex-wrap items-center gap-1.5">
                    <span className="truncate text-xs font-semibold text-white sm:text-sm">{label(o)}</span>
                    {tags.map((tag) => (
                      <span
                        key={tag}
                        className={cx(
                          'rounded px-1 text-[10px] font-bold uppercase tracking-wider',
                          o.taken && tag === t('pitch.options.taken') ? 'bg-pp-gold text-pp-night' : 'bg-pp-line text-slate-200',
                        )}
                        data-testid={o.taken && tag === t('pitch.options.taken') ? 'option-taken' : undefined}
                      >
                        {tag}
                      </span>
                    ))}
                  </span>
                  <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-pp-line/60" aria-hidden>
                    <span
                      className={cx('block h-full rounded-full', o.taken ? 'bg-pp-gold' : active ? 'bg-pp-signal' : 'bg-slate-400')}
                      style={{ width: `${Math.max(2, (o.score / max) * 100)}%` }}
                    />
                  </span>
                </span>
                <span className="ltr-nums text-end text-xs font-bold text-white">{score(o)}</span>
              </button>
            </li>
          );
        })}
      </ol>

      {total > TOP + 1 && (
        <button
          type="button"
          onClick={() => setAll((v) => !v)}
          aria-expanded={all}
          data-testid="option-expand"
          className="mt-1 min-h-11 rounded-lg px-2 text-xs font-semibold text-pp-signal hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
        >
          {all ? t('pitch.options.fewer') : t('pitch.options.all', { n: total })}
        </button>
      )}
      <p className="mt-1 text-[11px] leading-snug text-pp-mute">
        <span className="font-semibold text-slate-300" data-testid="option-method">{t('pitch.options.method', { v: replay.method_version ?? 1 })}</span>
        <span aria-hidden> · </span>
        <span data-testid="option-caveat">{t('pitch.options.caveat')}</span>
      </p>
    </section>
  );
};
