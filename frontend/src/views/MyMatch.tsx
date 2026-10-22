import React, { useMemo } from 'react';
import { BellRing, Heart, HeartOff, Info } from 'lucide-react';
import type { FocusMetric, MatchEvent, OverlayCard, PlayerStats, TeamInfo, Teams } from '../api/contract';
import { Badge, Panel, Segmented, TeamDot, cx } from '../components/ui';
import { useI18n } from '../i18n';
import type { MatchViewState, MetricSample } from '../state/matchStore';
import { playerName, teamById } from '../lib/teams';
import { CardItem } from './PlayerFocus';
import type { ViewProps } from './types';
import { ScoreValue } from '../components/CatchUp';
import { AskStudio } from '../components/AskStudio';
import { inkOn } from '../lib/contrast';

type Side = 'home' | 'away';
const METRICS: FocusMetric[] = ['pressure', 'xg', 'pass_difficulty', 'top_speed', 'momentum'];

export function favouriteSide(teams: Teams | null, favourite: string | null): Side | null {
  if (!teams || !favourite) return null;
  return teams.home.team_id === favourite ? 'home' : teams.away.team_id === favourite ? 'away' : null;
}

/** Score from the favourite's point of view (home first when there is none). */
export function perspectiveScore(score: { home: number | null; away: number | null }, side: Side | null) {
  return side === 'away' ? { us: score.away, them: score.home } : { us: score.home, them: score.away };
}

export function fastestPlayer(players: Record<string, PlayerStats>): PlayerStats | null {
  let best: PlayerStats | null = null;
  for (const p of Object.values(players)) if (!best || p.top_speed_kmh > best.top_speed_kmh) best = p;
  return best;
}

export function latestPassDifficulty(events: MatchEvent[]): MatchEvent | null {
  for (let i = events.length - 1; i >= 0; i--) if (events[i].metrics.pass_difficulty != null) return events[i];
  return null;
}

/** Card ordering for a favourite: their cards first (newest first), the rest after. */
export function isFavCard(c: OverlayCard, favourite: string | null): boolean | null {
  if (c.favourite_side != null) return c.favourite_side;
  if (!favourite || !c.team) return null;
  return c.team === favourite;
}

// ---------- sparkline ----------

const Sparkline: React.FC<{ series: { values: number[]; color: string }[]; label: string; zero?: boolean; min?: number; max?: number }> = ({
  series,
  label,
  zero,
  min,
  max,
}) => {
  const all = series.flatMap((s) => s.values);
  if (all.length < 2) return null;
  const lo = min ?? Math.min(...all, zero ? 0 : Infinity);
  const hi = max ?? Math.max(...all, zero ? 0 : -Infinity);
  const span = hi - lo || 1;
  const W = 300;
  const H = 72;
  const y = (v: number) => H - 4 - ((v - lo) / span) * (H - 8);
  return (
    <div dir="ltr" className="mt-3">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-20 w-full" role="img" aria-label={label}>
        {zero && lo < 0 && hi > 0 && <line x1={0} x2={W} y1={y(0)} y2={y(0)} stroke="#64748b" strokeDasharray="4 4" strokeWidth={1} />}
        {series.map((s, i) => {
          const n = s.values.length;
          const pts = s.values.map((v, j) => `${((j / Math.max(1, n - 1)) * W).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
          return <polyline key={i} points={pts} fill="none" stroke={s.color} strokeWidth={2} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />;
        })}
      </svg>
    </div>
  );
};

// ---------- favourite picker ----------

const ClubButton: React.FC<{ team: TeamInfo; on: boolean; onPick: () => void }> = ({ team, on, onPick }) => {
  const { t } = useI18n();
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onPick}
      className={cx('relative min-h-[96px] overflow-hidden rounded-2xl border-2 bg-pp-deep p-3 text-start transition', on && 'shadow-lg')}
      style={{ borderColor: on ? team.primary_color : `${team.primary_color}55`, boxShadow: on ? `0 0 24px ${team.primary_color}44` : undefined }}
    >
      <span aria-hidden className="absolute inset-y-0 start-0 w-2" style={{ background: `linear-gradient(${team.primary_color}, ${team.secondary_color})` }} />
      <span className="flex items-center gap-2 ps-2">
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-xs font-extrabold"
          style={{ background: team.primary_color, color: inkOn(team.primary_color) }}
        >
          {team.short_name}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-display text-base font-bold text-white">{team.name}</span>
          <span className="block text-[11px] text-pp-mute">{t('fan.my.formation', { formation: `\u2066${team.formation}\u2069` })}</span>
        </span>
        {on && <Heart className="h-5 w-5 shrink-0" style={{ color: team.primary_color, fill: team.primary_color }} aria-hidden />}
      </span>
      {team.style && <span className="mt-2 block ps-2 text-xs leading-snug text-slate-300">{team.style}</span>}
    </button>
  );
};

// ---------- the numbers ----------

const NumberRow: React.FC<{ label: string; us: string; them: string; usColor: string; themColor: string; usShare: number }> = ({
  label,
  us,
  them,
  usColor,
  themColor,
  usShare,
}) => (
  <div className="rounded-xl border border-pp-line/60 bg-pp-deep/60 p-3">
    <div className="flex items-baseline justify-between gap-2">
      <span className="ltr-nums font-display text-2xl font-extrabold" style={{ color: usColor }}>
        {us}
      </span>
      <span className="text-[11px] font-semibold uppercase tracking-wider text-pp-mute">{label}</span>
      <span className="ltr-nums text-sm font-semibold text-slate-400">{them}</span>
    </div>
    <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-pp-night">
      <div style={{ width: `${Math.max(0, Math.min(100, usShare))}%`, background: usColor }} />
      <div className="flex-1" style={{ background: `${themColor}66` }} />
    </div>
  </div>
);

// ---------- single metric ----------

const MetricDisplay: React.FC<{ metric: FocusMetric; match: MatchViewState }> = ({ metric, match }) => {
  const { t, num } = useI18n();
  const { teams, state, history } = match;
  const home = teams?.home ?? null;
  const away = teams?.away ?? null;
  const hc = home?.primary_color ?? '#60a5fa';
  const ac = away?.primary_color ?? '#f87171';
  const noData = <p className="py-4 text-center text-sm text-pp-mute">{t('fan.metric.noData')}</p>;
  const big = 'ltr-nums font-display text-5xl font-extrabold';
  const pair = (a: string, b: string) => (
    <div className="grid grid-cols-2 gap-3">
      {(
        [
          [home, a, hc],
          [away, b, ac],
        ] as const
      ).map(([team, v, c], i) => (
        <div key={i} className="rounded-xl bg-pp-deep/70 p-3 text-center">
          <p className="flex items-center justify-center gap-1.5 text-xs text-pp-mute">
            <TeamDot team={team} />
            {team?.short_name}
          </p>
          <p className={big} style={{ color: c }}>
            {v}
          </p>
        </div>
      ))}
    </div>
  );
  const trend = (sel: (h: MetricSample) => number[], opts: { zero?: boolean; min?: number; max?: number } = {}) => {
    const cols = [hc, ac];
    const width = history.length ? sel(history[0]).length : 0;
    const series = Array.from({ length: width }, (_, i) => ({ values: history.map((h) => sel(h)[i]), color: width === 1 ? '#ff3b2f' : cols[i] }));
    return <Sparkline series={series} label={t('fan.metric.trend', { metric: t(`metric.${metric}`) })} {...opts} />;
  };

  switch (metric) {
    case 'pressure':
      if (!state) return noData;
      return (
        <>
          {pair(num(state.home.pressure_index), num(state.away.pressure_index))}
          {trend((h) => [h.pressure_home, h.pressure_away], { min: 0, max: 100 })}
        </>
      );
    case 'xg':
      if (!state) return noData;
      return (
        <>
          {pair(num(state.xg_home, 2), num(state.xg_away, 2))}
          {trend((h) => [h.xg_home, h.xg_away], { min: 0 })}
        </>
      );
    case 'momentum': {
      if (!state) return noData;
      const m = state.momentum;
      const fav = m > 0 ? home : m < 0 ? away : null;
      return (
        <>
          <div className="rounded-xl bg-pp-deep/70 p-3 text-center">
            <p className={big} style={{ color: fav ? fav.primary_color : '#e2e8f0' }}>
              {m > 0 ? '+' : ''}
              {num(m)}
            </p>
            <p className="mt-1 text-sm font-semibold text-white">{fav ? t('fan.metric.favours', { team: fav.name }) : t('fan.metric.level')}</p>
            <p className="text-[11px] text-pp-mute">{t('fan.metric.scale', { team: home?.name ?? '' })}</p>
          </div>
          {trend((h) => [h.momentum], { zero: true, min: -100, max: 100 })}
        </>
      );
    }
    case 'top_speed': {
      const p = fastestPlayer(match.players);
      if (!p) return noData;
      const team = teamById(teams, p.team);
      return (
        <div className="rounded-xl bg-pp-deep/70 p-3 text-center" data-testid="metric-top-speed">
          <p className={big} style={{ color: team?.primary_color ?? '#ffd400' }}>
            {num(p.top_speed_kmh, 1)}
            <span className="ms-1 text-base font-semibold text-pp-mute">{t('unit.kmh')}</span>
          </p>
          <p className="mt-1 flex items-center justify-center gap-1.5 text-sm text-white">
            <TeamDot team={team} />
            {t('fan.metric.by', { name: playerName(teams, p.player_id) || p.player_id })}
          </p>
        </div>
      );
    }
    case 'pass_difficulty': {
      const e = latestPassDifficulty(match.events);
      if (!e || e.metrics.pass_difficulty == null) return noData;
      const team = teamById(teams, e.team);
      return (
        <div className="rounded-xl bg-pp-deep/70 p-3 text-center">
          <p className={big} style={{ color: team?.primary_color ?? '#ff9f1c' }}>
            {num(e.metrics.pass_difficulty)}
          </p>
          <p className="mt-1 flex flex-wrap items-center justify-center gap-1.5 text-sm text-white">
            <TeamDot team={team} />
            {t('fan.metric.by', { name: playerName(teams, e.player_id) || '–' })}
            <span className="ltr-nums text-xs text-pp-mute">{t('fan.metric.at', { clock: e.match_clock })}</span>
          </p>
        </div>
      );
    }
  }
};

// ---------- view ----------

export const MyMatch: React.FC<ViewProps> = ({ match, actions }) => {
  const { t, num } = useI18n();
  const { teams, state, profile } = match;
  const fav = profile.favourite_team;
  const side = favouriteSide(teams, fav);
  const us = side ? teams![side] : (teams?.home ?? null);
  const them = side ? teams![side === 'home' ? 'away' : 'home'] : (teams?.away ?? null);
  const themSide: Side = side === 'away' ? 'home' : 'away';
  const usSide: Side = side ?? 'home';
  const score = perspectiveScore(match.score, side);
  const focus = profile.focus_metric;

  const crewCards = useMemo(() => {
    const list = match.cards.filter((c) => c.slot !== 'metric_alert' && c.slot !== 'pitch_tag').reverse();
    const seen = new Set<string>();
    const unique = list.filter((c) => !seen.has(c.moment_id) && !!seen.add(c.moment_id)).slice(0, 12);
    if (!fav) return unique;
    return [...unique.filter((c) => isFavCard(c, fav)), ...unique.filter((c) => !isFavCard(c, fav))];
  }, [match.cards, fav]);

  const alerts = useMemo(() => match.cards.filter((c) => c.slot === 'metric_alert').reverse().slice(0, 6), [match.cards]);

  if (!teams || !us || !them) return <p className="p-6 text-center text-pp-mute">{t('common.loading')}</p>;

  const theme = side ? us.primary_color : '#ff3b2f';
  const share = (a: number, b: number) => (a + b > 0 ? (a / (a + b)) * 100 : 50);
  const nums = state
    ? [
        { label: t('fan.my.xg'), u: state[`xg_${usSide}`], th: state[`xg_${themSide}`], d: 2 },
        { label: t('fan.my.shots'), u: state[`shots_${usSide}`], th: state[`shots_${themSide}`], d: 0 },
        { label: t('fan.my.pressure'), u: state[usSide].pressure_index, th: state[themSide].pressure_index, d: 0 },
        { label: t('fan.my.possession'), u: state[usSide].possession_pct, th: state[themSide].possession_pct, d: 0, pct: true },
      ]
    : [];

  return (
    <div className="space-y-4" style={{ ['--fan-primary' as string]: theme }} data-favourite={fav ?? ''}>
      <section
        className="rounded-2xl border-2 p-4"
        style={{ borderColor: `${theme}aa`, background: `linear-gradient(135deg, ${theme}33, transparent 60%), #111a2e` }}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 font-display text-xl font-bold text-white">
            {side ? <Heart className="h-5 w-5" style={{ color: theme, fill: theme }} aria-hidden /> : <Info className="h-5 w-5 text-pp-mute" aria-hidden />}
            {side ? t('fan.my.yourClub', { name: us.name }) : t('fan.my.neutral')}
          </h2>
          <div className="flex items-center gap-3" aria-label={`${us.name} ${score.us ?? t('catchup.hiddenValue')}, ${them.name} ${score.them ?? t('catchup.hiddenValue')}`} data-testid="perspective-score">
            <span className="flex flex-col items-center text-[10px] uppercase text-pp-mute">
              <span className="font-bold text-white">{us.short_name}</span>
              {side && t('fan.my.us')}
            </span>
            <span className="flex items-center font-display text-4xl font-extrabold tabular-nums text-white">
              <span style={{ color: side ? theme : undefined }}><ScoreValue value={score.us} /></span>
              <span className="mx-1 text-pp-mute">–</span>
              <span><ScoreValue value={score.them} /></span>
            </span>
            <span className="flex flex-col items-center text-[10px] uppercase text-pp-mute">
              <span className="font-bold text-white">{them.short_name}</span>
              {side && t('fan.my.them')}
            </span>
            <span className="ltr-nums rounded-md bg-pp-night px-2 py-1 font-mono text-xs text-pp-signal">{match.clock}</span>
          </div>
        </div>
      </section>

      <Panel title={t('fan.my.pickClub')}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_auto]">
          {(['home', 'away'] as const).map((s) => (
            <ClubButton key={s} team={teams[s]} on={fav === teams[s].team_id} onPick={() => actions.setView({ favourite_team: teams[s].team_id })} />
          ))}
          <button
            type="button"
            aria-pressed={!fav}
            onClick={() => actions.setView({ favourite_team: null })}
            className={cx(
              'flex min-h-[48px] items-center justify-center gap-2 rounded-2xl border-2 px-4 text-sm font-bold sm:col-span-2 lg:col-span-1',
              !fav ? 'border-pp-pulse bg-pp-pulse/15 text-white' : 'border-pp-line bg-pp-deep text-pp-mute hover:text-white',
            )}
          >
            <HeartOff className="h-4 w-4" aria-hidden />
            {t('fan.my.noFavourite')}
          </button>
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="space-y-4 lg:col-span-7">
          <AskStudio match={match} actions={actions} compact />
          {state && (
            <Panel title={t('fan.my.numbers')}>
              <div className="mb-2 flex items-center justify-between text-[11px] font-semibold text-pp-mute">
                <span className="flex items-center gap-1.5">
                  <TeamDot team={us} />
                  {side ? t('fan.my.us') : us.short_name}
                </span>
                <span className="flex items-center gap-1.5">
                  {side ? t('fan.my.them') : them.short_name}
                  <TeamDot team={them} />
                </span>
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {nums.map((n) => (
                  <NumberRow
                    key={n.label}
                    label={n.label}
                    us={`${num(n.u, n.d)}${n.pct ? '%' : ''}`}
                    them={`${num(n.th, n.d)}${n.pct ? '%' : ''}`}
                    usColor={us.primary_color}
                    themColor={them.primary_color}
                    usShare={share(n.u, n.th)}
                  />
                ))}
              </div>
            </Panel>
          )}

          <Panel title={t('fan.metric.title')}>
            <Segmented
              label={t('fan.metric.pick')}
              value={focus ?? 'off'}
              onChange={(v) => actions.setView({ focus_metric: v === 'off' ? null : (v as FocusMetric) })}
              className="flex-wrap"
              options={[{ value: 'off', label: t('fan.metric.off') }, ...METRICS.map((m) => ({ value: m, label: t(`metric.${m}`) }))]}
            />
            <div className="mt-3">
              {focus ? (
                <>
                  <h3 className="mb-2 font-display text-sm font-bold text-white">{t(`metric.${focus}`)}</h3>
                  <MetricDisplay metric={focus} match={match} />
                  <p className="mt-3 flex items-center gap-1.5 text-[11px] text-pp-mute">
                    <BellRing className="h-3.5 w-3.5 text-pp-gold" aria-hidden />
                    {t('fan.metric.honest')}
                  </p>
                  <h3 className="mb-2 mt-3 text-[11px] font-bold uppercase tracking-wider text-pp-mute">{t('fan.metric.alerts')}</h3>
                  {alerts.length === 0 ? (
                    <p className="text-xs text-pp-mute">{t('fan.metric.noAlerts')}</p>
                  ) : (
                    <div className="space-y-2">
                      {alerts.map((c) => (
                        <CardItem key={c.card_id} card={c} />
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <p className="text-xs text-pp-mute">{t('fan.metric.offHint')}</p>
              )}
            </div>
          </Panel>
        </div>

        <Panel title={t('fan.my.crew')} className="lg:col-span-5" actions={fav ? <span className="text-[11px] text-pp-mute">{t('fan.my.crewHint')}</span> : undefined}>
          {crewCards.length === 0 ? (
            <p className="text-xs text-pp-mute">{t('fan.my.noCards')}</p>
          ) : (
            <div className="space-y-2">
              {crewCards.map((c) => {
                const mine = isFavCard(c, fav);
                return (
                  <CardItem
                    key={c.card_id}
                    card={c}
                    muted={!!fav && !mine}
                    highlight={fav && mine ? theme : null}
                    badge={fav && mine ? <Badge className="border-transparent" title={us.name}>{t('fan.my.yourSide')}</Badge> : null}
                  />
                );
              })}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
};
