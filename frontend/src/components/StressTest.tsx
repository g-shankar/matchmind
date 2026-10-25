// Stress test the crew: one small button that opens a panel. The viewer picks a played moment and
// one fault; the server replays that moment in a throwaway sandbox crew (POST
// /api/match/stress-test) and the steps play out like the crew rundown (CrewRelay.tsx): what broke
// or was injected, the fact-checker's verdict, the template taking over and the safe card.
// The offline demo plays recorded results (public/demo/demo-stress.json). Self-contained on purpose.
import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { ArrowDown, FlaskConical, ShieldCheck } from 'lucide-react';
import type { Bookmark, StressFault, StressResult, StressStep } from '../api/contract';
import { STRESS_FAULTS } from '../api/contract';
import { loadDemoStress, stressTest, type InsightResult } from '../api/insights';
import { useI18n } from '../i18n';
import { useInsightMode } from '../state/useInsight';
import { Modal } from './Modal';
import { compareMoments } from './MomentsList';
import { cx } from './ui';

export const STEP_MS = 450;

const TONE: Record<string, string> = {
  ok: 'border-emerald-400/60 text-emerald-300',
  took_over: 'border-pp-gold/70 text-pp-gold',
  fallback: 'border-pp-gold/70 text-pp-gold',
  skipped: 'border-dashed border-pp-line text-pp-mute',
  rejected: 'border-pp-pulse/70 text-pp-pulseSoft',
  injected: 'border-pp-pulse text-pp-pulseSoft',
  down: 'border-pp-pulse text-pp-pulseSoft',
  malformed: 'border-pp-pulse text-pp-pulseSoft',
};

const REASONS = new Set(['error', 'schema', 'timeout', 'fact_check', 'budget', 'circuit_open']);

/** The translated one-line outcome of a step. */
export function stepText(t: (k: string, v?: Record<string, string | number>) => string, s: StressStep): string {
  const reason = s.detail && REASONS.has(s.detail) ? t(`stress.reason.${s.detail}`) : t('stress.reason.error');
  switch (s.code) {
    case 'wrong_number':
      return t('stress.step.injected', { n: s.detail ?? '?' });
    case 'number_not_in_facts':
      return t('stress.step.rejected', { n: s.detail ?? '?' });
    case 'template':
    case 'template_explanation':
      return t(`stress.step.${s.code}`, { why: reason });
    case 'nothing_to_check':
      return t('stress.step.nothing_to_check', { why: reason });
    default:
      return t(`stress.step.${s.code}`);
  }
}

function reducedMotion(): boolean {
  try {
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
  } catch {
    return false;
  }
}

export const StressSteps: React.FC<{ result: StressResult }> = ({ result }) => {
  const { t } = useI18n();
  const [shown, setShown] = useState(() => (reducedMotion() ? result.steps.length : 1));
  useEffect(() => {
    if (shown >= result.steps.length) return;
    const id = window.setTimeout(() => setShown((n) => n + 1), STEP_MS);
    return () => window.clearTimeout(id);
  }, [shown, result.steps.length]);
  const done = shown >= result.steps.length;
  const card = result.card;
  return (
    <section data-testid="stress-steps" className="w-full border-s-4 border-pp-signal bg-pp-night" aria-live="polite">
      <ol>
        {result.steps.slice(0, shown).map((s, i) => (
          <li key={i} data-agent={s.agent} className="border-b border-pp-line/60 last:border-b-0 motion-safe:animate-[fadeIn_.3s_ease-out]">
            <div className="grid grid-cols-[3rem_1fr] gap-x-2 gap-y-0.5 px-3 py-2 text-xs">
              <span className="ltr-nums row-span-3 self-start bg-pp-chalk px-1 text-center font-display text-sm font-extrabold text-pp-night">
                {String(i + 1).padStart(2, '0')}
              </span>
              <span className="font-display text-sm font-bold uppercase tracking-broadcast text-pp-chalk">{t(`stress.agent.${s.agent}`)}</span>
              <span className="text-slate-200">
                <bdi>{stepText(t, s)}</bdi>
              </span>
              <span>
                <span className={cx('inline-block border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider', TONE[s.status] ?? TONE.ok)}>
                  <span className="sr-only">{t('relay.state')}: </span>
                  {t(`stress.status.${s.status}`)}
                </span>
              </span>
              {s.reasons && s.reasons.length > 0 && (
                <span className="col-start-2 text-[11px] text-pp-mute">
                  {t('stress.checkerSaid')} <bdi dir="ltr" className="ltr-nums">{s.reasons.join('; ')}</bdi>
                </span>
              )}
            </div>
            {i < result.steps.length - 1 && i < shown - 1 && (
              <p className="flex items-center gap-1 ps-[1.6rem] pb-1 text-[10px] font-bold uppercase tracking-wider text-pp-mute">
                <ArrowDown className="h-3 w-3 text-pp-signal" aria-hidden />
                {t('relay.handsTo', { desk: t(`stress.agent.${result.steps[i + 1].agent}`) })}
              </p>
            )}
          </li>
        ))}
      </ol>
      {done && card && (
        <div data-testid="stress-card" className="border-t-2 border-pp-signal bg-pp-deep px-3 py-2" dir={card.rtl ? 'rtl' : 'ltr'} lang={card.language}>
          <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-broadcast text-emerald-300">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
            {t(result.safe ? 'stress.safeCard' : 'stress.noSafeCard')}
          </p>
          <p className="mt-1 font-display text-base font-extrabold uppercase italic text-pp-chalk">{card.headline}</p>
          <p className="text-sm text-slate-200">{card.body}</p>
        </div>
      )}
      {done && !card && <p className="border-t border-pp-line px-3 py-2 text-xs text-pp-mute">{t('stress.noSafeCard')}</p>}
    </section>
  );
};

type RunState = InsightResult<StressResult> | { status: 'idle' } | { status: 'loading' };

/** The entry point: one small button, and the panel it opens. Hidden in catch-up mode.
 * `now` is the match clock: live, the server only tests moments already played, so later ones are left out. */
export const StressTestButton: React.FC<{
  bookmarks: Bookmark[];
  spoilers: boolean;
  now?: { clock_s: number; period?: number };
}> = ({ bookmarks, spoilers, now }) => {
  const { t, lang } = useI18n();
  const mode = useInsightMode();
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [recorded, setRecorded] = useState<Set<string> | null>(null);
  const [momentId, setMomentId] = useState('');
  const [fault, setFault] = useState<StressFault>('wrong_number');
  const [run, setRun] = useState<RunState>({ status: 'idle' });
  const [runKey, setRunKey] = useState(0);
  const live = useRef(true);
  useEffect(() => () => void (live.current = false), []);

  useEffect(() => {
    if (!open || mode !== 'demo' || recorded) return;
    loadDemoStress()
      .then((b) => live.current && setRecorded(new Set(Object.keys(b.results))))
      .catch(() => live.current && setRecorded(new Set()));
  }, [open, mode, recorded]);

  const options = useMemo(() => {
    const list = bookmarks.filter(
      (b) =>
        !b.moment_id.startsWith('metric:') &&
        (mode === 'demo' ? recorded?.has(b.moment_id) : !now || compareMoments(b, now) <= 0),
    );
    return list.slice(-40).reverse();
  }, [bookmarks, mode, recorded, now?.clock_s, now?.period]);
  const picked = options.some((o) => o.moment_id === momentId) ? momentId : (options[0]?.moment_id ?? '');

  if (!spoilers) return null;

  const go = async () => {
    if (!picked || run.status === 'loading') return;
    setRun({ status: 'loading' });
    const r = await stressTest(mode, picked, fault, lang);
    if (!live.current) return;
    setRun(r);
    setRunKey((k) => k + 1);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex min-h-[44px] items-center gap-1.5 border border-pp-line bg-pp-night px-3 font-display text-[13px] font-bold uppercase tracking-broadcast text-pp-chalk transition hover:border-pp-signal hover:text-pp-signal focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal motion-reduce:transition-none"
      >
        <FlaskConical className="h-4 w-4 text-pp-signal" aria-hidden />
        {t('stress.open')}
      </button>
      <Modal open={open} onClose={() => setOpen(false)} labelledBy={titleId} name="stress" className="max-w-lg">
        <div className="flex max-h-[85vh] flex-col gap-3 overflow-y-auto p-4">
          <h2 id={titleId} className="flex items-center gap-2 font-display text-lg font-extrabold uppercase italic tracking-broadcast text-pp-signal">
            <FlaskConical className="h-5 w-5" aria-hidden />
            {t('stress.title')}
          </h2>
          <p className="text-sm text-slate-300">{t('stress.intro')}</p>
          {mode === 'demo' && <p className="text-xs text-pp-gold">{t('stress.demoNote')}</p>}
          {options.length === 0 ? (
            <p className="text-sm text-pp-mute">{mode === 'demo' && !recorded ? t('relay.loading') : t('stress.noMoments')}</p>
          ) : (
            <>
              <label className="flex flex-col gap-1 text-xs font-bold uppercase tracking-broadcast text-pp-mute">
                {t('stress.moment')}
                <select
                  data-autofocus
                  value={picked}
                  onChange={(e) => setMomentId(e.target.value)}
                  className="min-h-[44px] border border-pp-line bg-pp-night px-2 text-sm normal-case tracking-normal text-pp-chalk"
                >
                  {options.map((b) => (
                    <option key={b.moment_id} value={b.moment_id}>
                      {`${b.match_clock} · ${t(`kind.${b.kind}`)}`}
                    </option>
                  ))}
                </select>
              </label>
              <fieldset>
                <legend className="mb-1 text-xs font-bold uppercase tracking-broadcast text-pp-mute">{t('stress.fault')}</legend>
                <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                  {STRESS_FAULTS.map((f) => (
                    <label
                      key={f}
                      className={cx(
                        'flex min-h-[44px] cursor-pointer items-center gap-2 border px-2 text-sm',
                        fault === f ? 'border-pp-signal bg-pp-deep text-pp-chalk' : 'border-pp-line text-slate-300',
                      )}
                    >
                      <input type="radio" name={`${titleId}-fault`} value={f} checked={fault === f} onChange={() => setFault(f)} className="accent-pp-signal" />
                      {t(`stress.fault.${f}`)}
                    </label>
                  ))}
                </div>
              </fieldset>
              <button
                type="button"
                onClick={go}
                aria-busy={run.status === 'loading'}
                className="inline-flex min-h-[44px] items-center justify-center gap-2 bg-pp-signal px-4 font-display text-sm font-extrabold uppercase tracking-broadcast text-pp-night disabled:opacity-60"
                disabled={run.status === 'loading'}
              >
                {run.status === 'loading' ? t('stress.running') : t('stress.run')}
              </button>
            </>
          )}
          {run.status === 'ready' && <StressSteps key={runKey} result={run.data} />}
          {(run.status === 'missing' || run.status === 'busy' || run.status === 'error' || run.status === 'needs_server') && (
            <p role="status" className="border border-dashed border-pp-line px-3 py-2 text-xs text-pp-mute">
              {t(`stress.problem.${run.status}`)}
            </p>
          )}
          <p className="border-t border-pp-line pt-2 text-[11px] text-pp-mute">{t('stress.sandboxNote')}</p>
          <button type="button" onClick={() => setOpen(false)} className="min-h-[44px] self-end border border-pp-line px-3 font-display text-sm font-bold uppercase text-pp-chalk hover:border-pp-signal">
            {t('stress.close')}
          </button>
        </div>
      </Modal>
    </>
  );
};
