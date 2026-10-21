import React, { useEffect, useState } from 'react';
import { Bot, FileText, ShieldCheck, X } from 'lucide-react';
import { isBetterOption, isUnfoundRun, type OverlayCard, type Teams } from '../api/contract';
import { useI18n } from '../i18n';
import { playerById, shortName } from '../lib/teams';
import { Pitch2D, decimalsOf, evidenceLabel, fmtFact, fmtUnit, pct, withClock } from './Pitch2D';
import { Badge, cx } from './ui';

export interface ReplayCardProps {
  card: OverlayCard; // kind better_option or unfound_run, replay set
  teams: Teams | null;
  compact?: boolean;
  onClose?: () => void;
}

const STEP_MS = 2500;
type Step = 1 | 2 | 3;

const clockOf = (s: number) => {
  const total = Math.max(0, Math.floor(s));
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
};

export const ReplayCard: React.FC<ReplayCardProps> = ({ card, teams, compact = false, onClose }) => {
  const i18n = useI18n();
  const { t, num, dir } = i18n;
  const [step, setStep] = useState<Step>(1);
  const [cycle, setCycle] = useState(0); // restarts the timer after a click

  useEffect(() => {
    const id = setTimeout(() => setStep((s) => ((s % 3) + 1) as Step), STEP_MS);
    return () => clearTimeout(id);
  }, [step, cycle]);

  useEffect(() => {
    setStep(1);
  }, [card.card_id]);

  const pick = (s: Step) => {
    setStep(s);
    setCycle((c) => c + 1);
  };

  const r = card.replay;
  const better = isBetterOption(r) ? r : null;
  const run = isUnfoundRun(r) ? r : null;
  const name = (id: string | null | undefined) => {
    const p = playerById(teams, id);
    return p ? shortName(p.name) : '';
  };

  const steps: { title: string; text: React.ReactNode }[] = better
    ? [
        { title: t('pitch.steps.better.1.title'), text: t('pitch.steps.better.1.text', { shooter: name(better.shooter_id), xg: num(better.shot_chance_quality, Math.max(2, decimalsOf(better.shot_chance_quality))) }) },
        {
          title: t('pitch.steps.better.2.title'),
          text: t('pitch.steps.better.2.text', {
            teammate: name(better.teammate_id),
            m: num(better.nearest_marker_m, 1),
            p: pct(better.pass_success),
          }),
        },
        {
          title: t('pitch.steps.better.3.title'),
          text: t('pitch.steps.better.3.text', { x: num(better.times_better, 1), alt: num(better.alt_chance_quality, Math.max(2, decimalsOf(better.alt_chance_quality))) }),
        },
      ]
    : run
      ? [
          {
            title: t('pitch.steps.run.1.title'),
            text: withClock(t('pitch.steps.run.1.text', { runner: name(run.runner_id), clock: '\u0000' }), run.pass_on_clock),
          },
          { title: t('pitch.steps.run.2.title'), text: t('pitch.steps.run.2.text', { carrier: name(run.carrier_id), m: num(run.clear_of_line_m, 1) }) },
          {
            title: t('pitch.steps.run.3.title'),
            text: t(run.one_on_one ? 'pitch.steps.run.3.oneOnOne' : 'pitch.steps.run.3.text', { xg: num(run.projected_chance_quality, Math.max(2, decimalsOf(run.projected_chance_quality))) }),
          },
        ]
      : [];

  const produced =
    card.produced_by === 'ai' ? (
      <Badge tone="signal" title={t('crew.ai')}>
        <Bot className="h-3 w-3" aria-hidden />
        {t('produced.ai')}
      </Badge>
    ) : (
      <Badge tone="mute" title={t('crew.templateHint')}>
        <FileText className="h-3 w-3" aria-hidden />
        {t('produced.template')}
      </Badge>
    );

  const closeBtn = onClose && (
    <button
      type="button"
      onClick={onClose}
      aria-label={t('common.close')}
      className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-pp-line text-pp-mute transition hover:border-pp-pulse hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
    >
      <X className="h-4 w-4" />
    </button>
  );

  const header = (
    <header className="flex items-start gap-2">
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
        <Badge tone="pulse" className="uppercase tracking-wider">
          {t(`kind.${card.kind}`)}
        </Badge>
        <span className="ltr-nums text-xs font-semibold text-pp-mute">{clockOf(card.show_at_s)}</span>
        {produced}
      </div>
      {closeBtn}
    </header>
  );

  const pitch = <Pitch2D teams={teams} event={null} replay={r} replayStep={step} />;

  if (compact) {
    const verdict = steps[2];
    return (
      <section dir={dir} className="animate-slide-up overflow-hidden rounded-2xl border border-pp-line/80 bg-pp-panel/95 p-2.5 shadow-2xl shadow-black/50 sm:p-3">
        {header}
        <h2 className="my-2 font-display text-base font-bold leading-tight text-white sm:text-lg">{card.headline}</h2>
        {pitch}
        {verdict && (
          <p className="mt-2 text-xs font-semibold text-pp-signal sm:text-sm" data-testid="replay-compact-verdict">
            {verdict.text}
          </p>
        )}
      </section>
    );
  }

  return (
    <section dir={dir} className="animate-slide-up rounded-2xl border border-pp-line/80 bg-pp-panel/95 p-3 shadow-2xl shadow-black/50 sm:p-4" aria-labelledby={`replay-${card.card_id}`}>
      <style>{`@keyframes ppProgress { from { transform: scaleX(0); } to { transform: scaleX(1); } }`}</style>
      {header}
      <h2 id={`replay-${card.card_id}`} className="mb-3 mt-2 font-display text-xl font-bold leading-tight text-white sm:text-2xl">
        {card.headline}
      </h2>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
        <div className="md:col-span-3">{pitch}</div>

        <div className="md:col-span-2">
          <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-pp-mute">{t('pitch.story')}</h3>
          <ol className="flex flex-col gap-2">
            {steps.map((s, i) => {
              const n = (i + 1) as Step;
              const active = n === step;
              return (
                <li key={n}>
                  <button
                    type="button"
                    onClick={() => pick(n)}
                    aria-current={active ? 'step' : undefined}
                    aria-label={`${t('pitch.step', { n })}: ${s.title}`}
                    className={cx(
                      'relative w-full overflow-hidden rounded-xl border p-2.5 text-start transition focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal',
                      active ? 'border-pp-signal/70 bg-pp-raised' : 'border-pp-line bg-pp-deep/60 opacity-75 hover:opacity-100',
                    )}
                  >
                    <span className="flex items-start gap-2.5">
                      <span
                        className={cx(
                          'ltr-nums mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold',
                          active ? 'bg-pp-signal text-pp-night' : 'bg-pp-line text-slate-200',
                        )}
                      >
                        {n}
                      </span>
                      <span className="min-w-0">
                        <span className="block font-display text-sm font-semibold uppercase tracking-wide text-white">{s.title}</span>
                        <span className="mt-0.5 block text-xs leading-snug text-slate-300 sm:text-sm">{s.text}</span>
                      </span>
                    </span>
                    {active && (
                      <span
                        key={`${step}-${cycle}`}
                        aria-hidden
                        className="absolute inset-x-0 bottom-0 h-0.5 bg-pp-signal"
                        style={{ transformOrigin: dir === 'rtl' ? 'right' : 'left', animation: `ppProgress ${STEP_MS}ms linear both` }}
                      />
                    )}
                  </button>
                </li>
              );
            })}
          </ol>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="space-y-3">
          {card.body && <p className="text-sm leading-relaxed text-slate-200">{card.body}</p>}
          {card.why && (
            <div className="rounded-xl border border-pp-gold/30 bg-pp-gold/5 p-3">
              <h3 className="mb-1 text-[11px] font-bold uppercase tracking-wider text-pp-gold">{t('pitch.why')}</h3>
              <p className="text-sm leading-relaxed text-slate-200">{card.why}</p>
            </div>
          )}
          {card.fallback_reason && (
            <p className="text-xs text-pp-mute" data-testid="replay-fallback">
              {t('pitch.fallback', { reason: card.fallback_reason })}
            </p>
          )}
        </div>

        {card.evidence.length > 0 && (
          <div className="rounded-xl border border-pp-line bg-pp-deep/60 p-3">
            <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-pp-mute">{t('evidence.title')}</h3>
            <dl className="divide-y divide-pp-line/60">
              {card.evidence.map((ev, i) => (
                <div key={`${ev.label}-${i}`} className="flex items-baseline justify-between gap-3 py-1.5">
                  <dt className="min-w-0">
                    <span className="block text-xs text-slate-300">{evidenceLabel(ev.label, t)}</span>
                    {ev.source_event_id && (
                      <span className="block truncate text-[10px] text-pp-mute">{t('evidence.source', { id: ev.source_event_id })}</span>
                    )}
                  </dt>
                  <dd className="ltr-nums shrink-0 text-sm font-bold text-white" data-testid="evidence-value">
                    {fmtFact(ev.value, i18n)}
                    {ev.unit ? <span className="ms-1 text-xs font-medium text-pp-mute">{fmtUnit(ev.unit, t)}</span> : null}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 flex items-center gap-1.5 text-[11px] text-emerald-300/90">
              <ShieldCheck className="h-3.5 w-3.5 shrink-0" aria-hidden />
              {t('pitch.factChecked')}
            </p>
          </div>
        )}
      </div>
    </section>
  );
};
