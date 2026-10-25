import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import { ChevronRight, Compass, FileText, Info, LayoutGrid, Pause, Play, RotateCcw, X } from 'lucide-react';
import type { Bookmark, Language, OverlayCard, PersonaType, SpeedMultiplier } from './api/contract';
import { I18nProvider, useI18n } from './i18n';
import { connectionLostText, toastText } from './i18n/toasts';
import { useMatch } from './state/useMatch';
import { activeCards } from './state/matchStore';
import type { ViewProps } from './views/types';
import { Badge, Logo, Segmented, cx } from './components/ui';
import { Pitch2D } from './components/Pitch2D';
import { CameraControl, useCameraPreset } from './components/CameraControl';
import { ReplayCard } from './components/ReplayCard';
import { ControlChaosGauge } from './components/ControlChaosGauge';
import { NarrativeFeed, StoryCard } from './components/NarrativeFeed';
import { MomentsList, compareMoments, seekTarget } from './components/MomentsList';
import { RecapModal } from './components/RecapModal';
import { LanguagePicker } from './components/LanguagePicker';
import { Modal } from './components/Modal';
import { InsightModeProvider } from './state/useInsight';
import { demoRequested } from './api/insights';
import { apiBase } from './api/transport';
// Ask the studio, catch-up mode and read-aloud.
import { AskStudio } from './components/AskStudio';
import { CatchUpBanner, CatchUpButton, ScoreValue } from './components/CatchUp';
import { ReadAloudCards, ReadAloudToggle } from './components/ReadAloud';
import { inkOn } from './lib/contrast';
import { MatchPicker } from './components/MatchPicker';
import { pickerOnLoad } from './lib/previews';
import { MomentRail } from './components/MomentRail';
import { StudioTour, keyMoments } from './components/StudioTour';
import { LazyAuditDrawer } from './components/ShowWorking';

// The heavier views load on first use, so the first screen arrives sooner on slow networks.
const SplitView = lazy(() => import('./views/SplitView').then((m) => ({ default: m.SplitView })));
const PlayerFocus = lazy(() => import('./views/PlayerFocus').then((m) => ({ default: m.PlayerFocus })));
const MyMatch = lazy(() => import('./views/MyMatch').then((m) => ({ default: m.MyMatch })));
const Lab = lazy(() => import('./views/Lab').then((m) => ({ default: m.Lab })));
const BroadcastOverlay = lazy(() => import('./components/BroadcastOverlay').then((m) => ({ default: m.BroadcastOverlay })));
const CrewHealth = lazy(() => import('./components/CrewHealth').then((m) => ({ default: m.CrewHealth })));

type ViewMode = 'studio' | 'overlay' | 'split' | 'follow' | 'fan' | 'lab';
const VIEWS: ViewMode[] = ['studio', 'overlay', 'split', 'follow', 'fan', 'lab'];
const PERSONAS: PersonaType[] = ['casual', 'tactical', 'fantasy'];
const SPEEDS: SpeedMultiplier[] = [1, 10, 60];

const viewFromHash = (): ViewMode => {
  const v = window.location.hash.replace('#', '') as ViewMode;
  return VIEWS.includes(v) ? v : 'studio';
};

export const isCapture = () => {
  try {
    return new URLSearchParams(window.location.search).get('capture') === '1';
  } catch {
    return false;
  }
};

const reducedMotion = () => {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch {
    return false;
  }
};

export const App: React.FC = () => {
  const { state, actions } = useMatch();
  // First load opens the match picker; deep links (?demo=1, #view, captures) go straight in.
  const [startPicker] = useState(() => pickerOnLoad(window.location.search, window.location.hash));
  return (
    <I18nProvider lang={state.profile.language}>
      <InsightModeProvider mode={state.status === 'demo' ? 'demo' : 'live'}>
        <Shell match={state} actions={actions} startWithPicker={startPicker} />
      </InsightModeProvider>
    </I18nProvider>
  );
};

/** Where the match comes from: the bundled synthetic replay, or the live synthetic stream. */
function useSourceKind(status: ViewProps['match']['status']): 'file' | 'eventhubs' | null {
  const [kind, setKind] = useState<'file' | 'eventhubs' | null>(null);
  useEffect(() => {
    if (status !== 'live' || kind) return;
    let live = true;
    fetch(`${apiBase()}/api/source`, { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { source?: string } | null) => {
        if (live && d) setKind(d.source === 'eventhubs' ? 'eventhubs' : 'file');
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [status, kind]);
  return kind;
}

/** A moment the viewer jumped to: its bookmark, then its card once the match reaches it. */
interface Focus {
  b: Bookmark;
  card: OverlayCard | null;
  fetched: boolean;
  missing: boolean;
  replayShown: boolean;
}

export const Shell: React.FC<ViewProps & { startWithPicker?: boolean }> = ({ match, actions, startWithPicker = false }) => {
  const { t, dir } = useI18n();
  const [pickerOpen, setPickerOpen] = useState(startWithPicker);
  const [view, setView] = useState<ViewMode>(viewFromHash);
  const [replay, setReplay] = useState<OverlayCard | null>(null);
  const [recapOpen, setRecapOpen] = useState(false);
  const [recapLoading, setRecapLoading] = useState(false);
  const [focus, setFocus] = useState<Focus | null>(null);
  const [ftDismissed, setFtDismissed] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [tourOpen, setTourOpen] = useState(false);
  const [auditFor, setAuditFor] = useState<string | null>(null);
  const [pendingJump, setPendingJump] = useState<Bookmark | null>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const source = useSourceKind(match.status);

  useEffect(() => {
    const onHash = () => setView(viewFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    if (match.recap) setRecapOpen(true);
  }, [match.recap]);

  const goTo = (v: ViewMode) => {
    if (v === view) return;
    window.location.hash = v;
    setView(v);
  };

  // A replay or a picked moment opened on one screen does not follow the viewer to the next.
  useEffect(() => {
    setReplay(null);
    setFocus(null);
  }, [view]);

  const openRecap = async () => {
    setRecapOpen(true);
    setRecapLoading(true);
    await actions.loadRecap();
    setRecapLoading(false);
  };

  const scrollToStage = () => {
    // Back up to the pitch so the picked moment is in view, below the sticky bar.
    stageRef.current?.scrollIntoView({ block: 'start', behavior: reducedMotion() ? 'auto' : 'smooth' });
  };

  const { profile, playback, teams } = match;
  const clockS = playback.clock_s;

  // Jump to a moment: a few seconds of build-up when the match is playing; straight onto the
  // moment when it is paused, so there is something to see without pressing play.
  const jumpTo = (b: Bookmark) => {
    const paused = !playback.is_running && !playback.ended;
    actions.seek(paused ? b.clock_s + 1 : seekTarget(b.clock_s), b.period);
    setFocus({ b, card: null, fetched: false, missing: false, replayShown: false });
    setFtDismissed(true);
    scrollToStage();
  };

  // The picked moment's own card: from the story feed when it lands there, else asked for
  // once the match clock has reached it (the server never serves a moment ahead of the clock).
  useEffect(() => {
    if (!focus || focus.card || focus.missing) return;
    const id = focus.b.moment_id;
    const inFeed = match.cards.find((c) => c.moment_id === id && c.slot !== 'pitch_tag' && c.slot !== 'metric_alert');
    if (inFeed) {
      setFocus((f) => (f && f.b.moment_id === id ? { ...f, card: inFeed } : f));
      return;
    }
    const reached = compareMoments(focus.b, { clock_s: playback.clock_s, period: playback.period }) <= 0;
    if (!reached || focus.fetched) return;
    setFocus((f) => (f && f.b.moment_id === id ? { ...f, fetched: true } : f));
    void actions.getMoment(id, profile.persona, profile.language).then((card) =>
      setFocus((f) => (f && f.b.moment_id === id ? { ...f, card, missing: !card } : f)),
    );
  }, [focus, match.cards, playback.clock_s, playback.period]); // eslint-disable-line react-hooks/exhaustive-deps

  // "Should he have passed?" and unfound runs open their replay as soon as the card is in.
  useEffect(() => {
    if (focus?.card?.replay && !focus.replayShown) {
      setReplay(focus.card);
      setFocus((f) => (f ? { ...f, replayShown: true } : f));
    }
  }, [focus]);

  // A tour stop that jumps from another screen lands once the studio is showing.
  useEffect(() => {
    if (pendingJump && view === 'studio') {
      jumpTo(pendingJump);
      setPendingJump(null);
    }
  }, [pendingJump, view]); // eslint-disable-line react-hooks/exhaustive-deps

  // The tour's key-moment run: jump to each, play into it, pause on it; "Next" moves on.
  const [keyRun, setKeyRun] = useState<{ list: Bookmark[]; index: number } | null>(null);
  const startKey = (list: Bookmark[], index: number) => {
    const b = list[index];
    setKeyRun({ list, index });
    if (view !== 'studio') {
      setPendingJump(b);
      goTo('studio');
    } else jumpTo(b);
    if (!playback.is_running && !playback.ended) actions.togglePause();
  };
  const keyNow = keyRun ? keyRun.list[keyRun.index] : null;
  const keyReached = !!keyNow && keyNow.moment_id === focus?.b.moment_id && compareMoments(keyNow, { clock_s: clockS, period: playback.period }) <= 0;
  useEffect(() => {
    if (keyReached && playback.is_running) actions.togglePause();
  }, [keyReached]); // eslint-disable-line react-hooks/exhaustive-deps
  const playKeys = () => {
    const list = keyMoments(match.bookmarks);
    if (list.length) startKey(list, 0);
  };
  const nextKey = () => {
    if (!keyRun) return;
    if (keyRun.index + 1 < keyRun.list.length) startKey(keyRun.list, keyRun.index + 1);
    else setKeyRun(null);
  };

  const tourGo = {
    studio: () => {
      goTo('studio');
      scrollToStage();
      return true;
    },
    decision: () => {
      const b = [...match.bookmarks].sort(compareMoments).find((x) => x.kind === 'better_option');
      if (!b) return false;
      if (view === 'studio') jumpTo(b);
      else {
        setPendingJump(b);
        goTo('studio');
      }
      return true;
    },
    fanArabic: () => {
      if (profile.language !== 'ar') actions.setView({ language: 'ar' });
      goTo('split');
      return true;
    },
    audit: () => {
      const card = [...match.cards].reverse().find((c) => !c.moment_id.startsWith('metric:') && c.slot !== 'pitch_tag');
      if (!card) return false;
      setAuditFor(card.moment_id);
      return true;
    },
  };

  const openReplayFor = useCallback(
    (momentId: string) => {
      void actions.getMoment(momentId, profile.persona, profile.language).then((card) => {
        if (card?.replay) setReplay(card);
      });
    },
    [actions, profile.persona, profile.language],
  );
  const [camera, setCamera] = useCameraPreset();

  const liveReplay = activeCards(match.cards, clockS, 'full_screen', match.cue.ruledOut).find((c) => c.replay);

  // OBS / vMix Browser Source: ?capture=1#overlay renders only the graphics, transparent (docs/OBS.md).
  if (view === 'overlay' && isCapture()) {
    return (
      <div dir={dir} className="h-screen w-screen overflow-hidden bg-transparent">
        <Suspense fallback={null}>
          <BroadcastOverlay match={match} actions={actions} capture />
        </Suspense>
      </div>
    );
  }

  const showFullTime = playback.ended && !ftDismissed && !recapOpen && view === 'studio';

  return (
    <div dir={dir} className="flex min-h-screen flex-col bg-pp-night text-slate-100">
      {/* Only this bar stays on screen while scrolling on a phone: brand, score, play and recap. */}
      <header className="sticky top-0 z-40 h-16 border-b-2 border-pp-pulse bg-pp-night/95 backdrop-blur">
        <div className="mx-auto flex h-full max-w-7xl items-center gap-2 px-3 sm:gap-3 sm:px-4">
          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <Logo />
            <div className="hidden min-w-0 lg:block">
              <h1 className="font-display text-2xl font-extrabold uppercase italic leading-none tracking-broadcast text-pp-chalk">
                Pitch<span className="text-pp-pulse">Pulse</span>
              </h1>
              <p className="hidden truncate text-[11px] text-pp-mute md:block">{t('visit.tagline')}</p>
            </div>
            <h1 className="sr-only lg:hidden">PitchPulse</h1>
          </div>
          <div className="hidden items-center gap-2 xl:flex">
            <SourceBadge status={match.status} source={source} />
          </div>
          <div className="ms-auto flex min-w-0 items-center gap-1.5 sm:gap-2">
            <Scoreline match={match} source={source} />
            <button
              type="button"
              onClick={actions.togglePause}
              disabled={playback.ended}
              aria-label={playback.is_running ? t('guide.pause') : t('guide.play')}
              title={playback.is_running ? t('guide.pause') : t('guide.play')}
              className="flex h-11 w-11 shrink-0 items-center justify-center border border-pp-line bg-pp-panel text-white hover:border-pp-pulse disabled:opacity-40"
            >
              {playback.is_running ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
            <div className="hidden items-center gap-2 lg:flex">
              <SpeedAndRestart match={match} actions={actions} />
            </div>
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              aria-haspopup="dialog"
              aria-label={t('picker.openLabel')}
              title={t('picker.openLabel')}
              data-testid="picker-open"
              className="flex h-11 w-11 shrink-0 items-center justify-center border border-pp-line bg-pp-panel text-pp-chalk hover:border-pp-signal lg:w-auto lg:gap-1.5 lg:px-3"
            >
              <LayoutGrid className="h-4 w-4" aria-hidden />
              <span className="hidden font-display text-sm font-bold uppercase tracking-broadcast lg:inline">{t('picker.open')}</span>
            </button>
            <button
              type="button"
              onClick={() => setTourOpen(true)}
              aria-label={t('tour.label')}
              title={t('tour.label')}
              aria-expanded={tourOpen}
              data-testid="tour-open"
              className="flex h-11 w-11 shrink-0 items-center justify-center border border-pp-signal/70 bg-pp-panel text-pp-signal hover:border-pp-signal lg:w-auto lg:gap-1.5 lg:px-3"
            >
              <Compass className="h-4 w-4" aria-hidden />
              <span className="hidden font-display text-sm font-bold uppercase tracking-broadcast lg:inline">{t('tour.open')}</span>
            </button>
            <button
              type="button"
              onClick={() => setAboutOpen(true)}
              aria-haspopup="dialog"
              aria-label={t('guide.about.label')}
              title={t('guide.about.label')}
              data-testid="about-open"
              className="flex h-11 w-11 shrink-0 items-center justify-center border border-pp-line bg-pp-panel text-pp-chalk hover:border-pp-signal lg:w-auto lg:gap-1.5 lg:px-3"
            >
              <Info className="h-4 w-4" aria-hidden />
              <span className="hidden font-display text-sm font-bold uppercase tracking-broadcast lg:inline">{t('guide.about.open')}</span>
            </button>
            <button
              type="button"
              onClick={openRecap}
              aria-label={t('play.recap')}
              className="flex h-11 min-w-[44px] shrink-0 items-center justify-center gap-1.5 bg-pp-signal px-3 font-display text-sm font-extrabold uppercase italic tracking-broadcast text-pp-night hover:bg-pp-chalk"
            >
              <FileText className="h-4 w-4" aria-hidden />
              <span className="hidden sm:inline">{t('play.recap')}</span>
            </button>
          </div>
        </div>
      </header>

      {/* Views and viewer choices: scroll away on phones, stay put under the bar on wide screens. */}
      <section aria-label={t('visit.choices')} className="z-30 border-b border-pp-line/60 bg-pp-night/95 backdrop-blur lg:sticky lg:top-16">
        <div className="mx-auto max-w-7xl px-3 pt-2 sm:px-4">
          <ViewTabs view={view} onPick={goTo} />
        </div>
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-2 px-3 py-2 sm:px-4">
          <AudiencePicker value={profile.persona === 'player_spotlight' ? 'casual' : profile.persona} onChange={(persona) => actions.setView({ persona })} />
          <div className="flex items-center gap-2 lg:hidden">
            <SpeedAndRestart match={match} actions={actions} />
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-pp-mute sm:ms-auto">
            <CatchUpButton match={match} actions={actions} />
            <ReadAloudToggle match={match} />
            <LanguagePicker value={profile.language} languages={match.languages} onChange={(language: Language) => actions.setView({ language })} />
          </div>
          <div className="flex flex-wrap items-center gap-2 xl:hidden">
            <SourceBadge status={match.status} source={source} />
          </div>
          {match.crew && (
            <Badge tone={match.crew.mode === 'ai' ? 'signal' : 'mute'} className="hidden whitespace-nowrap md:inline-flex" title={match.crew.mode === 'template' ? t('crew.templateHint') : undefined}>
              {t(match.crew.mode === 'ai' ? 'crew.ai' : 'crew.template')}
            </Badge>
          )}
        </div>
      </section>

      <main className="w-full flex-1">
        {match.connectionLost && <ConnectionLost language={profile.language} onRetry={actions.retryNow} />}
        <CatchUpBanner match={match} actions={actions} onStory={openRecap} />
        <ReadAloudCards match={match} />

        {match.status === 'demo' && (
          <div className="border-b border-pp-gold/30 bg-pp-gold/10 px-4 py-1.5 text-center text-xs text-pp-gold">
            {t(demoRequested() ? 'conn.demoMode' : 'conn.demoHint')}
          </div>
        )}

        <div className="mx-auto w-full max-w-7xl p-3 sm:p-4">
          {!teams ? (
            <StudioSkeleton />
          ) : (
            <Suspense fallback={<StudioSkeleton />}>
              {view === 'studio' && (
                // Phones: pitch, the crew's story, then the rest. Wide screens: two columns.
                <div className="flex flex-col gap-4 lg:grid lg:grid-cols-12 lg:items-start">
                  <div className="contents lg:col-span-7 lg:block lg:space-y-4">
                    <div ref={stageRef} className="order-1 scroll-mt-20 space-y-3 lg:scroll-mt-48">
                      {showFullTime && (
                        <FullTimeBanner
                          onRestart={() => {
                            actions.reset();
                            setFtDismissed(true);
                          }}
                          onRecap={() => {
                            setFtDismissed(true);
                            void openRecap();
                          }}
                          onDismiss={() => setFtDismissed(true)}
                        />
                      )}
                      {focus && (
                        <MomentFocus focus={focus} match={match} onClose={() => setFocus(null)} onOpenReplay={setReplay} />
                      )}
                      <MomentRail bookmarks={match.bookmarks} spoilers={profile.spoilers !== false} nowS={clockS} nowPeriod={playback.period} history={match.history} colors={{ home: teams.home.primary_color, away: teams.away.primary_color }} onJump={jumpTo} />
                      {liveReplay ? (
                        <ReplayCard card={liveReplay} teams={teams} />
                      ) : (
                        <div className="space-y-2">
                          <Pitch2D
                            teams={teams}
                            event={match.lastEvent}
                            recentEvents={match.events.slice(-6)}
                            positions={match.positions}
                            showTags
                            camera={camera}
                            pitchTags={activeCards(match.cards, clockS, 'pitch_tag', match.cue.ruledOut)}
                          />
                          <div className="flex justify-end">
                            <CameraControl value={camera} onChange={setCamera} />
                          </div>
                        </div>
                      )}
                    </div>
                    <div className="order-4">
                      <MomentsList match={match} actions={actions} onJump={jumpTo} />
                    </div>
                    <div className="order-5">
                      <ControlChaosGauge match={match} actions={actions} />
                    </div>
                    <div className="order-6">
                      <CrewHealthDisclosure match={match} />
                    </div>
                  </div>
                  <div className="contents lg:col-span-5 lg:block lg:space-y-4">
                    <div className="order-3 lg:order-none">
                      <AskStudio match={match} actions={actions} onOpenReplay={openReplayFor} onJump={jumpTo} />
                    </div>
                    <div className="order-2 lg:order-none">
                      <NarrativeFeed match={match} actions={actions} onOpenReplay={setReplay} />
                    </div>
                  </div>
                </div>
              )}
              {view === 'overlay' && <BroadcastOverlay match={match} actions={actions} />}
              {view === 'split' && <SplitView match={match} actions={actions} />}
              {view === 'follow' && <PlayerFocus match={match} actions={actions} />}
              {view === 'fan' && <MyMatch match={match} actions={actions} />}
              {view === 'lab' && <Lab match={match} actions={actions} />}
            </Suspense>
          )}
        </div>
      </main>

      <AboutFooter match={match} onHow={() => goTo('lab')} />

      <Modal open={!!replay} onClose={() => setReplay(null)} labelledBy={replay ? `replay-${replay.card_id}` : 'replay'} name="replay" className="max-w-4xl">
        {replay && <ReplayCard card={replay} teams={teams} onClose={() => setReplay(null)} />}
      </Modal>

      <Modal open={aboutOpen} onClose={() => setAboutOpen(false)} labelledBy="about-modal-title" name="about" className="max-w-2xl">
        <AboutPanel
          match={match}
          titleId="about-modal-title"
          onClose={() => setAboutOpen(false)}
          onHow={() => {
            setAboutOpen(false);
            goTo('lab');
          }}
        />
      </Modal>

      <MatchPicker
        open={pickerOpen}
        sessionMatchId={match.matchId}
        spoilerSafe={profile.spoilers === false}
        onClose={() => setPickerOpen(false)}
        onWatch={() => {
          setPickerOpen(false);
          if (view !== 'studio') goTo('studio');
          window.scrollTo({ top: 0 });
        }}
      />

      <StudioTour
        open={tourOpen}
        onClose={() => {
          setTourOpen(false);
          setKeyRun(null);
        }}
        go={tourGo}
        run={keyRun && keyNow ? { index: keyRun.index, total: keyRun.list.length, current: keyNow, paused: keyReached && !playback.is_running } : null}
        onPlayKeys={match.bookmarks.length ? playKeys : undefined}
        onNextKey={nextKey}
      />
      {auditFor && <LazyAuditDrawer momentId={auditFor} onClose={() => setAuditFor(null)} />}

      <RecapModal open={recapOpen} onClose={() => setRecapOpen(false)} recap={match.recap} loading={recapLoading} teams={teams} />

      {match.error && (
        <div role="alert" className="fixed bottom-4 start-4 end-4 z-50 mx-auto flex max-w-md items-center justify-between gap-3 border border-pp-pulse/50 bg-pp-panel px-4 py-3 text-sm shadow-xl">
          <span>{toastText(match.error, match.errorCode, profile.language)}</span>
          <button type="button" onClick={actions.clearError} aria-label={t('common.close')} className="flex h-11 w-11 shrink-0 items-center justify-center text-pp-mute hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
};

/** A long outage (LC-15): one plain sentence in the viewer's language and a button that
 * skips the back-off wait. Reconnecting carries on by itself either way. */
const ConnectionLost: React.FC<{ language: string; onRetry: () => void }> = ({ language, onRetry }) => {
  const text = connectionLostText(language);
  return (
    <div role="alert" data-testid="connection-lost" lang={text.lang} className="border-b border-pp-pulse/50 bg-pp-panel">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2 text-sm text-pp-chalk">
        <span className="h-2 w-2 shrink-0 animate-heartbeat rounded-full bg-pp-pulse" aria-hidden />
        <span className="min-w-0 flex-1">{text.message}</span>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex min-h-[44px] items-center border border-pp-line bg-pp-raised px-3 font-display text-sm font-bold uppercase tracking-broadcast text-pp-chalk hover:border-pp-signal"
        >
          {text.retry}
        </button>
      </div>
    </div>
  );
};

const SpeedAndRestart: React.FC<ViewProps> = ({ match, actions }) => {
  const { t } = useI18n();
  return (
    <>
      <Segmented
        label={t('play.speed')}
        value={match.playback.speed_multiplier}
        onChange={(s) => actions.setSpeed(s)}
        options={SPEEDS.map((s) => ({ value: s, label: <span className="ltr-nums">{s}x</span>, title: t('visit.sharedClock') }))}
        className="ltr-nums"
        dir="ltr"
      />
      <button
        type="button"
        onClick={actions.reset}
        aria-label={t('play.reset')}
        title={`${t('play.reset')}. ${t('visit.sharedClock')}`}
        className="flex h-11 w-11 shrink-0 items-center justify-center border border-pp-line bg-pp-panel text-pp-mute hover:text-white"
      >
        <RotateCcw className="h-4 w-4" />
      </button>
    </>
  );
};

/** Square broadcast tabs that scroll sideways on a phone, with a cue that there are more. */
const ViewTabs: React.FC<{ view: ViewMode; onPick: (v: ViewMode) => void }> = ({ view, onPick }) => {
  const { t, dir } = useI18n();
  const strip = useRef<HTMLDivElement>(null);
  const [more, setMore] = useState(false);
  const check = useCallback(() => {
    const el = strip.current;
    if (!el) return;
    const left = Math.abs(el.scrollLeft);
    setMore(el.scrollWidth - el.clientWidth - left > 4);
  }, []);
  useEffect(() => {
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, [check, dir]);
  useEffect(() => {
    strip.current?.querySelector('[aria-current="page"]')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
  }, [view]);
  return (
    <div className="relative">
      <nav aria-label={t('visit.views')} ref={strip} onScroll={check} className="flex max-w-full items-stretch overflow-x-auto border border-pp-line bg-pp-deep [scrollbar-width:none]">
        {VIEWS.map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => onPick(v)}
            aria-current={view === v ? 'page' : undefined}
            className={cx(
              'min-h-[44px] shrink-0 whitespace-nowrap border-b-2 px-3 font-display text-sm font-bold uppercase tracking-broadcast transition',
              view === v ? 'border-pp-pulse bg-pp-pulseFill text-white' : 'border-transparent text-pp-mute hover:text-pp-chalk',
            )}
          >
            {t(`view.${v}`)}
          </button>
        ))}
      </nav>
      {more && (
        <span
          aria-hidden
          data-testid="tabs-more"
          title={t('visit.moreViews')}
          className="pointer-events-none absolute inset-y-0 end-0 flex w-12 items-center justify-end bg-gradient-to-l from-pp-night via-pp-night/80 to-transparent pe-1 text-pp-chalk rtl:bg-gradient-to-r"
        >
          <ChevronRight className="h-5 w-5 rtl:rotate-180" />
        </span>
      )}
    </div>
  );
};

/** "I'm a: Fan / Analyst / Stats scout": rounded pills, so it never reads as another tab. */
const AudiencePicker: React.FC<{ value: PersonaType; onChange: (p: PersonaType) => void }> = ({ value, onChange }) => {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-2" title={t('visit.audienceHint')}>
      <span id="audience-label" className="text-xs font-semibold text-pp-mute">
        {t('visit.audience')}
      </span>
      <div role="radiogroup" aria-labelledby="audience-label" className="flex items-center gap-1 rounded-full border border-pp-line bg-pp-deep p-0.5">
        {PERSONAS.map((p) => (
          <button
            key={p}
            type="button"
            role="radio"
            aria-checked={value === p}
            onClick={() => onChange(p)}
            className={cx(
              'min-h-[36px] rounded-full px-3 text-xs font-semibold normal-case transition',
              value === p ? 'bg-pp-signal text-pp-night' : 'text-pp-chalk hover:bg-pp-raised',
            )}
          >
            {t(`persona.${p}`)}
          </button>
        ))}
      </div>
    </div>
  );
};

const SourceBadge: React.FC<{ status: ViewProps['match']['status']; source: 'file' | 'eventhubs' | null }> = ({ status, source }) => {
  const { t } = useI18n();
  if (status === 'demo') return <Badge tone="gold">{t('conn.demo')}</Badge>;
  if (status !== 'live') return <Badge>{t('conn.connecting')}</Badge>;
  // "Live" only for the live stream; the bundled match is a replay, and says so.
  if (source === 'eventhubs') {
    return (
      <Badge tone="pulse" title={t('visit.source.liveHint')}>
        <span className="h-2 w-2 animate-heartbeat rounded-full bg-white" />
        {t('visit.source.live')}
      </Badge>
    );
  }
  return (
    <Badge tone="mute" title={t('visit.source.replayHint')}>
      <span className="h-2 w-2 rounded-full bg-pp-signal" aria-hidden />
      {t('visit.source.replay')}
    </Badge>
  );
};

const FullTimeBanner: React.FC<{ onRestart: () => void; onRecap: () => void; onDismiss: () => void }> = ({ onRestart, onRecap, onDismiss }) => {
  const { t } = useI18n();
  return (
    <section aria-labelledby="ft-title" data-testid="full-time-banner" className="border-s-4 border-pp-signal bg-pp-panel px-4 py-3">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h2 id="ft-title" className="font-display text-lg font-extrabold uppercase italic tracking-broadcast text-pp-chalk">
            {t('visit.ft.title')}
          </h2>
          <p className="mt-0.5 text-sm text-slate-300">{t('visit.ft.body')}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button type="button" onClick={onRestart} className="inline-flex min-h-[44px] items-center gap-1.5 bg-pp-pulseFill px-4 font-display text-sm font-extrabold uppercase italic tracking-broadcast text-white hover:bg-pp-chalk hover:text-pp-night">
              <RotateCcw className="h-4 w-4" aria-hidden />
              {t('visit.ft.watch')}
            </button>
            <button type="button" onClick={onRecap} className="inline-flex min-h-[44px] items-center gap-1.5 border border-pp-line bg-pp-deep px-4 font-display text-sm font-bold uppercase tracking-broadcast text-pp-chalk hover:border-pp-signal">
              <FileText className="h-4 w-4" aria-hidden />
              {t('visit.ft.recap')}
            </button>
          </div>
        </div>
        <button type="button" onClick={onDismiss} aria-label={t('visit.ft.dismiss')} className="flex h-11 w-11 shrink-0 items-center justify-center text-pp-mute hover:text-white">
          <X className="h-4 w-4" />
        </button>
      </div>
    </section>
  );
};

const MomentFocus: React.FC<{ focus: Focus; match: ViewProps['match']; onClose: () => void; onOpenReplay: (c: OverlayCard) => void }> = ({
  focus,
  match,
  onClose,
  onOpenReplay,
}) => {
  const { t } = useI18n();
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    ref.current?.focus({ preventScroll: true });
  }, [focus.b.moment_id]);
  const status = focus.card ? null : focus.missing ? t('visit.jump.missing') : match.playback.is_running ? t('visit.jump.comingUp') : t('visit.jump.paused');
  return (
    <section ref={ref} tabIndex={-1} aria-labelledby="focus-title" data-testid="moment-focus" className="border border-pp-signal/70 bg-pp-panel p-3 focus:outline-none">
      <div className="mb-2 flex items-center gap-2">
        <h2 id="focus-title" className="min-w-0 flex-1 font-display text-sm font-extrabold uppercase italic tracking-broadcast text-pp-signal">
          {t('visit.jump.title', { clock: `⁦${focus.b.match_clock}⁩` })}
        </h2>
        <button type="button" onClick={onClose} aria-label={t('visit.jump.close')} className="flex h-11 w-11 shrink-0 items-center justify-center text-pp-mute hover:text-white">
          <X className="h-4 w-4" />
        </button>
      </div>
      {focus.card ? (
        <StoryCard card={focus.card} match={match} isTop={false} favouriteColor={null} onOpenReplay={onOpenReplay} highlight />
      ) : (
        <p role="status" className="flex items-center gap-2 text-sm text-slate-300">
          <Info className="h-4 w-4 shrink-0 text-pp-signal" aria-hidden />
          {status}
        </p>
      )}
    </section>
  );
};

/** Crew health is for the curious: folded away in the fan's studio, open in Under the hood. */
const CrewHealthDisclosure: React.FC<{ match: ViewProps['match'] }> = ({ match }) => {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  return (
    <details className="border border-pp-line bg-pp-panel/95" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="flex min-h-[44px] cursor-pointer items-center gap-2 px-4 font-display text-sm font-bold uppercase tracking-broadcast text-pp-mute hover:text-pp-chalk">
        <ChevronRight className={cx('h-4 w-4 transition rtl:rotate-180', open && 'rotate-90 rtl:rotate-90')} aria-hidden />
        {t('visit.health.more')}
        <span className="ms-2 hidden text-[11px] font-normal normal-case tracking-normal md:inline">{t('visit.health.moreHint')}</span>
      </summary>
      {open && (
        <Suspense fallback={<div className="h-24 animate-pulse bg-pp-raised/40" />}>
          <CrewHealth match={match} />
        </Suspense>
      )}
    </details>
  );
};

const AboutFooter: React.FC<{ match: ViewProps['match']; onHow: () => void }> = ({ match, onHow }) => {
  const { t } = useI18n();
  return (
    <footer aria-labelledby="about-title" className="mt-6 border-t-2 border-pp-pulse bg-pp-deep">
      <div className="mx-auto grid max-w-7xl gap-3 px-4 py-5 text-sm text-slate-300 md:grid-cols-3">
        <div className="md:col-span-2">
          <h2 id="about-title" className="mb-1 font-display text-base font-extrabold uppercase italic tracking-broadcast text-pp-chalk">
            {t('visit.about.title')}
          </h2>
          <p>{t('visit.about.what')}</p>
          <p className="mt-1">{t('visit.about.synthetic')}</p>
          <p className="mt-1">{t(match.crew?.mode === 'ai' ? 'visit.about.ai' : 'visit.about.template')}</p>
        </div>
        <div className="flex flex-col items-start gap-2 md:items-end">
          <button type="button" onClick={onHow} className="inline-flex min-h-[44px] items-center gap-1.5 border border-pp-line px-3 font-display text-sm font-bold uppercase tracking-broadcast text-pp-chalk hover:border-pp-signal">
            {t('visit.about.how')}
            <ChevronRight className="h-4 w-4 rtl:rotate-180" aria-hidden />
          </button>
          <p className="text-xs text-pp-mute">{t('visit.about.team')}</p>
        </div>
      </div>
    </footer>
  );
};

/** "About this demo" from the header: the footer's words, in a dialog reachable from any screen. */
const AboutPanel: React.FC<{ match: ViewProps['match']; titleId: string; onClose: () => void; onHow: () => void }> = ({ match, titleId, onClose, onHow }) => {
  const { t } = useI18n();
  return (
    <div className="border-t-4 border-pp-pulse bg-pp-panel p-4 text-sm text-slate-300 sm:p-5">
      <div className="mb-2 flex items-start gap-3">
        <h2 id={titleId} className="min-w-0 flex-1 font-display text-xl font-extrabold uppercase italic tracking-broadcast text-pp-chalk">
          {t('visit.about.title')}
        </h2>
        <button type="button" onClick={onClose} aria-label={t('common.close')} className="flex h-11 w-11 shrink-0 items-center justify-center text-pp-mute hover:text-white">
          <X className="h-4 w-4" />
        </button>
      </div>
      <p>{t('visit.about.what')}</p>
      <p className="mt-2">{t('visit.about.synthetic')}</p>
      <p className="mt-2">{t(match.crew?.mode === 'ai' ? 'visit.about.ai' : 'visit.about.template')}</p>
      <p className="mt-2 text-xs text-pp-mute">{t('visit.about.team')}</p>
      <button type="button" onClick={onHow} className="mt-3 inline-flex min-h-[44px] items-center gap-1.5 border border-pp-line px-3 font-display text-sm font-bold uppercase tracking-broadcast text-pp-chalk hover:border-pp-signal">
        {t('visit.about.how')}
        <ChevronRight className="h-4 w-4 rtl:rotate-180" aria-hidden />
      </button>
    </div>
  );
};

/** The shape of the studio while the match or a view loads, never a blank wait. */
const StudioSkeleton: React.FC = () => {
  const { t } = useI18n();
  return (
    <div role="status" aria-live="polite" className="grid grid-cols-1 gap-4 lg:grid-cols-12">
      <p className="text-sm text-pp-mute lg:col-span-12" data-testid="loading-label">{t('guide.loading')}</p>
      <div className="aspect-[105/68] animate-pulse border border-pp-line bg-pp-turf/60 lg:col-span-7" />
      <div className="space-y-3 lg:col-span-5">
        <div className="h-24 animate-pulse bg-pp-raised/60" />
        <div className="h-40 animate-pulse bg-pp-raised/50" />
      </div>
    </div>
  );
};

const Scoreline: React.FC<{ match: ViewProps['match']; source: 'file' | 'eventhubs' | null }> = ({ match, source }) => {
  const { t, dir } = useI18n();
  const { teams, score, clock, playback } = match;
  if (!teams) {
    // The scorebug's shape until the first snapshot lands, so the bar never looks empty.
    return <div aria-hidden data-testid="scoreline-placeholder" className="h-11 w-36 animate-pulse bg-pp-raised/70 sm:w-48" />;
  }
  // The live Event Hubs stream is not a replay; the bundled match (and the offline demo) is.
  const replaying = match.status === 'demo' || (match.status === 'live' && source === 'file');
  return (
    // Scoreboard strip: team colour blocks either side of a white score panel. Always home
    // on the left and away on the right, also on a right-to-left page.
    <div dir="ltr" className="flex h-11 min-w-0 items-stretch font-display text-sm font-bold uppercase tracking-broadcast sm:shrink-0 sm:text-base">
      <bdi className="flex items-center px-1.5 sm:px-2.5" style={{ background: teams.home.primary_color, color: inkOn(teams.home.primary_color) }}>
        {teams.home.short_name}
      </bdi>
      <span className="ltr-nums flex items-center bg-pp-chalk px-1.5 text-lg font-extrabold text-pp-night sm:px-2.5 sm:text-xl">
        <ScoreValue value={score.home} />-<ScoreValue value={score.away} />
      </span>
      <bdi className="flex items-center px-1.5 sm:px-2.5" style={{ background: teams.away.primary_color, color: inkOn(teams.away.primary_color) }}>
        {teams.away.short_name}
      </bdi>
      <span className="ltr-nums flex shrink-0 flex-col items-start justify-center whitespace-nowrap bg-pp-night px-1.5 leading-none text-pp-signal sm:px-2.5">
        {/* Says what is playing: a synthetic replay, on its own, at this speed (shared by everyone). */}
        {replaying && !playback.ended && (
          <span
            data-testid="replay-speed"
            dir={dir}
            title={t('guide.replay.hint', { speed: playback.speed_multiplier })}
            className="mb-0.5 hidden text-[9px] font-bold text-pp-mute min-[375px]:block"
          >
            {/* Narrow phones get the short form; the title and screen-reader text say it in full. */}
            <span className="min-[400px]:hidden">{t('guide.replay.short', { speed: playback.speed_multiplier })}</span>
            <span className="hidden min-[400px]:inline">{t('guide.replay.badge', { speed: playback.speed_multiplier })}</span>
            <span className="sr-only">. {t('guide.replay.hint', { speed: playback.speed_multiplier })}</span>
          </span>
        )}
        <span>{playback.ended ? t('play.ended') : clock}</span>
      </span>
    </div>
  );
};

export default App;
