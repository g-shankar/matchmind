// The crew rundown: for one moment, the five desks in running order (spotter, analyst,
// commentator, producer, fact-checker), drawn like a production-gallery rundown. Every line
// comes from the moment's audit (GET /api/match/moment/{id}/audit) and the crew's trace;
// a step the recording did not log says so instead of making a value up.
import React, { useId, useState } from 'react';
import { ArrowDown, ClipboardList } from 'lucide-react';
import type { MomentAudit, Slot } from '../api/contract';
import { insights } from '../api/insights';
import { useI18n } from '../i18n';
import { useInsight, useInsightMode } from '../state/useInsight';
import { cx } from './ui';

export const DESKS = ['spotter', 'analyst', 'commentator', 'producer', 'fact_checker'] as const;
export type Desk = (typeof DESKS)[number];
export type DeskState = 'ok' | 'fallback' | 'template' | 'rejected' | 'error' | 'unknown';

export interface RundownRow {
  desk: Desk;
  /** i18n key and values for the one-line output. */
  out: { key: string; vars: Record<string, string | number> };
  /** Total milliseconds the trace logged for this desk, or null when nothing was timed. */
  ms: number | null;
  state: DeskState;
  /** The fallback reason, when there is one. */
  why: string | null;
}

/** Builds the five rundown lines from the audit only; `slot` is the card's own placement. */
export function buildRundown(audit: MomentAudit, slot: Slot | null, kindLabel: (k: string) => string): RundownRow[] {
  const steps = audit.trace ?? [];
  const renders = audit.renderings ?? [];
  const fromTrace = (desk: Desk): Pick<RundownRow, 'ms' | 'state' | 'why'> | null => {
    const mine = steps.filter((s) => s.agent === desk);
    if (!mine.length) return null;
    const ms = mine.reduce((a, s) => a + s.ms, 0);
    const pick = (st: string) => mine.find((s) => s.status === st);
    if (pick('error')) return { ms, state: 'error', why: pick('error')?.detail ?? null };
    if (pick('rejected')) return { ms, state: 'rejected', why: pick('rejected')?.detail ?? null };
    if (pick('fallback')) return { ms, state: 'fallback', why: pick('fallback')?.detail ?? null };
    return { ms, state: 'ok', why: null };
  };
  const derived = (state: DeskState, why: string | null = null) => ({ ms: null, state, why });
  const ex = audit.explanation;
  const langs = [...new Set(renders.map((r) => r.text_language ?? r.language))].map((l) => l.toUpperCase()).join(', ');
  const passed = renders.filter((r) => r.fact_check?.ok).length;
  const commentFallback = renders.find((r) => r.fallback_reason);

  const placed = slot ?? (() => {
    const d = steps.find((s) => s.agent === 'producer' && s.detail)?.detail ?? '';
    const m = /:\s*([a-z_]+)$/.exec(d);
    return (m?.[1] as Slot | undefined) ?? null;
  })();

  return [
    {
      desk: 'spotter',
      out: {
        key: 'relay.out.spotter',
        vars: { kind: kindLabel(audit.kind), events: audit.source_event_ids.length, facts: Object.keys(audit.facts).length },
      },
      ...(fromTrace('spotter') ?? derived('unknown')),
    },
    {
      desk: 'analyst',
      out: ex.tactical_tag
        ? { key: 'relay.out.analyst', vars: { tag: ex.tactical_tag, n: ex.evidence.length } }
        : { key: 'relay.out.analystNoTag', vars: { n: ex.evidence.length } },
      ...(fromTrace('analyst') ??
        (ex.fallback_reason ? derived('fallback', ex.fallback_reason) : derived(ex.produced_by === 'template' ? 'template' : 'ok'))),
    },
    {
      desk: 'commentator',
      out: { key: 'relay.out.commentator', vars: { n: renders.length, langs: langs || '-' } },
      ...(fromTrace('commentator') ??
        (commentFallback
          ? derived('fallback', commentFallback.fallback_reason)
          : renders.length
            ? derived(renders.every((r) => r.produced_by === 'template') ? 'template' : 'ok')
            : derived('unknown'))),
    },
    {
      desk: 'producer',
      out: placed ? { key: 'relay.out.producer', vars: { slot: `relay.slot.${placed}` } } : { key: 'relay.out.producerNone', vars: {} },
      ...(fromTrace('producer') ?? derived('unknown')),
    },
    {
      desk: 'fact_checker',
      out: { key: 'relay.out.checker', vars: { ok: passed, n: renders.length } },
      ...(fromTrace('fact_checker') ?? (renders.length ? derived(passed === renders.length ? 'ok' : 'rejected') : derived('unknown'))),
    },
  ];
}

const STATE_TONE: Record<DeskState, string> = {
  ok: 'border-emerald-400/60 text-emerald-300',
  template: 'border-pp-line text-pp-mute',
  fallback: 'border-pp-gold/70 text-pp-gold',
  rejected: 'border-pp-pulse/70 text-pp-pulseSoft',
  error: 'border-pp-pulse text-pp-pulseSoft',
  unknown: 'border-dashed border-pp-line text-pp-mute',
};

export const Rundown: React.FC<{ audit: MomentAudit; slot: Slot | null }> = ({ audit, slot }) => {
  const { t, num } = useI18n();
  const titleId = useId();
  const rows = buildRundown(audit, slot, (k) => t(`kind.${k}`));
  const untimed = rows.every((r) => r.ms === null);
  const outText = (r: RundownRow) => {
    const vars = { ...r.out.vars };
    if (typeof vars.slot === 'string') vars.slot = t(vars.slot);
    return t(r.out.key, vars);
  };
  return (
    <section aria-labelledby={titleId} data-testid="crew-rundown" className="mt-2 w-full border-s-4 border-pp-signal bg-pp-night">
      <h4 id={titleId} className="flex items-center gap-2 border-b border-pp-line bg-pp-deep px-3 py-1.5 font-display text-xs font-extrabold uppercase italic tracking-broadcast text-pp-signal">
        <ClipboardList className="h-3.5 w-3.5" aria-hidden />
        {t('relay.title')}
      </h4>
      <ol>
        {rows.map((r, i) => {
          const next = rows[i + 1];
          const stateText =
            r.state === 'fallback' ? t('relay.state.fallback', { why: r.why ?? '-' }) : t(`relay.state.${r.state}`);
          return (
            <li key={r.desk} data-desk={r.desk} className="border-b border-pp-line/60 last:border-b-0">
              <div className="grid grid-cols-[3rem_1fr] gap-x-2 gap-y-0.5 px-3 py-2 text-xs">
                <span className="ltr-nums row-span-3 self-start bg-pp-chalk px-1 text-center font-display text-sm font-extrabold text-pp-night">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span className="font-display text-sm font-bold uppercase tracking-broadcast text-pp-chalk">{t(`relay.desk.${r.desk}`)}</span>
                <span className="text-slate-200">
                  <bdi>{outText(r)}</bdi>
                </span>
                <span className="flex flex-wrap items-center gap-2">
                  <span className="ltr-nums text-pp-signal">
                    <span className="sr-only">{t('relay.time')}: </span>
                    {r.ms === null ? <span className="text-pp-mute">{t('relay.notTimed')}</span> : `${num(r.ms, 1)} ms`}
                  </span>
                  <span className={cx('inline-block max-w-full truncate border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider', STATE_TONE[r.state])} title={stateText}>
                    <span className="sr-only">{t('relay.state')}: </span>
                    {stateText}
                  </span>
                </span>
              </div>
              {next && (
                <p className="flex items-center gap-1 ps-[1.6rem] pb-1 text-[10px] font-bold uppercase tracking-wider text-pp-mute">
                  <ArrowDown className="h-3 w-3 text-pp-signal" aria-hidden />
                  {t('relay.handsTo', { desk: t(`relay.desk.${next.desk}`) })}
                </p>
              )}
            </li>
          );
        })}
      </ol>
      {untimed && <p className="border-t border-pp-line px-3 py-1 text-[11px] text-pp-mute">{t('relay.timingNote')}</p>}
      <p className="border-t border-pp-line bg-pp-deep px-3 py-1.5 text-[11px] font-bold text-pp-chalk" data-testid="rundown-footer">
        {t('relay.footer')}
      </p>
    </section>
  );
};

const RundownLoader: React.FC<{ momentId: string; slot: Slot | null }> = ({ momentId, slot }) => {
  const { t } = useI18n();
  const mode = useInsightMode();
  const { state } = useInsight(() => insights.audit(mode, momentId), `${mode}:${momentId}:relay`);
  if (state.status === 'loading')
    return (
      <p role="status" className="mt-2 w-full animate-pulse border border-pp-line bg-pp-deep px-3 py-2 text-xs text-pp-mute">
        {t('relay.loading')}
      </p>
    );
  if (state.status !== 'ready')
    return <p role="status" className="mt-2 w-full border border-dashed border-pp-line px-3 py-2 text-xs text-pp-mute">{t('relay.unavailable')}</p>;
  return <Rundown audit={state.data} slot={slot} />;
};

/** The button on each story card and replay, and the rundown it opens in place. */
export const CrewRelayToggle: React.FC<{ momentId: string; slot?: Slot | null }> = ({ momentId, slot = null }) => {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const id = useId();
  if (momentId.startsWith('metric:')) return null;
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={id}
        className="inline-flex min-h-[44px] items-center gap-1.5 border border-pp-line bg-pp-night px-3 font-display text-[13px] font-bold uppercase tracking-broadcast text-pp-chalk transition hover:border-pp-signal hover:text-pp-signal focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal motion-reduce:transition-none"
      >
        <ClipboardList className="h-4 w-4 text-pp-signal" aria-hidden />
        {open ? t('relay.close') : t('relay.open')}
      </button>
      <div id={id} className="basis-full">
        {open && <RundownLoader momentId={momentId} slot={slot} />}
      </div>
    </>
  );
};
