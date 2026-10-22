// "Under the hood" (#lab): the engine's metric registry, basic stats, the synthetic
// auto-eventing benchmark, dataset downloads, the MCP endpoint and the broadcast
// outputs. In the offline demo the parts recorded in demo-insights.json still work,
// and the rest says plainly that it needs the live match server.
import React, { useMemo, useState } from 'react';
import { BookOpen, Cable, Database, Microscope, MonitorPlay, Radar, Sigma } from 'lucide-react';
import type {
  AutoEventingStatus,
  BasicStats,
  BenchmarkClassRow,
  DatasetFormat,
  DatasetIndex,
  MetricQuality,
  MetricRegistry,
} from '../api/contract';
import { captureUrl, cueSheetUrl, datasetExportUrl, insights, mcpUrl } from '../api/insights';
import { useI18n } from '../i18n';
import { useInsight, useInsightMode } from '../state/useInsight';
import { CopyField, InsightGate, SubHead } from '../components/InsightStatus';
import { Badge, Panel, Segmented, cx } from '../components/ui';
import type { ViewProps } from './types';

const SECTIONS = [
  { id: 'lab-metrics', key: 'lab.metrics.title', icon: Sigma },
  { id: 'lab-stats', key: 'lab.stats.title', icon: BookOpen },
  { id: 'lab-bench', key: 'lab.bench.title', icon: Radar },
  { id: 'lab-data', key: 'lab.data.title', icon: Database },
  { id: 'lab-mcp', key: 'lab.mcp.title', icon: Cable },
  { id: 'lab-outputs', key: 'lab.outputs.title', icon: MonitorPlay },
] as const;

export const MCP_TOOLS = [
  'get_match_snapshot',
  'list_moments',
  'get_moment',
  'get_overlay_card',
  'get_recap',
  'get_cue_sheet',
  'get_player_stats',
  'get_basic_stats',
  'get_metric_registry',
  'get_team_rosters',
  'get_crew_status',
  'get_auto_eventing',
  'get_recent_events',
  'simulate_match',
] as const;

const QUALITY_TONE: Record<MetricQuality, string> = {
  counted: 'border-pp-chalk/60 text-pp-chalk',
  calibrated: 'border-pp-signal text-pp-signal',
  heuristic: 'border-pp-gold text-pp-gold',
  estimated_from_synthetic_tracking: 'border-pp-pulseSoft text-pp-pulseSoft',
};

export const QualityBadge: React.FC<{ quality: MetricQuality; title?: string }> = ({ quality, title }) => {
  const { t } = useI18n();
  return (
    <span title={title} className={cx('inline-flex items-center border px-1.5 py-0.5 font-display text-[12px] font-bold uppercase tracking-broadcast', QUALITY_TONE[quality])}>
      {t(`lab.quality.${quality}`)}
    </span>
  );
};

export const Lab: React.FC<ViewProps> = ({ match }) => {
  const { t } = useI18n();
  const mode = useInsightMode();
  const demo = mode === 'demo';
  return (
    <div className="space-y-4">
      <Panel
        title={
          <span className="flex items-center gap-2">
            <Microscope className="h-4 w-4" aria-hidden />
            {t('lab.title')}
          </span>
        }
      >
        <p className="text-sm text-slate-200">{t('lab.subtitle')}</p>
        <p className="mt-1 text-xs text-pp-mute">{t('lab.synthetic')}</p>
        {demo && (
          <div className="mt-3 border-s-4 border-pp-gold bg-pp-gold/10 px-3 py-2 text-xs text-pp-gold">
            <p className="font-bold">{t('lab.demo.title')}</p>
            <p className="mt-0.5">{t('lab.demo.works')}</p>
            <p className="mt-0.5">{t('lab.demo.needs')}</p>
          </div>
        )}
        <nav aria-label={t('lab.jump')} className="mt-3 flex flex-wrap gap-1.5">
          {SECTIONS.map((s) => (
            <a
              key={s.id}
              href={`#lab`}
              onClick={(e) => {
                e.preventDefault();
                document.getElementById(s.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                document.getElementById(s.id)?.focus({ preventScroll: true });
              }}
              className="inline-flex min-h-[44px] items-center gap-1.5 border border-pp-line bg-pp-deep px-3 font-display text-[13px] font-bold uppercase tracking-broadcast text-pp-mute hover:border-pp-pulse hover:text-pp-chalk focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
            >
              <s.icon className="h-4 w-4" aria-hidden />
              {t(s.key)}
            </a>
          ))}
        </nav>
      </Panel>

      <MetricsSection />
      <StatsSection clock={match.clock} spoilers={match.profile.spoilers} />
      <BenchmarkSection />
      <DatasetSection spoilers={match.profile.spoilers} />
      <McpSection />
      <OutputsSection persona={match.profile.persona} language={match.profile.language} />
    </div>
  );
};

const Section: React.FC<{ id: string; title: string; icon: React.ElementType; actions?: React.ReactNode; children: React.ReactNode }> = ({
  id,
  title,
  icon: Icon,
  actions,
  children,
}) => (
  <div id={id} tabIndex={-1} className="scroll-mt-40 focus:outline-none">
    <Panel
      title={
        <span className="flex items-center gap-2">
          <Icon className="h-4 w-4" aria-hidden />
          {title}
        </span>
      }
      actions={actions}
    >
      {children}
    </Panel>
  </div>
);

// ------------------------------------------------------------------ metric registry

export const STATS_POLL_MS = 10000;

const QUALITIES: MetricQuality[] = ['counted', 'calibrated', 'heuristic', 'estimated_from_synthetic_tracking'];

const MetricsSection: React.FC = () => {
  const { t } = useI18n();
  const mode = useInsightMode();
  const { state, reload } = useInsight(() => insights.metrics(mode), mode);
  const [filter, setFilter] = useState<MetricQuality | 'all'>('all');
  return (
    <Section id="lab-metrics" title={t('lab.metrics.title')} icon={Sigma}>
      <p className="mb-3 text-sm text-pp-mute">{t('lab.metrics.hint')}</p>
      {state.status !== 'ready' ? (
        <InsightGate state={state} onRetry={reload} lines={6} />
      ) : (
        <Registry registry={state.data} filter={filter} setFilter={setFilter} />
      )}
    </Section>
  );
};

const Registry: React.FC<{ registry: MetricRegistry; filter: MetricQuality | 'all'; setFilter: (q: MetricQuality | 'all') => void }> = ({
  registry,
  filter,
  setFilter,
}) => {
  const { t } = useI18n();
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const m of registry.metrics) c[m.quality] = (c[m.quality] ?? 0) + 1;
    return c;
  }, [registry.metrics]);
  const shown = filter === 'all' ? registry.metrics : registry.metrics.filter((m) => m.quality === filter);
  return (
    <div className="space-y-4">
      <ul className="grid gap-2 sm:grid-cols-2">
        {QUALITIES.map((q) => (
          <li key={q} className="flex items-start gap-2 text-xs">
            <QualityBadge quality={q} />
            <span lang="en" className="text-pp-mute">
              {registry.quality_flags[q]}
            </span>
          </li>
        ))}
      </ul>
      <Segmented
        label={t('lab.metrics.filter')}
        value={filter}
        onChange={setFilter}
        className="flex-wrap [&>button]:min-h-[44px]"
        options={[
          { value: 'all' as const, label: <span className="ltr-nums">{t('lab.metrics.all', { n: registry.metrics.length })}</span> },
          ...QUALITIES.map((q) => ({ value: q, label: <span className="ltr-nums">{`${t(`lab.quality.${q}`)} ${counts[q] ?? 0}`}</span> })),
        ]}
      />
      <p className="text-[11px] text-pp-mute">{t('lab.serverEnglish')}</p>
      <ul className="grid gap-3 lg:grid-cols-2" aria-live="polite">
        {shown.map((m) => (
          <li key={m.id} className="border border-pp-line bg-pp-deep/70 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h4 lang="en" className="font-display text-base font-bold uppercase tracking-broadcast text-pp-chalk">
                {m.name}
              </h4>
              <QualityBadge quality={m.quality} title={registry.quality_flags[m.quality]} />
            </div>
            <p className="mt-0.5 flex flex-wrap gap-x-3 text-[11px] text-pp-mute">
              <code dir="ltr">{m.id}</code>
              <span>
                {t('lab.metrics.scope')}: {t(`lab.scope.${m.scope}`)}
              </span>
              <span>
                {t('lab.metrics.units')}: <span lang="en">{m.units}</span>
              </span>
            </p>
            <dl className="mt-2 space-y-1 text-xs">
              <Row label={t('lab.metrics.formula')}>{m.formula}</Row>
              {m.symbols && (
                <Row label={t('lab.metrics.symbols')}>
                  <code dir="ltr" className="whitespace-pre-wrap text-pp-signal">
                    {m.symbols}
                  </code>
                </Row>
              )}
              <Row label={t('lab.metrics.limitations')}>{m.limitations}</Row>
            </dl>
            <details className="mt-1 text-xs">
              <summary className="flex min-h-[44px] cursor-pointer items-center font-bold text-pp-signal focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal">
                {t('lab.metrics.more')}
              </summary>
              <dl className="space-y-1">
                <Row label={t('lab.metrics.window')}>{m.window}</Row>
                <Row label={t('lab.metrics.range')}>{m.range}</Row>
                {m.edge_cases && <Row label={t('lab.metrics.edge')}>{m.edge_cases}</Row>}
                {m.source_events.length > 0 && <Row label={t('lab.metrics.sources')}>{m.source_events.join(', ')}</Row>}
              </dl>
            </details>
          </li>
        ))}
      </ul>
      <div>
        <SubHead>{t('lab.metrics.notComputed')}</SubHead>
        <ul className="space-y-1 text-xs">
          {registry.not_computed.map((n) => (
            <li key={n.id} className="flex flex-wrap gap-x-2 border-s-2 border-pp-line ps-2">
              <Badge>{t('lab.metrics.notBuilt')}</Badge>
              <span lang="en" className="font-semibold text-pp-chalk">
                {n.name}
              </span>
              <span lang="en" className="text-pp-mute">
                {n.reason}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="grid gap-x-2 sm:grid-cols-[7rem_1fr]">
    <dt className="text-[10px] font-bold uppercase tracking-broadcast text-pp-mute">{label}</dt>
    <dd lang="en" className="text-slate-200">
      {children}
    </dd>
  </div>
);

// ------------------------------------------------------------------ basic stats

const TEAM_ROWS: { key: string; get: (s: BasicStats['teams'][string], num: (v: number, d?: number) => string) => string }[] = [
  { key: 'possession', get: (s, num) => `${num(s.possession_pct, 1)}%` },
  { key: 'passes', get: (s) => `${s.passes_completed}/${s.passes_attempted}` },
  { key: 'passAccuracy', get: (s, num) => (s.pass_accuracy_pct == null ? '–' : `${num(s.pass_accuracy_pct, 1)}%`) },
  { key: 'shots', get: (s) => `${s.shots} (${s.shots_on_target})` },
  { key: 'goals', get: (s) => String(s.goals ?? '–') },
  { key: 'tackles', get: (s) => `${s.tackles_won}/${s.tackles_attempted}` },
  { key: 'interceptions', get: (s) => String(s.interceptions) },
  { key: 'fouls', get: (s) => String(s.fouls) },
  { key: 'ppda', get: (s, num) => (s.ppda == null ? '–' : num(s.ppda, 1)) },
  { key: 'distance', get: (s, num) => `${num(s.distance_km, 1)} km` },
  { key: 'topSpeed', get: (s, num) => `${num(s.top_speed_kmh, 1)} km/h` },
];

const StatsSection: React.FC<{ clock: string; spoilers: boolean }> = ({ clock, spoilers }) => {
  const { t } = useI18n();
  const mode = useInsightMode();
  const { state, reload, refreshing } = useInsight(() => insights.basicStats(mode, spoilers), `${mode}:${spoilers}`, { pollMs: STATS_POLL_MS });
  return (
    <Section
      id="lab-stats"
      title={t('lab.stats.title')}
      icon={BookOpen}
      actions={
        mode === 'live' && (
          <button
            type="button"
            onClick={reload}
            disabled={refreshing}
            className="min-h-[44px] border border-pp-line px-3 font-display text-[13px] font-bold uppercase tracking-broadcast text-pp-chalk hover:border-pp-pulse disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
          >
            {t('lab.stats.refresh', { clock })}
          </button>
        )
      }
    >
      <p className="mb-3 text-sm text-pp-mute">{t('lab.stats.hint')}</p>
      {state.status !== 'ready' ? (
        <InsightGate state={state} onRetry={reload} lines={6} needsServerKey="lab.stats.needsServer" />
      ) : (
        <StatsTables stats={state.data} hideResult={!spoilers} />
      )}
    </Section>
  );
};

/** `hideResult`: catch-up mode, so no goals row (a team's goals are the score). */
export const StatsTables: React.FC<{ stats: BasicStats; hideResult?: boolean }> = ({ stats, hideResult = false }) => {
  const { t, num } = useI18n();
  const teams = Object.values(stats.teams);
  const rows = TEAM_ROWS.filter((r) => r.key !== 'goals' || (!hideResult && teams.every((tm) => tm.goals !== null)));
  const [sort, setSort] = useState<'distance_km' | 'passes_completed' | 'top_speed_kmh'>('passes_completed');
  const players = useMemo(() => [...stats.players].sort((a, b) => b[sort] - a[sort]), [stats.players, sort]);
  return (
    <div className="space-y-4">
      <p className="flex flex-wrap gap-2 text-[11px] text-pp-mute">
        <Badge tone="mute">
          <span className="ltr-nums">{stats.clock}</span>
        </Badge>
        <span>{t('lab.stats.denominator')}:</span>
        <span lang="en" className="text-pp-chalk">
          {stats.pass_accuracy_denominator}
        </span>
        <span>·</span>
        <span lang="en" className="text-pp-gold">
          {stats.physical_label}
        </span>
      </p>
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[300px] border-collapse text-sm">
          <caption className="sr-only">{t('lab.stats.teamCaption')}</caption>
          <thead>
            <tr>
              <th scope="col" className="py-1 text-start text-[10px] uppercase tracking-broadcast text-pp-mute">
                {t('lab.stats.stat')}
              </th>
              {teams.map((tm) => (
                <th key={tm.team_id} scope="col" className="py-1 text-end font-display text-sm font-bold uppercase tracking-broadcast text-pp-chalk">
                  {tm.team_id}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-t border-pp-line/60">
                <th scope="row" className="py-1.5 text-start font-normal text-pp-mute">
                  {t(`lab.stats.${r.key}`)}
                </th>
                {teams.map((tm) => (
                  <td key={tm.team_id} className="ltr-nums py-1.5 text-end font-bold text-white">
                    {r.get(tm, num)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <SubHead className="mb-0">{t('lab.stats.players', { n: players.length })}</SubHead>
          <Segmented
            label={t('lab.stats.sort')}
            value={sort}
            onChange={setSort}
            className="[&>button]:min-h-[44px]"
            options={[
              { value: 'passes_completed' as const, label: t('lab.stats.passes') },
              { value: 'distance_km' as const, label: t('lab.stats.distance') },
              { value: 'top_speed_kmh' as const, label: t('lab.stats.topSpeed') },
            ]}
          />
        </div>
        <div className="relative max-h-80 overflow-auto border border-pp-line" tabIndex={0} aria-label={t('lab.stats.playerCaption')}>
          <table className="w-full min-w-[520px] border-collapse text-xs">
            <caption className="sr-only">{t('lab.stats.playerCaption')}</caption>
            <thead className="sticky top-0 bg-pp-deep">
              <tr className="text-[10px] uppercase tracking-broadcast text-pp-mute">
                <th scope="col" className="px-2 py-1 text-start">{t('lab.stats.player')}</th>
                <th scope="col" className="px-2 py-1 text-end">{t('lab.stats.passes')}</th>
                <th scope="col" className="px-2 py-1 text-end">{t('lab.stats.shots')}</th>
                <th scope="col" className="px-2 py-1 text-end">{t('lab.stats.tackles')}</th>
                <th scope="col" className="px-2 py-1 text-end">{t('lab.stats.distance')}</th>
                <th scope="col" className="px-2 py-1 text-end">{t('lab.stats.topSpeed')}</th>
              </tr>
            </thead>
            <tbody>
              {players.map((p) => (
                <tr key={p.player_id} className="border-t border-pp-line/50">
                  <th scope="row" className="px-2 py-1 text-start font-semibold text-pp-chalk">
                    <span className="ltr-nums me-1 text-pp-mute">{p.number ?? ''}</span>
                    {p.name ?? p.player_id}
                    <span className="ms-1 text-[10px] text-pp-mute">{p.team}</span>
                  </th>
                  <td className="ltr-nums px-2 py-1 text-end">{`${p.passes_completed}/${p.passes_attempted}`}</td>
                  <td className="ltr-nums px-2 py-1 text-end">{`${p.shots} (${p.shots_on_target})`}</td>
                  <td className="ltr-nums px-2 py-1 text-end">{`${p.tackles_won}/${p.tackles_attempted}`}</td>
                  <td className="ltr-nums px-2 py-1 text-end">{num(p.distance_km, 2)}</td>
                  <td className="ltr-nums px-2 py-1 text-end">{num(p.top_speed_kmh, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ benchmark

const BenchmarkSection: React.FC = () => {
  const { t } = useI18n();
  const mode = useInsightMode();
  const { state, reload } = useInsight(() => insights.autoEventing(mode), mode);
  return (
    <Section id="lab-bench" title={t('lab.bench.title')} icon={Radar}>
      <p className="mb-3 inline-flex border border-pp-pulse bg-pp-pulse/15 px-2 py-1 font-display text-sm font-bold uppercase tracking-broadcast text-pp-chalk">
        {t('lab.bench.label')}
      </p>
      {state.status !== 'ready' ? (
        <InsightGate state={state} onRetry={reload} lines={8} missingKey="lab.bench.missing" />
      ) : (
        <Benchmark data={state.data} />
      )}
    </Section>
  );
};

const pct = (v: number, num: (v: number, d?: number) => string) => `${num(v * 100, 1)}%`;
const ci = (c: [number, number] | null, num: (v: number, d?: number) => string) => (c ? `${num(c[0] * 100, 1)}–${num(c[1] * 100, 1)}` : '–');

export const Benchmark: React.FC<{ data: AutoEventingStatus }> = ({ data }) => {
  const { t, num } = useI18n();
  const rows = [...(data.classes ?? []), ...(data.pressure ? [data.pressure] : [])];
  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <BigStat label={t('lab.bench.passes')} value={`${num(data.passes_detected_pct, 1)}%`} />
        <BigStat
          label={t('lab.bench.speed')}
          value={`${num(data.speed_mae_kmh, 2)} km/h`}
          note={data.speed_mae_ci_kmh ? t('lab.bench.ci', { lo: num(data.speed_mae_ci_kmh[0], 2), hi: num(data.speed_mae_ci_kmh[1], 2) }) : undefined}
        />
        <BigStat label={t('lab.bench.events')} value={num(data.events_checked)} note={data.match_id ?? undefined} />
      </dl>

      {rows.length > 0 && (
        <div>
          <SubHead>{t('lab.bench.classes')}</SubHead>
          <ClassTable rows={rows} />
          <p className="mt-1 text-[11px] text-pp-mute">{t('lab.bench.ciNote')}</p>
        </div>
      )}

      {data.confusion && <Confusion confusion={data.confusion} />}

      {data.baseline && data.classes && <Baseline ours={data.classes} baseline={data.baseline} />}

      {data.pixel_path && <PixelPath row={data.pixel_path} />}

      {data.caveat && (
        <p lang="en" className="border-s-4 border-pp-gold bg-pp-gold/10 px-3 py-2 text-xs text-pp-gold">
          {data.caveat}
        </p>
      )}
    </div>
  );
};

const BigStat: React.FC<{ label: string; value: string; note?: string }> = ({ label, value, note }) => (
  <div className="border border-pp-line bg-pp-deep/70 px-3 py-2">
    <dt className="text-[10px] font-bold uppercase tracking-broadcast text-pp-mute">{label}</dt>
    <dd className="ltr-nums font-display text-2xl font-extrabold text-pp-chalk">{value}</dd>
    {note && <dd className="ltr-nums text-[11px] text-pp-mute">{note}</dd>}
  </div>
);

const ClassTable: React.FC<{ rows: BenchmarkClassRow[] }> = ({ rows }) => {
  const { t, num } = useI18n();
  return (
    <div className="relative overflow-x-auto">
      <table className="w-full min-w-[560px] border-collapse text-xs">
        <caption className="sr-only">{t('lab.bench.classes')}</caption>
        <thead>
          <tr className="text-[10px] uppercase tracking-broadcast text-pp-mute">
            <th scope="col" className="py-1 text-start">{t('lab.bench.kind')}</th>
            <th scope="col" className="py-1 text-end">{t('lab.bench.support')}</th>
            <th scope="col" className="py-1 text-end">{t('lab.bench.precision')}</th>
            <th scope="col" className="py-1 text-end">{t('lab.bench.recall')}</th>
            <th scope="col" className="py-1 text-end">F1</th>
            <th scope="col" className="w-1/4 py-1">
              <span className="sr-only">{t('health.bar')}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.kind} className="border-t border-pp-line/60">
              <th scope="row" className="py-1.5 text-start font-display text-sm font-bold uppercase tracking-broadcast text-pp-chalk">
                {t(`lab.kind.${r.kind}`)}
              </th>
              <td className="ltr-nums py-1.5 text-end text-pp-mute">{r.support}</td>
              <td className="ltr-nums py-1.5 text-end">
                {pct(r.precision, num)}
                <span className="block text-[10px] text-pp-mute">{ci(r.precision_ci, num)}</span>
              </td>
              <td className="ltr-nums py-1.5 text-end">
                {pct(r.recall, num)}
                <span className="block text-[10px] text-pp-mute">{ci(r.recall_ci, num)}</span>
              </td>
              <td className="ltr-nums py-1.5 text-end font-bold text-pp-signal">{num(r.f1, 3)}</td>
              <td className="py-1.5 ps-3" aria-hidden>
                <div className="h-2 bg-pp-deep">
                  <div className="h-2 bg-pp-signal" style={{ width: `${Math.max(1, r.f1 * 100)}%` }} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const kindLabel = (t: (k: string) => string, k: string) => {
  const out = t(`lab.kind.${k}`);
  return out === `lab.kind.${k}` ? k : out;
};

export const Confusion: React.FC<{ confusion: NonNullable<AutoEventingStatus['confusion']> }> = ({ confusion }) => {
  const { t } = useI18n();
  const max = Math.max(1, ...confusion.counts.flat());
  return (
    <div>
      <SubHead>{t('lab.bench.confusion')}</SubHead>
      <p className="mb-2 text-xs text-pp-mute">{t('lab.bench.confusionHint')}</p>
      <div className="relative overflow-x-auto">
        <table className="border-collapse text-[11px]">
          <caption className="sr-only">{t('lab.bench.confusion')}</caption>
          <thead>
            <tr>
              <th scope="col" className="p-1 text-start text-[10px] uppercase tracking-broadcast text-pp-mute">
                {t('lab.bench.trueDetected')}
              </th>
              {confusion.columns.map((c) => (
                <th key={c} scope="col" className="min-w-[3.25rem] p-1 text-center text-[10px] uppercase tracking-broadcast text-pp-mute">
                  {kindLabel(t, c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {confusion.rows.map((r, i) => (
              <tr key={r}>
                <th scope="row" className="p-1 text-start font-display text-xs font-bold uppercase tracking-broadcast text-pp-chalk">
                  {kindLabel(t, r)}
                </th>
                {confusion.columns.map((c, j) => {
                  const v = confusion.counts[i]?.[j] ?? 0;
                  const diag = r === c;
                  const a = v === 0 ? 0 : 0.15 + 0.85 * Math.sqrt(v / max);
                  return (
                    <td
                      key={c}
                      className={cx('ltr-nums h-10 min-w-[3.25rem] border border-pp-night p-1 text-center font-bold', a > 0.55 ? 'text-pp-night' : 'text-pp-chalk')}
                      style={{ background: v === 0 ? '#121210' : diag ? `rgba(255,212,0,${a})` : `rgba(255,59,47,${a})` }}
                    >
                      {v}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const Baseline: React.FC<{ ours: BenchmarkClassRow[]; baseline: NonNullable<AutoEventingStatus['baseline']> }> = ({ ours, baseline }) => {
  const { t, num } = useI18n();
  const base = new Map(baseline.classes.map((c) => [c.kind, c]));
  const rows = ours.filter((c) => base.has(c.kind));
  return (
    <div>
      <SubHead>{t('lab.bench.baseline')}</SubHead>
      <p lang="en" className="mb-2 text-xs text-pp-mute">
        {baseline.name}
      </p>
      <ul className="space-y-2">
        {rows.map((c) => {
          const b = base.get(c.kind)!;
          return (
            <li key={c.kind} className="grid grid-cols-[6rem_1fr] items-center gap-2 text-xs">
              <span className="font-display text-sm font-bold uppercase tracking-broadcast text-pp-chalk">{t(`lab.kind.${c.kind}`)}</span>
              <div className="space-y-1">
                <Bar label={t('lab.bench.ours')} value={c.f1} text={num(c.f1, 3)} tone="bg-pp-signal" />
                <Bar label={t('lab.bench.naive')} value={b.f1} text={num(b.f1, 3)} tone="bg-pp-mute" />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

const Bar: React.FC<{ label: string; value: number; text: string; tone: string }> = ({ label, value, text, tone }) => (
  <div className="flex items-center gap-2">
    <span className="w-16 shrink-0 text-[10px] uppercase tracking-broadcast text-pp-mute">{label}</span>
    <div className="h-2.5 flex-1 bg-pp-deep" aria-hidden>
      <div className={cx('h-2.5', tone)} style={{ width: `${Math.max(1, value * 100)}%` }} />
    </div>
    <span className="ltr-nums w-12 shrink-0 text-end font-bold">{text}</span>
  </div>
);

const PixelPath: React.FC<{ row: NonNullable<AutoEventingStatus['pixel_path']> }> = ({ row }) => {
  const { t, num } = useI18n();
  const pix = new Map(row.pixels.map((c) => [c.kind, c]));
  const base = import.meta.env.BASE_URL;
  return (
    <div>
      <SubHead>{t('lab.bench.pixel')}</SubHead>
      <p className="mb-2 inline-flex border border-pp-gold px-2 py-0.5 text-[11px] font-bold uppercase tracking-broadcast text-pp-gold">
        {t('lab.bench.pixelLabel')}
      </p>
      <div className="grid gap-4 md:grid-cols-[minmax(0,320px)_1fr]">
        <figure>
          <video
            className="w-full border border-pp-line bg-black"
            poster={`${base}lab/pixel-path-still.jpg`}
            muted
            loop
            playsInline
            controls
            preload="none"
            aria-label={t('lab.bench.videoAlt')}
          >
            {/* VP9 for browsers without H.264 (some open-source builds), then the original MP4. */}
            <source src={`${base}lab/pixel-path.webm`} type="video/webm" />
            <source src={`${base}lab/pixel-path.mp4`} type="video/mp4" />
          </video>
          <figcaption className="mt-1 text-[11px] text-pp-mute">{t('lab.bench.videoCaption')}</figcaption>
        </figure>
        <div className="space-y-2 text-xs">
          <dl className="grid grid-cols-2 gap-2">
            <BigStat label={t('lab.bench.frames')} value={`${num(row.frames)}`} note={`${row.width_px}×${row.height_px} px · ${num(row.window_s, 0)} s`} />
            <BigStat label={t('lab.bench.ballFound')} value={`${num(row.ball_found_pct, 1)}%`} />
            <BigStat label={t('lab.bench.playerError')} value={row.player_error_m == null ? '–' : `${num(row.player_error_m, 3)} m`} />
            <BigStat label={t('lab.bench.ballError')} value={row.ball_error_m == null ? '–' : `${num(row.ball_error_m, 3)} m`} />
          </dl>
          <table className="w-full border-collapse text-xs">
            <caption className="sr-only">{t('lab.bench.pixelCompare')}</caption>
            <thead>
              <tr className="text-[10px] uppercase tracking-broadcast text-pp-mute">
                <th scope="col" className="py-1 text-start">{t('lab.bench.kind')}</th>
                <th scope="col" className="py-1 text-end">{t('lab.bench.support')}</th>
                <th scope="col" className="py-1 text-end">{t('lab.bench.f1Coord')}</th>
                <th scope="col" className="py-1 text-end">{t('lab.bench.f1Pixels')}</th>
              </tr>
            </thead>
            <tbody>
              {row.coordinate.map((c) => (
                <tr key={c.kind} className="border-t border-pp-line/60">
                  <th scope="row" className="py-1 text-start font-semibold text-pp-chalk">
                    {t(`lab.kind.${c.kind}`)}
                  </th>
                  <td className="ltr-nums py-1 text-end text-pp-mute">{c.support}</td>
                  {/* No true events of this kind in the clip: F1 has nothing to measure. */}
                  <td className="ltr-nums py-1 text-end">{c.support ? num(c.f1, 3) : '–'}</td>
                  <td className="ltr-nums py-1 text-end text-pp-signal">{c.support && pix.has(c.kind) ? num(pix.get(c.kind)!.f1, 3) : '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[11px] text-pp-mute">{t('lab.bench.pixelSmall')}</p>
          <p className="ltr-nums text-[11px] text-pp-mute">
            {t('lab.bench.pixelSpeed', {
              c: row.speed_mae_kmh_coordinate == null ? '–' : num(row.speed_mae_kmh_coordinate, 2),
              p: row.speed_mae_kmh_pixels == null ? '–' : num(row.speed_mae_kmh_pixels, 2),
            })}
          </p>
        </div>
      </div>
    </div>
  );
};

// ------------------------------------------------------------------ dataset

const DatasetSection: React.FC<{ spoilers: boolean }> = ({ spoilers }) => {
  const { t } = useI18n();
  const mode = useInsightMode();
  const { state, reload } = useInsight(() => insights.dataset(mode), mode);
  return (
    <Section id="lab-data" title={t('lab.data.title')} icon={Database}>
      {state.status !== 'ready' ? <InsightGate state={state} onRetry={reload} lines={5} /> : <Dataset index={state.data} demo={state.source === 'demo'} hideResult={!spoilers} />}
    </Section>
  );
};

const FORMATS: DatasetFormat[] = ['jsonl', 'csv', 'zip'];

/** `hideResult`: catch-up mode, so no results and no storyline blurbs (the demo's tells how it ends). */
export const Dataset: React.FC<{ index: DatasetIndex; demo: boolean; hideResult?: boolean }> = ({ index, demo, hideResult = false }) => {
  const { t } = useI18n();
  const bundled = index.matches.filter((m) => m.kind === 'bundled');
  const seeded = index.matches.filter((m) => m.kind === 'seeded');
  const [showSeeded, setShowSeeded] = useState(false);
  const rows = showSeeded ? index.matches : bundled;
  return (
    <div className="space-y-3">
      <p className="flex flex-wrap items-center gap-2 text-sm">
        <Badge tone="gold">{t('lab.data.synthetic')}</Badge>
        <span className="text-pp-mute">{t('lab.data.hint')}</span>
      </p>
      <ul className="grid gap-1 text-xs sm:grid-cols-3">
        {Object.entries(index.scenarios).map(([k, v]) => (
          <li key={k} className="border border-pp-line/70 bg-pp-deep/60 p-2">
            <code dir="ltr" className="block text-pp-signal">
              {k}
            </code>
            {hideResult ? (
              <span className="text-pp-mute">{t('catchup.hiddenValue')}</span>
            ) : (
              <span lang="en" className="text-pp-mute">
                {v}
              </span>
            )}
          </li>
        ))}
      </ul>
      {demo && <p className="border border-dashed border-pp-line px-3 py-2 text-xs text-pp-mute">{t('lab.data.demo')}</p>}
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse text-xs">
          <caption className="sr-only">{t('lab.data.title')}</caption>
          <thead>
            <tr className="text-[10px] uppercase tracking-broadcast text-pp-mute">
              <th scope="col" className="py-1 text-start">{t('lab.data.match')}</th>
              <th scope="col" className="py-1 text-start">{t('lab.data.scenario')}</th>
              <th scope="col" className="py-1 text-end">{t('lab.data.seed')}</th>
              <th scope="col" className="py-1 text-center">{t('lab.data.score')}</th>
              <th scope="col" className="py-1 text-end">{t('lab.data.events')}</th>
              <th scope="col" className="py-1 text-end">{t('lab.data.download')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.match_id} className="border-t border-pp-line/60">
                <th scope="row" className="py-1 text-start">
                  <code dir="ltr" className="font-bold text-pp-chalk">
                    {m.match_id}
                  </code>
                </th>
                <td className="py-1">
                  <code dir="ltr" className="text-pp-mute">
                    {m.scenario}
                  </code>
                </td>
                <td className="ltr-nums py-1 text-end">{m.seed}</td>
                <td className="ltr-nums py-1 text-center">
                  {hideResult ? (
                    <>
                      {`${m.home}–${m.away}`} <span className="text-pp-mute">({t('catchup.hiddenValue')})</span>
                    </>
                  ) : m.score ? (
                    `${m.home} ${m.score} ${m.away}`
                  ) : (
                    `${m.home}–${m.away}`
                  )}
                </td>
                <td className="ltr-nums py-1 text-end">{m.events ?? '–'}</td>
                <td className="py-1 text-end">
                  <span className="inline-flex gap-1">
                    {FORMATS.filter((f) => index.formats.includes(f)).map((f) => {
                      const href = demo ? null : datasetExportUrl(m.match_id, f);
                      return href ? (
                        <a
                          key={f}
                          href={href}
                          download
                          aria-label={t('lab.data.get', { id: m.match_id, format: f.toUpperCase() })}
                          className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center border border-pp-line px-2 font-display text-xs font-bold uppercase text-pp-signal hover:border-pp-signal focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
                        >
                          {f}
                        </a>
                      ) : (
                        <span
                          key={f}
                          aria-disabled="true"
                          title={t('lab.data.demo')}
                          className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center border border-dashed border-pp-line px-2 font-display text-xs font-bold uppercase text-pp-mute"
                        >
                          {f}
                        </span>
                      );
                    })}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {seeded.length > 0 && (
        <button
          type="button"
          onClick={() => setShowSeeded((v) => !v)}
          aria-expanded={showSeeded}
          className="min-h-[44px] px-2 text-xs font-bold text-pp-signal hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
        >
          {showSeeded ? t('lab.data.hideSeeded') : t('lab.data.showSeeded', { n: seeded.length, from: index.seeded.seed_start, to: index.seeded.seed_end })}
        </button>
      )}
      <p className="ltr-nums text-[11px] text-pp-mute">
        {t('lab.data.meta', {
          v: index.schema_version,
          l: index.pitch.length_m,
          w: index.pitch.width_m,
          hz: index.tracking.hz,
          s: index.tracking.max_window_s,
        })}
      </p>
    </div>
  );
};

// ------------------------------------------------------------------ MCP

const McpSection: React.FC = () => {
  const { t } = useI18n();
  const demo = useInsightMode() === 'demo';
  return (
    <Section id="lab-mcp" title={t('lab.mcp.title')} icon={Cable}>
      <p className="mb-3 text-sm text-pp-mute">{t('lab.mcp.hint')}</p>
      {demo && <p className="mb-3 border border-dashed border-pp-line px-3 py-2 text-xs text-pp-mute">{t('lab.mcp.demo')}</p>}
      <div className="grid gap-3 md:grid-cols-2">
        <CopyField label={t('lab.mcp.http')} value={mcpUrl()} />
        <CopyField label={t('lab.mcp.stdio')} value="matchmind-mcp" />
      </div>
      <p className="mb-2 mt-1 text-[11px] text-pp-mute">{t('lab.mcp.readOnly')}</p>
      <SubHead>{t('lab.mcp.tools', { n: MCP_TOOLS.length })}</SubHead>
      <ul className="grid gap-1.5 text-xs sm:grid-cols-2">
        {MCP_TOOLS.map((name) => (
          <li key={name} className="border border-pp-line/70 bg-pp-deep/60 px-2 py-1.5">
            <code dir="ltr" className="font-bold text-pp-signal">
              {name}
            </code>
            <span className="block text-pp-mute">{t(`lab.mcp.tool.${name}`)}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
};

// ------------------------------------------------------------------ broadcast outputs

const OutputsSection: React.FC<{ persona: string; language: string }> = ({ persona, language }) => {
  const { t } = useI18n();
  const demo = useInsightMode() === 'demo';
  const p = persona === 'player_spotlight' ? 'casual' : persona;
  const capture = captureUrl(p, language, demo);
  const cues = cueSheetUrl(p, language);
  return (
    <Section id="lab-outputs" title={t('lab.outputs.title')} icon={MonitorPlay}>
      <p className="mb-3 text-sm text-pp-mute">{t('lab.outputs.hint')}</p>
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <CopyField label={t('lab.outputs.obs')} value={capture} href={capture} />
          <p className="text-[11px] text-pp-mute">{t(demo ? 'lab.outputs.obsDemo' : 'lab.outputs.obsHint')}</p>
        </div>
        <div>
          <CopyField label={t('lab.outputs.cues')} value={cues} href={demo ? null : cues} />
          <p className="text-[11px] text-pp-mute">{t(demo ? 'lab.outputs.cuesDemo' : 'lab.outputs.cuesHint')}</p>
        </div>
      </div>
    </Section>
  );
};
