// Crew health: who runs the model steps, who chains the agents, and the crew's
// rolling service levels from GET /api/crew/status (docs/TRUST.md). Every rate
// sits next to its counts; nothing is estimated in the browser.
import React from 'react';
import { Activity, CircuitBoard, Gauge, Languages } from 'lucide-react';
import type { CrewStatus } from '../api/contract';
import { insights } from '../api/insights';
import { useI18n } from '../i18n';
import { useInsight, useInsightMode } from '../state/useInsight';
import type { MatchViewState } from '../state/matchStore';
import { InsightGate, SubHead } from './InsightStatus';
import { Badge, Panel, cx } from './ui';

const PROVIDERS = ['templates', 'azure_openai', 'foundry_agents'] as const;
const ORCHESTRATORS = ['in_process', 'agent_framework'] as const;
export const HEALTH_POLL_MS = 5000;

export const CrewHealth: React.FC<{ match: Pick<MatchViewState, 'crew'> }> = ({ match }) => {
  const { t } = useI18n();
  const mode = useInsightMode();
  const { state, reload, refreshing } = useInsight(() => insights.crewStatus(mode), mode, { pollMs: HEALTH_POLL_MS });
  // The offline demo has no crew running: show what the recording says, and say what needs the server.
  const status: CrewStatus | null = state.status === 'ready' ? state.data : mode === 'demo' ? match.crew : null;
  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <Activity className="h-4 w-4" aria-hidden />
          {t('health.title')}
        </span>
      }
      actions={
        <span className="flex items-center gap-2 text-[11px] text-pp-mute" aria-live="polite">
          {mode === 'live' && state.status === 'ready' && (
            <>
              <span className={cx('h-2 w-2 rounded-full bg-pp-signal', refreshing && 'animate-heartbeat')} aria-hidden />
              {t('health.auto')}
            </>
          )}
          {mode === 'demo' && <Badge tone="gold">{t('conn.demo')}</Badge>}
        </span>
      }
    >
      {!status ? (
        <InsightGate state={state} onRetry={reload} lines={5} />
      ) : (
        <HealthBody status={status} demo={mode === 'demo'} />
      )}
    </Panel>
  );
};

const Choice: React.FC<{ label: string; active: boolean; note?: string }> = ({ label, active, note }) => (
  <li
    aria-current={active ? 'true' : undefined}
    className={cx(
      'flex min-h-[44px] flex-col justify-center border px-2.5 py-1.5',
      active ? 'border-pp-signal bg-pp-signal/10 text-pp-chalk' : 'border-dashed border-pp-line text-pp-mute',
    )}
  >
    <span className="font-display text-sm font-bold uppercase tracking-broadcast">{label}</span>
    {note && <span className="text-[10px]">{note}</span>}
  </li>
);

export const HealthBody: React.FC<{ status: CrewStatus; demo: boolean }> = ({ status, demo }) => {
  const { t, num } = useI18n();
  const provider = status.provider ?? (status.mode === 'ai' ? 'azure_openai' : 'templates');
  const orchestrator = status.orchestrator ?? 'in_process';
  const h = status.health;
  const rate = (r: number | null | undefined, n: number, d: number) =>
    r == null ? t('health.rateNone', { n, d }) : t('health.rate', { pct: num(r * 100, 1), n, d });
  const maxP95 = Math.max(1, ...(h?.latency ?? []).map((l) => l.p95_ms));
  const tr = status.translator;
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <SubHead>{t('health.provider')}</SubHead>
          <ul className="grid gap-1.5" aria-label={t('health.provider')}>
            {PROVIDERS.map((p) => (
              <Choice key={p} label={t(`health.provider.${p}`)} active={provider === p} note={provider === p ? t('health.active') : t('health.offUntil')} />
            ))}
          </ul>
        </div>
        <div>
          <SubHead>{t('health.orchestrator')}</SubHead>
          <ul className="grid gap-1.5" aria-label={t('health.orchestrator')}>
            {ORCHESTRATORS.map((o) => (
              <Choice key={o} label={t(`health.orchestrator.${o}`)} active={orchestrator === o} note={orchestrator === o ? t('health.active') : t('health.offUntil')} />
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-pp-mute">
            {t('health.model')}{' '}
            <code dir="ltr" className="text-pp-chalk">
              {status.model ?? t('health.noModel')}
            </code>
          </p>
        </div>
      </div>

      {demo || !h ? (
        <p className="border border-dashed border-pp-line px-3 py-2 text-xs text-pp-mute">{t(demo ? 'health.demo' : 'health.noHealth')}</p>
      ) : (
        <>
          <dl className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <Stat icon={<Gauge className="h-4 w-4" aria-hidden />} label={t('health.momentsPerMin')} value={num(h.moments_per_min, 1)} />
            <Stat label={t('health.fallbackRate')} value={rate(h.fallback_rate, h.fallback_steps, h.model_steps)} />
            <Stat label={t('health.rejectionRate')} value={rate(h.rejection_rate, h.rejected_checks, h.checks)} />
          </dl>
          {status.mode === 'template' && <p className="text-[11px] text-pp-mute">{t('health.templateNote')}</p>}
          <div>
            <SubHead>{t('health.latency')}</SubHead>
            {h.latency.length === 0 ? (
              <p className="text-xs text-pp-mute">{t('health.noSamples')}</p>
            ) : (
              <div className="relative overflow-x-auto">
                <table className="w-full min-w-[320px] border-collapse text-xs">
                  <caption className="sr-only">{t('health.latencyCaption', { n: h.window })}</caption>
                  <thead>
                    <tr className="text-[10px] uppercase tracking-broadcast text-pp-mute">
                      <th scope="col" className="py-1 text-start">{t('health.agent')}</th>
                      <th scope="col" className="py-1 text-end">{t('health.samples')}</th>
                      <th scope="col" className="py-1 text-end">p50</th>
                      <th scope="col" className="py-1 text-end">p95</th>
                      <th scope="col" className="w-1/3 py-1"><span className="sr-only">{t('health.bar')}</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {h.latency.map((l) => (
                      <tr key={l.agent} className="border-t border-pp-line/60">
                        <th scope="row" className="py-1.5 text-start font-display text-sm font-bold uppercase tracking-broadcast text-pp-chalk">{l.agent}</th>
                        <td className="ltr-nums py-1.5 text-end text-pp-mute">{l.samples}</td>
                        <td className="ltr-nums py-1.5 text-end text-pp-chalk">{num(l.p50_ms, 1)} ms</td>
                        <td className="ltr-nums py-1.5 text-end text-pp-signal">{num(l.p95_ms, 1)} ms</td>
                        <td className="py-1.5 ps-3" aria-hidden>
                          <div className="h-2 bg-pp-deep">
                            <div className="h-2 bg-pp-signal" style={{ width: `${Math.max(2, (l.p95_ms / maxP95) * 100)}%` }} />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <SubHead>
            <span className="inline-flex items-center gap-1.5">
              <CircuitBoard className="h-4 w-4 text-pp-pulse" aria-hidden />
              {t('health.breakers')}
            </span>
          </SubHead>
          {status.breakers_open.length === 0 ? (
            <p className="text-xs text-pp-mute">{t('health.breakersNone')}</p>
          ) : (
            <ul className="flex flex-wrap gap-1.5">
              {status.breakers_open.map((b) => (
                <li key={b}>
                  <Badge tone="pulse">{b}</Badge>
                </li>
              ))}
            </ul>
          )}
          <p className="ltr-nums mt-1 text-[11px] text-pp-mute">
            {t('health.totals', { m: status.moments, f: status.fallbacks, r: status.rejections })}
          </p>
        </div>
        <div>
          <SubHead>
            <span className="inline-flex items-center gap-1.5">
              <Languages className="h-4 w-4 text-pp-signal" aria-hidden />
              {t('health.translator')}
            </span>
          </SubHead>
          {!tr || tr.mode === 'off' ? (
            <p className="text-xs text-pp-mute">{t('health.translatorOff')}</p>
          ) : (
            <p className="ltr-nums text-xs text-pp-chalk">
              {t(tr.breaker_open ? 'health.translatorBreaker' : tr.available ? 'health.translatorOn' : 'health.translatorDown')}{' '}
              <span className="text-pp-mute">
                {t('health.translatorCounts', { n: tr.translated, c: tr.cache_hits, f: tr.fallbacks, r: tr.rejections })}
              </span>
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

const Stat: React.FC<{ label: string; value: string; icon?: React.ReactNode }> = ({ label, value, icon }) => (
  <div className="border border-pp-line bg-pp-deep/70 px-3 py-2">
    <dt className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-broadcast text-pp-mute">
      {icon}
      {label}
    </dt>
    <dd className="ltr-nums mt-0.5 font-display text-lg font-extrabold text-pp-chalk">{value}</dd>
  </div>
);
