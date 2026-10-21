import React, { useEffect, useState } from 'react';
import { FileText, Pause, Play, RotateCcw, X } from 'lucide-react';
import type { Language, OverlayCard, PersonaType, SpeedMultiplier } from './api/contract';
import { I18nProvider, UI_LANGUAGES, useI18n } from './i18n';
import { useMatch } from './state/useMatch';
import { activeCards } from './state/matchStore';
import type { ViewProps } from './views/types';
import { Badge, Logo, Segmented, cx } from './components/ui';
import { Pitch2D } from './components/Pitch2D';
import { ReplayCard } from './components/ReplayCard';
import { ControlChaosGauge } from './components/ControlChaosGauge';
import { NarrativeFeed } from './components/NarrativeFeed';
import { MomentsList } from './components/MomentsList';
import { BroadcastOverlay } from './components/BroadcastOverlay';
import { RecapModal } from './components/RecapModal';
import { SplitView } from './views/SplitView';
import { PlayerFocus } from './views/PlayerFocus';
import { MyMatch } from './views/MyMatch';

type ViewMode = 'studio' | 'overlay' | 'split' | 'follow' | 'fan';
const VIEWS: ViewMode[] = ['studio', 'overlay', 'split', 'follow', 'fan'];
const PERSONAS: PersonaType[] = ['casual', 'tactical', 'fantasy'];
const SPEEDS: SpeedMultiplier[] = [1, 10, 60];

const viewFromHash = (): ViewMode => {
  const v = window.location.hash.replace('#', '') as ViewMode;
  return VIEWS.includes(v) ? v : 'studio';
};

export const App: React.FC = () => {
  const { state, actions } = useMatch();
  return (
    <I18nProvider lang={state.profile.language}>
      <Shell match={state} actions={actions} />
    </I18nProvider>
  );
};

const Shell: React.FC<ViewProps> = ({ match, actions }) => {
  const { t, dir, num } = useI18n();
  const [view, setView] = useState<ViewMode>(viewFromHash);
  const [replay, setReplay] = useState<OverlayCard | null>(null);
  const [recapOpen, setRecapOpen] = useState(false);
  const [recapLoading, setRecapLoading] = useState(false);

  useEffect(() => {
    const onHash = () => setView(viewFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    if (match.recap) setRecapOpen(true);
  }, [match.recap]);

  const goTo = (v: ViewMode) => {
    window.location.hash = v;
    setView(v);
  };

  // A replay opened on one screen does not follow the viewer to the next.
  useEffect(() => setReplay(null), [view]);

  const openRecap = async () => {
    setRecapOpen(true);
    setRecapLoading(true);
    await actions.loadRecap();
    setRecapLoading(false);
  };

  const { profile, playback, teams } = match;
  const clockS = playback.clock_s;
  const liveReplay = activeCards(match.cards, clockS, 'full_screen').find((c) => c.replay);

  return (
    <div dir={dir} className="flex min-h-screen flex-col bg-pp-night text-slate-100">
      <header className="sticky top-0 z-40 border-b border-pp-line/70 bg-pp-deep/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-3">
            <Logo />
            <div>
              <h1 className="font-display text-xl font-bold tracking-wide text-white">
                Pitch<span className="text-pp-pulse">Pulse</span>
              </h1>
              <p className="hidden text-[11px] text-pp-mute sm:block">{t('app.tagline')}</p>
            </div>
            <ConnectionBadge status={match.status} />
            {match.crew && (
              <Badge tone={match.crew.mode === 'ai' ? 'signal' : 'mute'} title={match.crew.mode === 'template' ? t('crew.templateHint') : undefined}>
                {t(match.crew.mode === 'ai' ? 'crew.ai' : 'crew.template')}
              </Badge>
            )}
            {match.autoEventing && (
              <Badge tone="signal" className="hidden md:inline-flex" title={t('auto.label')}>
                {t('auto.label')} ·{' '}
                <span className="ltr-nums">
                  {t('auto.summary', {
                    pct: num(match.autoEventing.passes_detected_pct, 1),
                    mae: num(match.autoEventing.speed_mae_kmh, 1),
                  })}
                </span>
              </Badge>
            )}
          </div>

          <nav aria-label="Views" className="flex max-w-full items-center gap-1 overflow-x-auto rounded-xl border border-pp-line bg-pp-night p-1">
            {VIEWS.map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => goTo(v)}
                aria-current={view === v ? 'page' : undefined}
                className={cx(
                  'min-h-[34px] whitespace-nowrap rounded-lg px-3 text-xs font-bold transition',
                  view === v ? 'bg-pp-raised text-white ring-1 ring-pp-pulse/60' : 'text-pp-mute hover:text-white',
                )}
              >
                {t(`view.${v}`)}
              </button>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={actions.togglePause}
              disabled={playback.ended}
              aria-label={playback.is_running ? t('play.pause') : t('play.play')}
              title={playback.is_running ? t('play.pause') : t('play.play')}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-pp-line bg-pp-panel text-white hover:border-pp-pulse disabled:opacity-40"
            >
              {playback.is_running ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
            <Segmented
              label={t('play.speed')}
              value={playback.speed_multiplier}
              onChange={(s) => actions.setSpeed(s)}
              options={SPEEDS.map((s) => ({ value: s, label: <span className="ltr-nums">{s}x</span> }))}
            />
            <button
              type="button"
              onClick={actions.reset}
              aria-label={t('play.reset')}
              title={t('play.reset')}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-pp-line bg-pp-panel text-pp-mute hover:text-white"
            >
              <RotateCcw className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={openRecap}
              className="flex h-9 items-center gap-1.5 rounded-lg bg-pp-pulse px-3 text-xs font-bold text-white hover:bg-pp-pulse/85"
            >
              <FileText className="h-4 w-4" />
              {t('play.recap')}
            </button>
          </div>
        </div>

        <div className="border-t border-pp-line/50 bg-pp-night/60">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-2">
            <div className="flex items-center gap-2 text-xs text-pp-mute">
              <span className="font-semibold">{t('persona.label')}</span>
              <Segmented
                label={t('persona.label')}
                value={profile.persona === 'player_spotlight' ? 'casual' : profile.persona}
                onChange={(persona) => actions.setView({ persona })}
                options={PERSONAS.map((p) => ({ value: p, label: t(`persona.${p}`) }))}
              />
            </div>
            <Scoreline match={match} />
            <div className="flex items-center gap-2 text-xs text-pp-mute">
              <span className="font-semibold">{t('lang.label')}</span>
              <Segmented
                label={t('lang.label')}
                value={profile.language}
                onChange={(language: Language) => actions.setView({ language })}
                options={UI_LANGUAGES.map((l) => ({ value: l as Language, label: t(`lang.${l}`) }))}
              />
            </div>
          </div>
        </div>
      </header>

      {match.status === 'demo' && (
        <div className="border-b border-pp-gold/30 bg-pp-gold/10 px-4 py-1.5 text-center text-xs text-pp-gold">
          {t('conn.demoHint')}
        </div>
      )}

      <main className="mx-auto w-full max-w-7xl flex-1 p-4">
        {!teams ? (
          <div className="flex h-64 items-center justify-center text-pp-mute">{t('common.loading')}</div>
        ) : (
          <>
            {view === 'studio' && (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
                <div className="space-y-4 lg:col-span-7">
                  {liveReplay ? (
                    <ReplayCard card={liveReplay} teams={teams} />
                  ) : (
                    <Pitch2D
                      teams={teams}
                      event={match.lastEvent}
                      recentEvents={match.events.slice(-6)}
                      positions={match.positions}
                      showTags
                      pitchTags={activeCards(match.cards, clockS, 'pitch_tag')}
                    />
                  )}
                  <ControlChaosGauge match={match} actions={actions} />
                  <MomentsList match={match} actions={actions} />
                </div>
                <div className="lg:col-span-5">
                  <NarrativeFeed match={match} actions={actions} onOpenReplay={setReplay} />
                </div>
              </div>
            )}
            {view === 'overlay' && <BroadcastOverlay match={match} actions={actions} />}
            {view === 'split' && <SplitView match={match} actions={actions} />}
            {view === 'follow' && <PlayerFocus match={match} actions={actions} />}
            {view === 'fan' && <MyMatch match={match} actions={actions} />}
          </>
        )}
      </main>

      {replay && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setReplay(null)}>
          <div className="w-full max-w-4xl" onClick={(e) => e.stopPropagation()}>
            <ReplayCard card={replay} teams={teams} onClose={() => setReplay(null)} />
          </div>
        </div>
      )}

      <RecapModal open={recapOpen} onClose={() => setRecapOpen(false)} recap={match.recap} loading={recapLoading} teams={teams} />

      {match.error && (
        <div role="alert" className="fixed bottom-4 start-4 end-4 z-50 mx-auto flex max-w-md items-center justify-between gap-3 rounded-xl border border-pp-pulse/50 bg-pp-panel px-4 py-3 text-sm shadow-xl">
          <span>{match.error}</span>
          <button type="button" onClick={actions.clearError} aria-label={t('common.close')} className="text-pp-mute hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
};

const ConnectionBadge: React.FC<{ status: ViewProps['match']['status'] }> = ({ status }) => {
  const { t } = useI18n();
  if (status === 'live') {
    return (
      <Badge tone="pulse">
        <span className="h-2 w-2 animate-heartbeat rounded-full bg-pp-pulse" />
        {t('conn.live')}
      </Badge>
    );
  }
  if (status === 'demo') return <Badge tone="gold">{t('conn.demo')}</Badge>;
  return <Badge>{t('conn.connecting')}</Badge>;
};

const Scoreline: React.FC<{ match: ViewProps['match'] }> = ({ match }) => {
  const { t } = useI18n();
  const { teams, score, clock, playback } = match;
  if (!teams) return null;
  return (
    <div className="flex items-center gap-3 rounded-xl border border-pp-line bg-pp-deep px-3 py-1 font-display text-sm">
      <span className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: teams.home.primary_color }} />
        {teams.home.short_name}
      </span>
      <span className="ltr-nums text-lg font-bold text-white">
        {score.home} - {score.away}
      </span>
      <span className="flex items-center gap-1.5">
        {teams.away.short_name}
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: teams.away.primary_color }} />
      </span>
      <span className="ltr-nums rounded bg-pp-raised px-2 text-xs text-pp-signal">{playback.ended ? t('play.ended') : clock}</span>
    </div>
  );
};

export default App;
