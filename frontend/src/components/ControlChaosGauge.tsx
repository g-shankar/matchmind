import React from 'react';
import { Activity, Flame, Gauge, ShieldCheck } from 'lucide-react';
import type { TeamInfo } from '../api/contract';
import { useI18n } from '../i18n';
import type { ViewProps } from '../views/types';
import { Badge, Panel, TeamDot } from './ui';
import { tOr } from './NarrativeFeed';

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

// Arc from chaos (left, -1) to control (right, +1); stays left-to-right in every language.
const Dial: React.FC<{ value: number; label: string }> = ({ value, label }) => {
  const { t } = useI18n();
  const angle = Math.PI * (1 - (clamp(value, -1, 1) + 1) / 2); // pi .. 0
  const nx = 60 + 44 * Math.cos(angle);
  const ny = 60 - 44 * Math.sin(angle);
  return (
    <div dir="ltr" className="relative mx-auto w-full max-w-[220px]">
      <svg viewBox="0 0 120 70" role="img" aria-label={label} className="w-full">
        <defs>
          <linearGradient id="cc-arc" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#ff3b2f" />
            <stop offset="50%" stopColor="#ff9f1c" />
            <stop offset="100%" stopColor="#f2efe8" />
          </linearGradient>
        </defs>
        <path d="M10 60 A50 50 0 0 1 110 60" fill="none" stroke="#24324f" strokeWidth="10" strokeLinecap="round" />
        <path d="M10 60 A50 50 0 0 1 110 60" fill="none" stroke="url(#cc-arc)" strokeWidth="6" strokeLinecap="round" />
        <line x1="60" y1="60" x2={nx} y2={ny} stroke="#fff" strokeWidth="2.5" strokeLinecap="round" style={{ transition: 'all .7s ease-out' }} />
        <circle cx="60" cy="60" r="4.5" fill="#fff" />
      </svg>
      <div className="mt-1 flex justify-between text-[10px] font-bold uppercase tracking-wider">
        <span className="flex items-center gap-1 text-pp-pulseSoft">
          <Flame className="h-3 w-3" aria-hidden />
          {t('studio.gauge.chaos')}
        </span>
        <span className="flex items-center gap-1 text-pp-signal">
          {t('studio.gauge.control')}
          <ShieldCheck className="h-3 w-3" aria-hidden />
        </span>
      </div>
    </div>
  );
};

const Row: React.FC<{ label: string; hint: string; children: React.ReactNode }> = ({ label, hint, children }) => (
  <div title={hint}>
    <div className="mb-1 flex items-center justify-between gap-2 text-[11px] font-semibold uppercase tracking-wider text-pp-mute">
      <span className="cursor-help underline decoration-dotted decoration-pp-line underline-offset-4">{label}</span>
    </div>
    {children}
  </div>
);

const PairStat: React.FC<{ home: TeamInfo; away: TeamInfo; homeValue: string; awayValue: string; label: string; hint: string }> = ({
  home,
  away,
  homeValue,
  awayValue,
  label,
  hint,
}) => (
  <div title={hint} className="rounded-lg border border-pp-line/70 bg-pp-deep/70 p-2 text-center">
    <div className="cursor-help text-[10px] font-semibold uppercase tracking-wider text-pp-mute">{label}</div>
    <div className="mt-1 flex items-center justify-center gap-2 font-display text-base font-bold text-white">
      <span className="flex items-center gap-1">
        <TeamDot team={home} size={7} />
        <span className="ltr-nums">{homeValue}</span>
      </span>
      <span className="text-pp-line">|</span>
      <span className="flex items-center gap-1">
        <span className="ltr-nums">{awayValue}</span>
        <TeamDot team={away} size={7} />
      </span>
    </div>
  </div>
);

export const ControlChaosGauge: React.FC<ViewProps> = ({ match }) => {
  const { t, num } = useI18n();
  const { state, teams } = match;

  if (!state || !teams) {
    return (
      <Panel title={t('studio.gauge.title')}>
        <p className="py-6 text-center text-sm text-pp-mute">{t('common.waiting')}</p>
      </Panel>
    );
  }

  const { home, away } = teams;
  const homePos = clamp(state.home.possession_pct, 0, 100);
  const awayPos = clamp(state.away.possession_pct, 0, 100);
  const momentum = clamp(state.momentum, -100, 100);
  const tempo = tOr(t, `tempo.${state.tempo}`, state.tempo);
  const cc = state.control_chaos;

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <Gauge className="h-4 w-4 text-pp-signal" aria-hidden />
          {t('studio.gauge.title')}
        </span>
      }
      actions={
        <Badge tone="signal" title={t('studio.gauge.tempoHint')}>
          <Activity className="h-3 w-3" aria-hidden />
          <span className="sr-only">{t('studio.gauge.tempo')}: </span>
          {tempo}
        </Badge>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div title={t('studio.gauge.dialHint')}>
          <Dial value={cc} label={t('studio.gauge.dialLabel', { value: num(cc, 2) })} />
          <p className="ltr-nums mt-1 text-center font-display text-2xl font-bold text-white">
            {cc > 0 ? '+' : ''}
            {num(cc, 2)}
          </p>
        </div>

        <div className="space-y-3">
          <Row label={t('studio.gauge.possession')} hint={t('studio.gauge.possessionHint')}>
            <div className="mb-1 flex justify-between text-xs font-bold text-white">
              <span className="flex items-center gap-1.5">
                <TeamDot team={home} size={8} />
                {home.short_name} <span className="ltr-nums">{num(homePos)}%</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="ltr-nums">{num(awayPos)}%</span> {away.short_name}
                <TeamDot team={away} size={8} />
              </span>
            </div>
            <div className="flex h-2.5 overflow-hidden rounded-full bg-pp-deep">
              <div className="transition-all duration-700" style={{ width: `${homePos}%`, background: home.primary_color }} />
              <div className="transition-all duration-700" style={{ width: `${awayPos}%`, background: away.primary_color }} />
            </div>
          </Row>

          <Row label={t('studio.gauge.momentum')} hint={t('studio.gauge.momentumHint')}>
            <div className="flex items-center gap-2">
              <span className="w-10 text-[11px] font-bold text-white">{home.short_name}</span>
              <div
                className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-pp-deep"
                role="meter"
                aria-valuemin={-100}
                aria-valuemax={100}
                aria-valuenow={state.momentum}
                aria-label={t('studio.gauge.momentum')}
              >
                <span className="absolute inset-y-0 w-px bg-pp-mute/60" style={{ insetInlineStart: '50%' }} />
                <div
                  className="absolute inset-y-0 transition-all duration-700"
                  style={{
                    width: `${Math.abs(momentum) / 2}%`,
                    background: momentum >= 0 ? home.primary_color : away.primary_color,
                    ...(momentum >= 0 ? { insetInlineEnd: '50%' } : { insetInlineStart: '50%' }),
                  }}
                />
              </div>
              <span className="w-10 text-end text-[11px] font-bold text-white">{away.short_name}</span>
              <span className="ltr-nums w-10 text-end text-xs font-bold text-pp-signal">
                {momentum > 0 ? '+' : ''}
                {num(state.momentum)}
              </span>
            </div>
          </Row>

          <Row label={t('studio.gauge.pressure')} hint={t('studio.gauge.pressureHint')}>
            {([home, away] as const).map((tm, i) => {
              const v = clamp(i === 0 ? state.home.pressure_index : state.away.pressure_index, 0, 100);
              return (
                <div key={tm.team_id} className="mb-1 flex items-center gap-2 text-[11px]">
                  <span className="w-10 font-bold text-white">{tm.short_name}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-pp-deep">
                    <div className="h-full transition-all duration-700" style={{ width: `${v}%`, background: tm.primary_color }} />
                  </div>
                  <span className="ltr-nums w-8 text-end font-bold text-slate-200">{num(v)}</span>
                </div>
              );
            })}
          </Row>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <PairStat home={home} away={away} homeValue={num(state.xg_home, 2)} awayValue={num(state.xg_away, 2)} label={t('studio.gauge.xg')} hint={t('studio.gauge.xgHint')} />
        <PairStat home={home} away={away} homeValue={num(state.shots_home)} awayValue={num(state.shots_away)} label={t('studio.gauge.shots')} hint={t('studio.gauge.shotsHint')} />
        <div title={t('studio.gauge.tempoHint')} className="rounded-lg border border-pp-line/70 bg-pp-deep/70 p-2 text-center">
          <div className="cursor-help text-[10px] font-semibold uppercase tracking-wider text-pp-mute">{t('studio.gauge.tempo')}</div>
          <div className="mt-1 font-display text-base font-bold text-pp-signal">{tempo}</div>
        </div>
        <div title={t('studio.gauge.epmHint')} className="rounded-lg border border-pp-line/70 bg-pp-deep/70 p-2 text-center">
          <div className="cursor-help text-[10px] font-semibold uppercase tracking-wider text-pp-mute">{t('studio.gauge.epm')}</div>
          <div className="ltr-nums mt-1 font-display text-base font-bold text-white">{num(state.events_per_min, 1)}</div>
        </div>
      </div>
    </Panel>
  );
};
