import React, { useMemo, useState } from 'react';
import { Activity, Crosshair, Maximize2, Navigation, Search, UserCheck, Video, ZoomIn } from 'lucide-react';
import type { EventMetrics, MatchEvent, OverlayCard, PlayerStats, Teams } from '../api/contract';
import { Pitch2D } from '../components/Pitch2D';
import { Badge, Panel, Segmented, TeamDot, cx } from '../components/ui';
import { useI18n } from '../i18n';
import { activeCards } from '../state/matchStore';
import { playerById, shortName, type PlayerRef } from '../lib/teams';
import type { ViewProps } from './types';

const LINE_ORDER = { GK: 0, DEF: 1, MID: 2, FWD: 3 } as const;

/** The selected player, or the home side's first forward until the viewer picks someone. */
export function defaultFocusId(teams: Teams | null, chosen: string | null): string | null {
  if (!teams) return null;
  if (chosen && playerById(teams, chosen)) return chosen;
  const home = teams.home.players;
  return (home.find((p) => p.line === 'FWD') ?? home[0] ?? teams.away.players[0])?.player_id ?? null;
}

export const involves = (e: MatchEvent | null, id: string | null) =>
  !!e && !!id && (e.player_id === id || e.receiver_id === id);

// Evidence values as they arrive; numbers get two decimals at most for display.
export function EvidenceValue({ value, unit }: { value: string | number | boolean; unit: string | null }) {
  const { num } = useI18n();
  const shown = typeof value === 'number' ? num(value, Number.isInteger(value) ? 0 : 2) : String(value);
  return (
    <span className="ltr-nums font-mono text-white">
      {shown}
      {unit ? ` ${unit}` : ''}
    </span>
  );
}

/** One crew card: headline, body, kind, evidence and who wrote it. */
export const CardItem: React.FC<{ card: OverlayCard; muted?: boolean; highlight?: string | null; badge?: React.ReactNode }> = ({
  card,
  muted,
  highlight,
  badge,
}) => {
  const { t } = useI18n();
  return (
    <article
      dir={card.rtl ? 'rtl' : undefined}
      className={cx('rounded-xl border bg-pp-deep/70 p-3 transition', muted ? 'border-pp-line/50 opacity-60' : 'border-pp-line')}
      style={highlight ? { borderColor: highlight, borderInlineStartWidth: 4 } : undefined}
    >
      <div className="mb-1 flex flex-wrap items-center gap-1.5">
        <Badge tone="pulse">{t(`kind.${card.kind}`)}</Badge>
        <span className="ltr-nums text-[11px] text-pp-mute">{fmtClock(card.show_at_s)}</span>
        {badge}
        <Badge tone={card.produced_by === 'ai' ? 'signal' : 'mute'} className="ms-auto" title={card.fallback_reason ?? undefined}>
          {t(`produced.${card.produced_by}`)}
        </Badge>
      </div>
      <h3 className="font-display text-sm font-bold text-white">{card.headline}</h3>
      {card.body && <p className="mt-1 text-xs leading-relaxed text-slate-300">{card.body}</p>}
      {card.why && <p className="mt-1 text-[11px] italic text-pp-mute">{card.why}</p>}
      {card.evidence.length > 0 && (
        <dl className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px]" aria-label={t('evidence.title')}>
          {card.evidence.map((ev, i) => (
            <div key={`${ev.label}-${i}`} className="flex items-center gap-1">
              <dt className="text-pp-mute">{ev.label.replace(/_/g, ' ')}</dt>
              <dd>
                <EvidenceValue value={ev.value} unit={ev.unit} />
              </dd>
            </div>
          ))}
        </dl>
      )}
      {card.fallback_reason && (
        <p className="mt-1 text-[10px] text-pp-mute">{t('fan.follow.fallback', { reason: card.fallback_reason })}</p>
      )}
    </article>
  );
};

export const fmtClock = (s: number) => {
  const m = Math.floor(Math.max(0, s) / 60);
  const sec = Math.floor(Math.max(0, s) % 60);
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
};

const METRIC_KEYS: { key: keyof EventMetrics; digits: number; unit?: string }[] = [
  { key: 'player_speed_kmh', digits: 1, unit: 'unit.kmh' },
  { key: 'ball_speed_kmh', digits: 0, unit: 'unit.kmh' },
  { key: 'pass_distance_m', digits: 1, unit: 'unit.m' },
  { key: 'pass_difficulty', digits: 0 },
  { key: 'chance_quality', digits: 2 },
  { key: 'distance_to_goal_m', digits: 1, unit: 'unit.m' },
];

/** Metrics present on an event, ready to show. */
export function EventMetricChips({ e }: { e: MatchEvent }) {
  const { t, num } = useI18n();
  const chips: React.ReactNode[] = [];
  for (const m of METRIC_KEYS) {
    const v = e.metrics[m.key];
    if (typeof v === 'number') {
      chips.push(
        <span key={m.key} className="rounded-md bg-pp-night px-1.5 py-0.5">
          <span className="text-pp-mute">{t(`fan.mx.${m.key}`)} </span>
          <span className="ltr-nums font-mono text-white">
            {num(v, m.digits)}
            {m.unit ? ` ${t(m.unit)}` : ''}
          </span>
        </span>,
      );
    }
  }
  const flags: [boolean, string][] = [
    [e.metrics.progressive, 'event.progressive'],
    [e.metrics.sprint, 'fan.mx.sprint'],
    [e.metrics.fast_shot, 'fan.mx.fast_shot'],
    [e.under_pressure, 'fan.mx.under_pressure'],
  ];
  for (const [on, key] of flags) if (on) chips.push(<Badge key={key} tone="gold">{t(key)}</Badge>);
  if (e.metrics.pitch_zone) chips.push(<span key="zone" className="text-pp-mute">{t(`zone.${e.metrics.pitch_zone}`)}</span>);
  return <div className="flex flex-wrap items-center gap-1.5 text-[11px]">{chips}</div>;
}

const StatCard: React.FC<{ stats: PlayerStats | undefined }> = ({ stats }) => {
  const { t, num } = useI18n();
  if (!stats || stats.touches === 0) return <p className="py-6 text-center text-sm text-pp-mute">{t('fan.follow.noTouches')}</p>;
  const rows: [string, string][] = [
    ['fan.stat.touches', num(stats.touches)],
    ['fan.stat.passes', `${num(stats.passes_completed)}/${num(stats.passes)}`],
    ['fan.stat.accuracy', `${num(stats.pass_accuracy)}%`],
    ['fan.stat.keyPasses', num(stats.key_passes)],
    ['fan.stat.shots', num(stats.shots)],
    ['fan.stat.goals', num(stats.goals)],
    ['fan.stat.assists', num(stats.assists)],
    ['fan.stat.xg', num(stats.xg, 2)],
    ['fan.stat.xa', num(stats.xa, 2)],
    ['fan.stat.tackles', num(stats.tackles_won)],
    ['fan.stat.interceptions', num(stats.interceptions)],
    ['fan.stat.topSpeed', `${num(stats.top_speed_kmh, 1)} ${t('unit.kmh')}`],
    ['fan.stat.sprints', num(stats.sprints)],
    ['fan.stat.distance', `${num(stats.distance_km, 2)} ${t('unit.km')}`],
  ];
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {rows.map(([k, v]) => (
        <div key={k} className={cx('rounded-xl border border-pp-line/60 bg-pp-deep/60 p-2.5', k === 'fan.stat.distance' && 'col-span-2 sm:col-span-3')}>
          <dt className="text-[11px] text-pp-mute">{t(k)}</dt>
          <dd className="ltr-nums font-display text-lg font-bold text-white" data-stat={k}>
            {v}
          </dd>
        </div>
      ))}
    </dl>
  );
};

const PlayerPicker: React.FC<{ teams: Teams; selected: string | null; onPick: (id: string) => void }> = ({ teams, selected, onPick }) => {
  const { t } = useI18n();
  const [q, setQ] = useState('');
  const needle = q.trim().toLowerCase();
  const groups = (['home', 'away'] as const).map((side) => {
    const team = teams[side];
    const players = [...team.players]
      .sort((a, b) => LINE_ORDER[a.line] - LINE_ORDER[b.line] || a.number - b.number)
      .filter(
        (p) =>
          !needle ||
          p.name.toLowerCase().includes(needle) ||
          String(p.number) === needle ||
          p.position.toLowerCase().includes(needle),
      );
    return { side, team, players };
  });
  const none = groups.every((g) => g.players.length === 0);
  return (
    <div>
      <label className="relative block">
        <span className="sr-only">{t('fan.follow.filter')}</span>
        <Search className="pointer-events-none absolute start-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-pp-mute" aria-hidden />
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t('fan.follow.filterPlaceholder')}
          className="min-h-[40px] w-full rounded-xl border border-pp-line bg-pp-night ps-8 pe-3 text-sm text-white placeholder:text-pp-mute focus:border-pp-pulse focus:outline-none"
        />
      </label>
      {none && <p className="mt-3 text-xs text-pp-mute">{t('fan.follow.noMatch')}</p>}
      <div className="mt-3 max-h-[22rem] space-y-3 overflow-y-auto pe-1 lg:max-h-[calc(100vh-12rem)]">
        {groups.map(
          ({ side, team, players }) =>
            players.length > 0 && (
              <div key={side} role="group" aria-label={team.name}>
                <h3 className="mb-1.5 flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-pp-mute">
                  <TeamDot team={team} />
                  {team.name}
                </h3>
                <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-1">
                  {players.map((p) => {
                    const on = p.player_id === selected;
                    return (
                      <li key={p.player_id}>
                        <button
                          type="button"
                          aria-pressed={on}
                          onClick={() => onPick(p.player_id)}
                          className={cx(
                            'flex min-h-[36px] w-full items-center gap-2 rounded-lg border px-2 text-start text-xs transition',
                            on ? 'border-pp-pulse bg-pp-pulse/15 text-white' : 'border-transparent bg-pp-deep/60 text-slate-300 hover:border-pp-line',
                          )}
                        >
                          <span
                            className="ltr-nums flex h-6 w-7 shrink-0 items-center justify-center rounded-md text-[11px] font-bold"
                            style={{ background: team.primary_color, color: team.secondary_color }}
                          >
                            {p.number}
                          </span>
                          <span className="min-w-0 flex-1 truncate font-semibold">{p.name}</span>
                          <span className="shrink-0 font-mono text-[10px] text-pp-mute">{p.position}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ),
        )}
      </div>
    </div>
  );
};

const BigTile: React.FC<{ icon: React.ReactNode; label: string; value: string; unit: string; color: string }> = ({ icon, label, value, unit, color }) => (
  <div className="rounded-xl border border-pp-line bg-pp-deep/70 p-3">
    <div className="mb-1 flex items-center justify-between text-[11px] text-pp-mute">
      <span>{label}</span>
      {icon}
    </div>
    <div className="flex items-baseline gap-1">
      <span className="ltr-nums font-mono text-3xl font-extrabold" style={{ color }}>
        {value}
      </span>
      <span className="text-xs text-pp-mute">{unit}</span>
    </div>
  </div>
);

export const PlayerFocus: React.FC<ViewProps> = ({ match, actions }) => {
  const { t, num, dir } = useI18n();
  const [zoom, setZoom] = useState(true);
  const { teams, profile } = match;
  const focusId = defaultFocusId(teams, profile.focus_player_id);
  const player: PlayerRef | null = playerById(teams, focusId);
  const stats = focusId ? match.players[focusId] : undefined;
  const camOn = profile.persona === 'player_spotlight';
  const clockS = match.state?.clock_s ?? match.playback.clock_s;

  const byPlayer = useMemo(() => match.events.filter((e) => e.player_id === focusId), [match.events, focusId]);
  const latest = byPlayer[byPlayer.length - 1] ?? null;
  const moments = useMemo(() => {
    const seen = new Set<string>();
    return [...match.cards]
      .reverse()
      .filter((c) => focusId && c.player_ids.includes(focusId) && c.slot !== 'metric_alert' && !seen.has(c.moment_id) && seen.add(c.moment_id))
      .slice(0, 8);
  }, [match.cards, focusId]);

  if (!teams || !player || !focusId) return <p className="p-6 text-center text-pp-mute">{t('common.loading')}</p>;

  const pick = (id: string) => actions.setView({ focus_player_id: id });
  const toggleCam = () =>
    actions.setView(camOn ? { persona: 'casual' } : { persona: 'player_spotlight', focus_player_id: focusId });
  const pitchEvent = involves(match.lastEvent, focusId) ? match.lastEvent : null;
  const color = player.team.primary_color;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
      <Panel title={t('fan.follow.pick')} className="order-2 self-start lg:sticky lg:top-4 lg:order-1 lg:col-span-4">
        <PlayerPicker teams={teams} selected={profile.focus_player_id ? focusId : null} onPick={pick} />
      </Panel>

      <div className="order-1 space-y-4 lg:order-2 lg:col-span-8">
        <section
          className="rounded-2xl border bg-pp-panel p-4"
          style={{ borderColor: `${color}88` }}
          aria-label={player.name}
        >
          <div className="flex flex-wrap items-center gap-3">
            <div
              className="ltr-nums flex h-14 w-14 shrink-0 items-center justify-center rounded-xl font-display text-2xl font-extrabold shadow-inner"
              style={{ background: color, color: player.team.secondary_color }}
            >
              {player.number}
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="flex items-center gap-2 font-display text-xl font-bold text-white">
                <UserCheck className="h-5 w-5 shrink-0 text-pp-signal" aria-hidden />
                <span className="break-words">{player.name}</span>
              </h2>
              <p className="flex items-center gap-2 text-xs text-pp-mute">
                <span className="font-semibold text-slate-300">{player.position}</span>
                <span aria-hidden>·</span>
                <TeamDot team={player.team} />
                <span>{player.team.name}</span>
              </p>
              {!profile.focus_player_id && <p className="mt-1 text-[11px] text-pp-gold">{t('fan.follow.suggested')}</p>}
            </div>
            <button
              type="button"
              aria-pressed={camOn}
              onClick={toggleCam}
              title={t('fan.follow.playerCamHint')}
              className={cx(
                'flex min-h-[40px] items-center gap-2 rounded-xl border px-3 text-xs font-bold transition',
                camOn ? 'border-pp-pulse bg-pp-pulse text-white' : 'border-pp-line bg-pp-night text-slate-200 hover:border-pp-pulse',
              )}
            >
              <Video className="h-4 w-4" aria-hidden />
              {t('fan.follow.playerCam')}
            </button>
          </div>
          {camOn && <p className="mt-2 text-[11px] text-pp-pulseSoft">{t('fan.follow.playerCamHint')}</p>}
          <label className="mt-3 block lg:hidden">
            <span className="sr-only">{t('fan.follow.pick')}</span>
            <select
              value={focusId}
              onChange={(e) => pick(e.target.value)}
              className="min-h-[40px] w-full rounded-xl border border-pp-line bg-pp-night px-2 text-sm text-white"
            >
              {(['home', 'away'] as const).map((s) => (
                <optgroup key={s} label={teams[s].name}>
                  {teams[s].players.map((p) => (
                    <option key={p.player_id} value={p.player_id}>
                      {`${p.number} · ${p.name} (${p.position})`}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
        </section>

        <Panel
          title={t('fan.follow.pitchView')}
          actions={
            <Segmented
              label={t('fan.follow.pitchView')}
              value={zoom ? 'zoom' : 'full'}
              onChange={(v) => setZoom(v === 'zoom')}
              options={[
                { value: 'zoom', label: <span className="flex items-center gap-1"><ZoomIn className="h-3.5 w-3.5" aria-hidden />{t('fan.follow.zoom')}</span> },
                { value: 'full', label: <span className="flex items-center gap-1"><Maximize2 className="h-3.5 w-3.5" aria-hidden />{t('fan.follow.full')}</span> },
              ]}
            />
          }
        >
          <div dir="ltr" className="relative">
            {!match.positions[focusId] && (
              <p
                dir={dir}
                className="absolute inset-x-0 top-3 z-20 mx-auto w-fit rounded-full border border-pp-line bg-pp-deep/90 px-3 py-1 text-xs text-pp-mute"
              >
                {t('fan.follow.waitingTouch', { name: player ? shortName(player.name) : '' })}
              </p>
            )}
            <Pitch2D
              teams={teams}
              event={pitchEvent}
              positions={match.positions}
              trails={match.trails}
              focusPlayerId={focusId}
              zoomOnFocus={zoom}
              showTags
              pitchTags={activeCards(match.cards, clockS, 'pitch_tag').filter((c) => c.player_ids.includes(focusId))}
            />
          </div>
        </Panel>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <BigTile
            icon={<Activity className="h-4 w-4 text-pp-signal" aria-hidden />}
            label={t('fan.stat.topSpeed')}
            value={stats ? num(stats.top_speed_kmh, 1) : '–'}
            unit={t('unit.kmh')}
            color="#ffd400"
          />
          <BigTile
            icon={<Navigation className="h-4 w-4 text-pp-gold" aria-hidden />}
            label={t('fan.stat.distance')}
            value={stats ? num(stats.distance_km, 2) : '–'}
            unit={t('unit.km')}
            color="#ff9f1c"
          />
          <div className="rounded-xl border border-pp-line bg-pp-deep/70 p-3">
            <div className="mb-1 flex items-center justify-between text-[11px] text-pp-mute">
              <span>{t('fan.follow.latest')}</span>
              <Crosshair className="h-4 w-4 text-pp-pulse" aria-hidden />
            </div>
            {latest ? (
              <>
                <p className="flex items-baseline gap-2">
                  <span className="font-display text-lg font-bold text-white">{t(`event.${latest.type}`)}</span>
                  <span className="ltr-nums text-xs text-pp-mute">{latest.match_clock}</span>
                </p>
                <EventMetricChips e={latest} />
              </>
            ) : (
              <p className="text-sm text-pp-mute">{t('fan.follow.noAction')}</p>
            )}
          </div>
        </div>

        <Panel title={t('fan.follow.stats')}>
          <StatCard stats={stats} />
        </Panel>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Panel title={t('fan.follow.moments')}>
            {moments.length === 0 ? (
              <p className="text-xs text-pp-mute">{t('fan.follow.noMoments')}</p>
            ) : (
              <div className="space-y-2">
                {moments.map((c) => (
                  <CardItem key={c.card_id} card={c} />
                ))}
              </div>
            )}
          </Panel>
          <Panel title={t('fan.follow.recent')}>
            {byPlayer.length === 0 ? (
              <p className="text-xs text-pp-mute">{t('fan.follow.noAction')}</p>
            ) : (
              <ol className="space-y-1.5">
                {byPlayer
                  .slice(-10)
                  .reverse()
                  .map((e) => (
                    <li key={e.event_id} className="rounded-lg border border-pp-line/60 bg-pp-deep/60 p-2">
                      <div className="mb-1 flex items-center gap-2 text-xs">
                        <span className="ltr-nums font-mono font-bold text-pp-signal">{e.match_clock}</span>
                        <span className="font-semibold text-white">{t(`event.${e.type}`)}</span>
                      </div>
                      <EventMetricChips e={e} />
                    </li>
                  ))}
              </ol>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
};
