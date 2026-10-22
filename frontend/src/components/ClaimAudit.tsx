// "Show your working": the claim audit for one moment (GET /api/match/moment/{id}/audit,
// docs/TRUST.md). Every sentence is shown with what the machine checked about it,
// the fact each number binds to, its source events, the cross-language parity
// result and the crew's trace. Wording is never claimed as verified.
import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowLeft, Gavel, ListChecks, ShieldCheck, X } from 'lucide-react';
import type { Claim, ClaimField, FactValue, MomentAudit, MomentKind, PersonaType, RenderingAudit } from '../api/contract';
import { insights } from '../api/insights';
import { useI18n } from '../i18n';
import { defaultLanguages } from '../lib/languages';
import { useInsight, useInsightMode } from '../state/useInsight';
import { InsightGate, SubHead } from './InsightStatus';
import { Badge, Segmented, cx } from './ui';

const RTL = new Set(['ar']);
const TRACE_PREVIEW = 8;

/** A claim that failed a check (not one with nothing to check). Mirrors crew/claims.py `_failed`. */
export const claimFailed = (c: Claim) => c.check === 'unverified_text' && !c.reason.startsWith('no number or squad name');

type Segment = { text: string; binding?: NonNullable<Claim['bindings']>[number] };

/** Splits a sentence around its bindings, in order, so each one can be marked inline. */
export function claimSegments(claim: Claim): Segment[] {
  const out: Segment[] = [];
  let cursor = 0;
  const s = claim.sentence;
  for (const b of claim.bindings ?? []) {
    if (!b.text) continue;
    const at = s.indexOf(b.text, cursor);
    if (at < 0) continue;
    if (at > cursor) out.push({ text: s.slice(cursor, at) });
    out.push({ text: b.text, binding: b });
    cursor = at + b.text.length;
  }
  if (cursor < s.length) out.push({ text: s.slice(cursor) });
  return out;
}

// ------------------------------------------------------------------ the button

export const ShowWorkingButton: React.FC<{
  momentId: string;
  persona?: PersonaType;
  language?: string;
  className?: string;
}> = ({ momentId, persona, language, className }) => {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button
        ref={ref}
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        className={cx(
          'inline-flex min-h-[44px] items-center gap-1.5 border border-pp-line bg-pp-night px-3 font-display text-[13px] font-bold uppercase tracking-broadcast text-pp-chalk transition hover:border-pp-signal hover:text-pp-signal focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal',
          className,
        )}
      >
        <ListChecks className="h-4 w-4 text-pp-signal" aria-hidden />
        {t('audit.button')}
      </button>
      {open && (
        <AuditDrawer
          momentId={momentId}
          persona={persona}
          language={language}
          onClose={() => {
            setOpen(false);
            ref.current?.focus();
          }}
        />
      )}
    </>
  );
};

// ------------------------------------------------------------------ the drawer

export const AuditDrawer: React.FC<{
  momentId: string;
  persona?: PersonaType;
  language?: string;
  onClose: () => void;
}> = ({ momentId, persona, language, onClose }) => {
  const { t, dir } = useI18n();
  const mode = useInsightMode();
  const titleId = useId();
  const [stack, setStack] = useState<string[]>([momentId]);
  // Always the working for the moment that was asked for, even if this drawer is reused.
  useEffect(() => setStack([momentId]), [momentId]);
  const current = stack[stack.length - 1];
  const { state, reload } = useInsight(() => insights.audit(mode, current), `${mode}:${current}`);
  const panel = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== 'Tab' || !panel.current) return;
    const items = panel.current.querySelectorAll<HTMLElement>('button, a[href], select, [tabindex]:not([tabindex="-1"])');
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  const open = (id: string) => setStack((s) => [...s, id]);
  const back = () => setStack((s) => (s.length > 1 ? s.slice(0, -1) : s));

  const drawer = (
    <div
      dir={dir}
      className="fixed inset-0 z-[60] flex justify-end bg-black/60"
      // The drawer is portalled, but React events still bubble to the card that opened it
      // (e.g. the replay modal's backdrop): stop them here.
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
      onKeyDown={onKeyDown}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
        className="flex h-full w-full max-w-2xl animate-fade-in flex-col border-s-4 border-pp-signal bg-pp-panel text-slate-100 shadow-2xl"
      >
        <header className="flex items-stretch justify-between gap-2 border-b border-pp-line">
          <div className="flex min-w-0 items-stretch">
            {stack.length > 1 && (
              <button
                type="button"
                onClick={back}
                aria-label={t('audit.back')}
                title={t('audit.back')}
                className="flex w-11 shrink-0 items-center justify-center border-e border-pp-line text-pp-mute hover:text-pp-chalk focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
              >
                <ArrowLeft className="h-4 w-4 rtl:rotate-180" aria-hidden />
              </button>
            )}
            <h2 id={titleId} className="pp-slant flex items-center gap-2 bg-pp-chalk py-2 pe-7 ps-3 font-display text-base font-extrabold uppercase italic tracking-broadcast text-pp-night">
              <ShieldCheck className="h-4 w-4 text-pp-pulse" aria-hidden />
              {t('audit.title')}
            </h2>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label={t('common.close')}
            className="flex w-12 shrink-0 items-center justify-center text-pp-mute hover:text-pp-chalk focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto overscroll-contain p-4">
          <p className="mb-3 text-xs leading-relaxed text-pp-mute">{t('audit.intro')}</p>
          <Legend />
          <div aria-live="polite" aria-busy={state.status === 'loading'}>
            {state.status === 'ready' ? (
              <AuditBody key={current} audit={state.data} demo={state.source === 'demo'} persona={persona} language={language} onOpenMoment={open} />
            ) : (
              <div className="mt-4">
                <InsightGate state={state} onRetry={reload} lines={8} missingKey="audit.missing" />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
  return createPortal(drawer, document.body);
};

// ------------------------------------------------------------------ legend

export const Legend: React.FC = () => {
  const { t } = useI18n();
  return (
    <div className="mb-4 border border-pp-line bg-pp-deep/70 p-3">
      <span className="mb-2 block text-[11px] font-bold uppercase tracking-broadcast text-pp-mute">{t('audit.legend')}</span>
      <ul className="grid gap-2 text-xs sm:grid-cols-2">
        <li className="flex items-center gap-2">
          <Mark kind="number">0.24</Mark>
          <span>{t('audit.legend.number')}</span>
        </li>
        <li className="flex items-center gap-2">
          <Mark kind="name">Kerrigan</Mark>
          <span>{t('audit.legend.name')}</span>
        </li>
        <li className="flex items-center gap-2">
          <Mark kind="unbound">7</Mark>
          <span>{t('audit.legend.unbound')}</span>
        </li>
        <li className="flex items-center gap-2">
          <span className="border-b border-dashed border-pp-mute px-1 text-pp-mute">{t('audit.legend.sample')}</span>
          <span>{t('audit.legend.unverified')}</span>
        </li>
      </ul>
    </div>
  );
};

const Mark: React.FC<{ kind: 'number' | 'name' | 'unbound'; title?: string; children: React.ReactNode }> = ({ kind, title, children }) => (
  <mark
    title={title}
    data-mark={kind}
    className={cx(
      'ltr-nums px-0.5 font-bold',
      kind === 'number' && 'bg-pp-signal text-pp-night',
      kind === 'name' && 'bg-transparent text-pp-chalk outline outline-1 outline-pp-chalk/70',
      kind === 'unbound' && 'bg-pp-pulse text-white line-through',
    )}
  >
    {children}
  </mark>
);

// ------------------------------------------------------------------ body

const AuditBody: React.FC<{
  audit: MomentAudit;
  demo: boolean;
  persona?: PersonaType;
  language?: string;
  onOpenMoment: (id: string) => void;
}> = ({ audit, demo, persona, language, onOpenMoment }) => {
  const { t } = useI18n();
  const personas = useMemo(() => [...new Set(audit.renderings.map((r) => r.persona))], [audit.renderings]);
  const start =
    audit.renderings.find((r) => r.persona === persona && r.language === language && r.source === 'live') ??
    audit.renderings.find((r) => r.persona === persona && r.language === language) ??
    audit.renderings.find((r) => r.persona === persona) ??
    audit.renderings[0];
  const [pick, setPick] = useState<{ persona: PersonaType; language: string } | null>(start ? { persona: start.persona, language: start.language } : null);
  const languages = useMemo(
    () => [...new Set(audit.renderings.filter((r) => r.persona === pick?.persona).map((r) => r.language))],
    [audit.renderings, pick?.persona],
  );
  const rendering =
    audit.renderings.find((r) => r.persona === pick?.persona && r.language === pick?.language && r.source === 'live') ??
    audit.renderings.find((r) => r.persona === pick?.persona && r.language === pick?.language) ??
    null;
  const labels = useMemo(() => {
    const m: Record<string, string> = {};
    for (const e of audit.explanation.evidence) if (e.label_key) m[e.label_key] = e.label;
    return m;
  }, [audit.explanation.evidence]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="gold">{t(`kind.${audit.kind as MomentKind}`)}</Badge>
        <span className="ltr-nums font-display text-sm font-bold text-pp-signal">{audit.match_clock}</span>
        <code dir="ltr" className="break-all text-[11px] text-pp-mute">
          {audit.moment_id}
        </code>
      </div>

      {demo && <p className="border-s-2 border-pp-gold bg-pp-gold/10 px-3 py-2 text-xs text-pp-gold">{t('audit.demoNote')}</p>}

      <Corrections audit={audit} onOpenMoment={onOpenMoment} />

      <section aria-labelledby="audit-sentences">
        <SubHead id="audit-sentences">{t('audit.sentences')}</SubHead>
        {personas.length > 0 && pick ? (
          <div className="mb-3 flex flex-wrap gap-2">
            <Segmented
              label={t('audit.pickPersona')}
              value={pick.persona}
              onChange={(p) =>
                setPick({ persona: p, language: audit.renderings.some((r) => r.persona === p && r.language === pick.language) ? pick.language : audit.renderings.find((r) => r.persona === p)!.language })
              }
              options={personas.map((p) => ({ value: p, label: t(`persona.${p}`) }))}
              className="flex-wrap [&>button]:min-h-[44px]"
            />
            <Segmented
              label={t('audit.pickLanguage')}
              value={pick.language}
              onChange={(l) => setPick({ persona: pick.persona, language: l })}
              options={languages.map((l) => ({ value: l, label: <span lang={l}>{l.toUpperCase()}</span>, title: defaultLanguages().find((x) => x.code === l)?.name ?? l }))}
              className="flex-wrap [&>button]:min-h-[44px]"
            />
          </div>
        ) : (
          <p className="text-sm text-pp-mute">{t('audit.noRenderings')}</p>
        )}
        {rendering && <RenderingView rendering={rendering} labels={labels} />}
      </section>

      <Facts audit={audit} labels={labels} />
      <Parity audit={audit} />
      <Trace audit={audit} demo={demo} />

      <section aria-labelledby="audit-not-checked">
        <SubHead id="audit-not-checked">{t('audit.notChecked')}</SubHead>
        <ul lang="en" dir="ltr" className="list-disc space-y-1 ps-5 text-start text-xs text-slate-300">
          {audit.not_checked.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
        <p className="mt-1 text-[11px] text-pp-mute">{t('audit.serverEnglish')}</p>
      </section>
    </div>
  );
};

const FIELD_ORDER: ClaimField[] = ['title', 'headline', 'body', 'why', 'paragraph', 'key_moment'];

const RenderingView: React.FC<{ rendering: RenderingAudit; labels: Record<string, string> }> = ({ rendering, labels }) => {
  const { t } = useI18n();
  const lang = rendering.text_language ?? rendering.language;
  const counts = { verified_numeric: 0, verified_name: 0, unverified_text: 0 } as Record<Claim['check'], number>;
  for (const c of rendering.claims) counts[c.check] += 1;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {rendering.source === 'live' && <Badge tone="pulse">{t('audit.source.live')}</Badge>}
        <Badge tone={rendering.produced_by === 'ai' ? 'signal' : 'mute'}>{t(`produced.${rendering.produced_by}`)}</Badge>
        {rendering.translated_by && <Badge tone="mute">{t('world.translated')}</Badge>}
        <Badge tone={rendering.fact_check.ok ? 'signal' : 'pulse'}>{t(rendering.fact_check.ok ? 'audit.factCheck.ok' : 'audit.factCheck.fail')}</Badge>
        <span className="ltr-nums text-pp-mute">
          {t('audit.counts', { n: counts.verified_numeric, m: counts.verified_name, u: counts.unverified_text })}
        </span>
      </div>
      {!rendering.fact_check.ok && (
        <ul lang="en" dir="ltr" className="list-disc ps-5 text-start text-xs text-pp-pulseSoft">
          {rendering.fact_check.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      <ol className="space-y-2">
        {[...rendering.claims]
          .sort((a, b) => FIELD_ORDER.indexOf(a.field) - FIELD_ORDER.indexOf(b.field))
          .map((c, i) => (
            <ClaimRow key={`${c.field}-${i}`} claim={c} lang={lang} labels={labels} />
          ))}
      </ol>
    </div>
  );
};

export const ClaimRow: React.FC<{ claim: Claim; lang: string; labels: Record<string, string> }> = ({ claim, lang, labels }) => {
  const { t, num } = useI18n();
  const failed = claimFailed(claim);
  const tone = claim.check === 'verified_numeric' ? 'border-pp-signal' : claim.check === 'verified_name' ? 'border-pp-chalk/70' : failed ? 'border-pp-pulse' : 'border-pp-line';
  const checkKey = failed ? 'audit.check.failed' : `audit.check.${claim.check}`;
  return (
    <li className={cx('border border-s-4 border-pp-line/70 bg-pp-deep/70 p-3', tone)}>
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-bold uppercase tracking-broadcast text-pp-mute">{t(`audit.field.${claim.field}`)}</span>
        <Badge tone={claim.check === 'verified_numeric' ? 'signal' : failed ? 'pulse' : 'mute'} className={claim.check === 'verified_name' ? 'text-pp-chalk' : undefined}>
          {t(checkKey)}
        </Badge>
      </div>
      <p
        lang={lang}
        dir={RTL.has(lang) ? 'rtl' : 'ltr'}
        className={cx('text-sm leading-relaxed text-white', claim.check === 'unverified_text' && 'underline-offset-4 [&>span]:underline [&>span]:decoration-pp-mute [&>span]:decoration-dashed')}
      >
        {claimSegments(claim).map((seg, i) =>
          seg.binding ? (
            <Mark
              key={i}
              kind={seg.binding.kind === 'number' ? (seg.binding.fact_key ? 'number' : 'unbound') : 'name'}
              title={seg.binding.fact_key ? `${seg.binding.fact_key} = ${String(seg.binding.value)}` : t('audit.legend.unbound')}
            >
              {seg.text}
            </Mark>
          ) : (
            <span key={i}>{seg.text}</span>
          ),
        )}
      </p>
      {(claim.bindings ?? []).length > 0 && (
        <dl className="mt-2 grid gap-x-3 gap-y-1 text-[11px] sm:grid-cols-[auto_1fr]">
          {(claim.bindings ?? []).map((b, i) => (
            <React.Fragment key={`${b.text}-${i}`}>
              <dt className="ltr-nums font-bold text-pp-chalk" lang={lang}>
                {b.text}
              </dt>
              <dd className="text-pp-mute">
                {b.fact_key ? (
                  <>
                    <span aria-hidden>→ </span>
                    <code dir="ltr" className="text-pp-signal">
                      {b.fact_key}
                    </code>
                    {labels[b.fact_key] ? <span> ({labels[b.fact_key]})</span> : null}
                    {' = '}
                    <span className="ltr-nums text-pp-chalk">{formatValue(b.value, num, t)}</span>
                    {b.unit ? <span className="ltr-nums"> {b.unit}</span> : null}
                    {b.entity_id ? (
                      <span>
                        {' · '}
                        {t('audit.entity', { id: b.entity_id })}
                      </span>
                    ) : null}
                  </>
                ) : (
                  <span className="text-pp-pulseSoft">{t('audit.unboundNumber')}</span>
                )}
              </dd>
            </React.Fragment>
          ))}
        </dl>
      )}
      {claim.source_event_ids.length > 0 && (
        <p className="mt-2 flex flex-wrap items-center gap-1 text-[11px] text-pp-mute">
          <span>{t('audit.sources')}</span>
          {claim.source_event_ids.map((id) => (
            <code key={id} dir="ltr" className="border border-pp-line bg-pp-night px-1 text-pp-chalk">
              {id}
            </code>
          ))}
        </p>
      )}
      <p lang="en" dir="ltr" className="mt-1 text-start text-[11px] italic text-pp-mute">
        {claim.reason}
      </p>
    </li>
  );
};

/** A fact exactly as in the payload (up to three decimals), like the evidence table. */
export function formatFact(value: FactValue, num: (v: number, d?: number) => string, t: (k: string) => string) {
  if (typeof value === 'boolean') return t(value ? 'studio.feed.yes' : 'studio.feed.no');
  if (typeof value === 'number') return num(value, Math.min(3, String(value).split('.')[1]?.length ?? 0));
  return value;
}

const formatValue = (v: FactValue | null, num: (v: number, d?: number) => string, t: (k: string) => string) =>
  v === null ? '' : formatFact(v, num, t);

const Facts: React.FC<{ audit: MomentAudit; labels: Record<string, string> }> = ({ audit, labels }) => {
  const { t, num } = useI18n();
  const entries = Object.entries(audit.facts);
  return (
    <section aria-labelledby="audit-facts">
      <SubHead id="audit-facts">{t('audit.facts')}</SubHead>
      <p className="mb-2 text-xs text-pp-mute">{t('audit.factsHint')}</p>
      <dl className="grid grid-cols-1 divide-y divide-pp-line/60 border border-pp-line/70 bg-pp-deep/70 text-xs sm:grid-cols-2 sm:divide-y-0">
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-baseline justify-between gap-3 px-3 py-1.5 sm:border-b sm:border-pp-line/40">
            <dt className="min-w-0 text-pp-mute">
              <code dir="ltr" className="break-all">
                {k}
              </code>
              {labels[k] && <span className="block text-[10px]">{labels[k]}</span>}
            </dt>
            <dd className="ltr-nums shrink-0 font-bold text-white">{formatFact(v, num, t)}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 flex flex-wrap items-center gap-1 text-[11px] text-pp-mute">
        <span>{t('audit.sourceEvents')}</span>
        {audit.source_event_ids.map((id) => (
          <code key={id} dir="ltr" className="border border-pp-line bg-pp-night px-1 text-pp-chalk">
            {id}
          </code>
        ))}
      </p>
    </section>
  );
};

const Parity: React.FC<{ audit: MomentAudit }> = ({ audit }) => {
  const { t } = useI18n();
  const p = audit.parity;
  const rows = useMemo(() => {
    const by = new Map<string, Map<string, string[]>>();
    for (const [label, keys] of Object.entries(p.stated)) {
      const [who, rest] = label.split('/');
      const lang = (rest ?? '').split(' ')[0];
      if (!by.has(who)) by.set(who, new Map());
      by.get(who)!.set(lang + (rest?.includes('(live)') ? '*' : ''), keys);
    }
    return by;
  }, [p.stated]);
  const langs = useMemo(() => [...new Set([...rows.values()].flatMap((m) => [...m.keys()]))], [rows]);
  return (
    <section aria-labelledby="audit-parity">
      <SubHead id="audit-parity">{t('audit.parity')}</SubHead>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
        <Badge tone={p.ok ? 'signal' : 'pulse'}>{t(p.ok ? 'audit.parity.ok' : 'audit.parity.fail')}</Badge>
        <span className="ltr-nums text-pp-mute">{t('audit.parity.counts', { n: p.renderings, w: p.withheld })}</span>
      </div>
      <p className="mb-2 text-xs text-pp-mute">{t('audit.parity.hint')}</p>
      {p.key_facts.length > 0 && (
        <p className="mb-2 flex flex-wrap items-center gap-1 text-[11px] text-pp-mute">
          <span>{t('audit.parity.keyFacts')}</span>
          {p.key_facts.map((k) => (
            <code key={k} dir="ltr" className="border border-pp-signal/60 px-1 text-pp-signal">
              {k}
            </code>
          ))}
        </p>
      )}
      {rows.size > 0 && (
        <div className="relative overflow-x-auto">
          <table className="w-full border-collapse text-[11px]">
            <caption className="sr-only">{t('audit.parity.table')}</caption>
            <thead>
              <tr>
                <th scope="col" className="border border-pp-line bg-pp-deep px-2 py-1 text-start text-pp-mute">
                  {t('audit.parity.audience')}
                </th>
                {langs.map((l) => (
                  <th key={l} scope="col" className="border border-pp-line bg-pp-deep px-2 py-1 text-pp-mute">
                    {l.toUpperCase()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...rows.entries()].map(([who, cells]) => (
                <tr key={who}>
                  <th scope="row" className="border border-pp-line px-2 py-1 text-start font-semibold text-pp-chalk">
                    {t(`persona.${who}`)}
                  </th>
                  {langs.map((l) => {
                    const keys = cells.get(l);
                    return (
                      <td key={l} className="ltr-nums border border-pp-line px-2 py-1 text-center" title={keys?.join(', ')}>
                        {keys ? (
                          <span className="text-pp-chalk">
                            {keys.length}/{p.key_facts.length}
                            <span className="sr-only">: {keys.join(', ')}</span>
                          </span>
                        ) : (
                          <span className="text-pp-mute">·</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {p.problems.length > 0 && (
        <>
          <p className="mt-2 text-xs text-pp-gold">{t('audit.parity.problems')}</p>
          <ul lang="en" dir="ltr" className="list-disc ps-5 text-start text-[11px] text-pp-pulseSoft">
            {p.problems.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
};

const Trace: React.FC<{ audit: MomentAudit; demo: boolean }> = ({ audit, demo }) => {
  const { t, num } = useI18n();
  const [all, setAll] = useState(false);
  const steps = audit.trace;
  const total = steps.reduce((s, x) => s + x.ms, 0);
  const shown = all ? steps : steps.slice(0, TRACE_PREVIEW);
  return (
    <section aria-labelledby="audit-trace">
      <SubHead id="audit-trace">{t('audit.trace')}</SubHead>
      {steps.length === 0 ? (
        <p className="border border-dashed border-pp-line px-3 py-2 text-xs text-pp-mute">{t(demo ? 'audit.trace.demo' : 'audit.trace.none')}</p>
      ) : (
        <>
          <p className="ltr-nums mb-2 text-xs text-pp-mute">{t('audit.trace.total', { n: steps.length, ms: num(total, 1) })}</p>
          <ol className="space-y-1">
            {shown.map((s, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 border border-pp-line/60 bg-pp-deep/60 px-2 py-1 text-[11px]">
                <span className="w-24 shrink-0 font-display text-xs font-bold uppercase tracking-broadcast text-pp-chalk">{s.agent}</span>
                <Badge tone={s.status === 'ok' ? 'mute' : s.status === 'fallback' ? 'gold' : s.status === 'skipped' ? 'mute' : 'pulse'}>
                  {t(`audit.status.${s.status}`)}
                </Badge>
                <span className="ltr-nums text-pp-signal">{num(s.ms, 2)} ms</span>
                {s.detail && (
                  <code dir="ltr" className="min-w-0 break-all text-pp-mute">
                    {s.detail}
                  </code>
                )}
              </li>
            ))}
          </ol>
          {steps.length > TRACE_PREVIEW && (
            <button
              type="button"
              onClick={() => setAll((v) => !v)}
              aria-expanded={all}
              className="mt-2 min-h-[44px] px-2 text-xs font-bold text-pp-signal hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
            >
              {all ? t('audit.trace.less') : t('audit.trace.all', { n: steps.length })}
            </button>
          )}
        </>
      )}
    </section>
  );
};

const Corrections: React.FC<{ audit: MomentAudit; onOpenMoment: (id: string) => void }> = ({ audit, onOpenMoment }) => {
  const { t } = useI18n();
  const retracts = audit.retracts ?? [];
  if (!retracts.length && !audit.ruled_out_by) return null;
  const link = (id: string) => (
    <button
      key={id}
      type="button"
      onClick={() => onOpenMoment(id)}
      className="inline-flex min-h-[44px] items-center gap-1.5 border border-pp-pulse/70 px-3 text-xs font-bold text-pp-chalk hover:bg-pp-pulse/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
    >
      <Gavel className="h-3.5 w-3.5 text-pp-pulse" aria-hidden />
      <code dir="ltr">{id}</code>
    </button>
  );
  return (
    <section aria-label={t('audit.var')} className="border-s-4 border-pp-pulse bg-pp-pulse/10 p-3">
      {retracts.length > 0 && (
        <>
          <p className="mb-2 text-xs text-pp-chalk">{t('audit.var.retracts')}</p>
          <div className="flex flex-wrap gap-2">{retracts.map(link)}</div>
        </>
      )}
      {audit.ruled_out_by && (
        <>
          <p className="mb-2 text-xs text-pp-chalk">{t('audit.var.ruledOut')}</p>
          <div className="flex flex-wrap gap-2">{link(audit.ruled_out_by)}</div>
        </>
      )}
    </section>
  );
};
