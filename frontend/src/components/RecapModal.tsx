import React, { useEffect, useRef } from 'react';
import { AlertTriangle, Award, CheckCircle2, FileText, X } from 'lucide-react';
import type { Recap, Teams } from '../api/contract';
import { useI18n } from '../i18n';
import { playerById } from '../lib/teams';
import { Badge } from './ui';
import { factLabel, factValue } from './BroadcastOverlay';

export interface RecapModalProps {
  open: boolean;
  onClose: () => void;
  recap: Recap | null;
  loading: boolean;
  teams: Teams | null;
}

const Skeleton: React.FC = () => {
  const { t } = useI18n();
  return (
    <div role="status" aria-live="polite" className="space-y-4">
      <span className="sr-only">{t('broadcast.recap.loading')}</span>
      <div className="h-3 w-1/3 animate-pulse rounded bg-pp-raised" />
      <div className="h-7 w-3/4 animate-pulse rounded bg-pp-raised" />
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-3 w-full animate-pulse rounded bg-pp-raised/70" />
      ))}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="h-28 animate-pulse rounded-xl bg-pp-raised/60" />
        <div className="h-28 animate-pulse rounded-xl bg-pp-raised/60" />
      </div>
      <p aria-hidden className="text-center text-xs text-pp-mute">{t('broadcast.recap.loading')}</p>
    </div>
  );
};

const SectionTitle: React.FC<{ children: React.ReactNode; tone?: string }> = ({ children, tone = 'text-slate-300' }) => (
  <h3 className={`mb-2 font-display text-xs font-bold uppercase tracking-wider ${tone}`}>{children}</h3>
);

const RecapBody: React.FC<{ recap: Recap; teams: Teams | null }> = ({ recap, teams }) => {
  const i18n = useI18n();
  const { t } = i18n;
  const potm = playerById(teams, recap.player_of_the_match_id);
  const potmName = recap.player_of_the_match ?? potm?.name ?? null;
  const potmColor = potm?.team.primary_color ?? '#fbbf24';
  const stats = Object.entries(recap.stats);

  return (
    <div className="space-y-6">
      <div className="border-b border-pp-line pb-4">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-bold uppercase tracking-widest text-pp-signal">
            {t('broadcast.recap.generatedAt', { clock: `⁦${recap.generated_at_clock}⁩` })}
          </span>
          <Badge tone={recap.produced_by === 'ai' ? 'signal' : 'mute'}>{t(`produced.${recap.produced_by}`)}</Badge>
        </div>
        <h2 id="recap-headline" className="font-display text-2xl font-extrabold tracking-wide text-white">
          {recap.headline}
        </h2>
      </div>

      {recap.summary_paragraphs.length > 0 && (
        <section>
          <SectionTitle>{t('broadcast.recap.summary')}</SectionTitle>
          <div className="space-y-3">
            {recap.summary_paragraphs.map((para, idx) => (
              <p key={idx} className="text-sm leading-relaxed text-slate-300">
                {para}
              </p>
            ))}
          </div>
        </section>
      )}

      <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-2">
        <section className="rounded-xl border border-pp-line bg-pp-night/70 p-4">
          <SectionTitle tone="text-pp-gold">{t('broadcast.recap.keyMoments')}</SectionTitle>
          {recap.key_moments.length ? (
            <ol className="max-h-72 space-y-1.5 overflow-y-auto pe-1">
              {recap.key_moments.map((m) => (
                <li key={m.moment_id} className="flex items-start gap-2 rounded-lg border border-pp-line/60 bg-pp-deep p-2 text-xs">
                  <span className="ltr-nums shrink-0 rounded bg-pp-raised px-1.5 py-0.5 font-bold text-pp-signal">{m.match_clock}</span>
                  <span className="min-w-0">
                    <Badge tone="pulse" className="mb-0.5">
                      {t(`kind.${m.kind}`)}
                    </Badge>
                    {m.headline !== t(`kind.${m.kind}`) && <span className="block text-slate-200">{m.headline}</span>}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-xs text-pp-mute">{t('common.none')}</p>
          )}
        </section>

        <section
          className="flex flex-col items-center justify-center gap-2 rounded-xl border bg-pp-night/70 p-4 text-center"
          style={{ borderColor: `${potmColor}88` }}
        >
          <Award className="h-8 w-8" style={{ color: potmColor }} aria-hidden />
          <span className="text-[11px] font-bold uppercase tracking-widest text-pp-mute">{t('broadcast.recap.potm')}</span>
          <p className="font-display text-xl font-extrabold tracking-wide text-white">{potmName ?? t('common.none')}</p>
          {potm && (
            <p className="flex items-center gap-1.5 text-xs text-slate-300">
              <span aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: potm.team.primary_color }} />
              {potm.team.short_name} · <span className="ltr-nums">#{potm.number}</span> {potm.position}
            </p>
          )}
        </section>
      </div>

      {stats.length > 0 && (
        <section>
          <SectionTitle>{t('broadcast.recap.stats')}</SectionTitle>
          <div className="overflow-hidden rounded-xl border border-pp-line">
            <table className="w-full text-sm">
              <thead className="sr-only">
                <tr>
                  <th scope="col">{t('broadcast.recap.stat')}</th>
                  <th scope="col">{t('broadcast.recap.value')}</th>
                </tr>
              </thead>
              <tbody>
                {stats.map(([key, value], i) => (
                  <tr key={key} className={i % 2 ? 'bg-pp-deep' : 'bg-pp-night/60'}>
                    <th scope="row" className="px-3 py-1.5 text-start font-normal text-pp-mute">
                      {factLabel(t, key)}
                    </th>
                    <td className="px-3 py-1.5 text-end font-semibold text-white">
                      <span className="ltr-nums">{factValue(i18n, value)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {recap.fact_check.ok ? (
        <p className="flex items-center gap-2 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
          <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden />
          {t('broadcast.recap.factOk')}
        </p>
      ) : (
        <div className="rounded-xl border border-pp-gold/40 bg-pp-gold/10 px-3 py-2 text-sm text-pp-gold">
          <p className="flex items-center gap-2 font-semibold">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
            {t('broadcast.recap.factFail')}
          </p>
          <ul className="mt-1 list-disc space-y-0.5 ps-6 text-xs">
            {recap.fact_check.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export const RecapModal: React.FC<RecapModalProps> = ({ open, onClose, recap, loading, teams }) => {
  const { t, dir } = useI18n();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      dir={dir}
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/80 p-3 backdrop-blur-md sm:p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="recap-title"
        onClick={(e) => e.stopPropagation()}
        className="relative flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-pp-line bg-pp-panel shadow-2xl"
      >
        <header className="flex items-center justify-between gap-3 border-b border-pp-line bg-gradient-to-r from-pp-pulse/20 via-pp-raised to-pp-panel px-4 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-2">
            <FileText className="h-5 w-5 shrink-0 text-pp-pulse" aria-hidden />
            <h2 id="recap-title" className="truncate font-display text-lg font-bold uppercase tracking-wider text-white">
              {recap?.title || t('broadcast.recap.title')}
            </h2>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label={t('broadcast.recap.close')}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-pp-mute transition hover:bg-white/10 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="overflow-y-auto p-4 sm:p-6">
          {loading ? (
            <Skeleton />
          ) : recap ? (
            <RecapBody recap={recap} teams={teams} />
          ) : (
            <div className="flex flex-col items-center gap-2 py-12 text-center">
              <FileText className="h-10 w-10 text-pp-line" aria-hidden />
              <p className="font-display text-lg font-semibold text-white">{t('broadcast.recap.empty')}</p>
              <p className="max-w-md text-sm text-pp-mute">{t('broadcast.recap.emptyHint')}</p>
            </div>
          )}
        </div>

        <footer className="flex justify-end border-t border-pp-line bg-pp-deep px-4 py-3 sm:px-6">
          <button
            type="button"
            onClick={onClose}
            className="min-h-[36px] rounded-lg bg-pp-pulse px-4 text-xs font-bold text-white transition hover:bg-pp-pulse/85"
          >
            {t('broadcast.recap.close')}
          </button>
        </footer>
      </div>
    </div>
  );
};
