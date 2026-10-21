import { useCallback, useEffect, useReducer, useRef } from 'react';
import type { OverlayCard, ServerMessage, SpeedMultiplier, ViewerProfile } from '../api/contract';
import { LiveTransport } from '../api/liveTransport';
import { DEFAULT_PROFILE, MockMatchServer, loadDemoFixture } from '../api/mockServer';
import type { MatchTransport } from '../api/transport';
import { initialMatchState, matchReducer } from './matchStore';

const PROFILE_KEY = 'pitchpulse.profile';
const LIVE_TIMEOUT_MS = 2500;
const RETRY_MS = 2000;
const MAX_RETRIES = 3;

function storedProfile(): ViewerProfile {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (raw) return { ...DEFAULT_PROFILE, ...(JSON.parse(raw) as Partial<ViewerProfile>) };
  } catch {
    // Private windows and blocked storage fall back to defaults.
  }
  return DEFAULT_PROFILE;
}

function saveProfile(profile: ViewerProfile) {
  try {
    localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  } catch {
    // Best effort only.
  }
}

// `?demo=1` forces the offline replay; `?live=1` never falls back to it.
function connectionMode(): 'auto' | 'demo' | 'live' {
  const q = new URLSearchParams(window.location.search);
  if (q.get('demo') === '1') return 'demo';
  if (q.get('live') === '1') return 'live';
  return 'auto';
}

export function useMatch() {
  const [state, dispatch] = useReducer(matchReducer, undefined, () => initialMatchState(storedProfile()));
  const transportRef = useRef<MatchTransport | null>(null);
  const profileRef = useRef(state.profile);
  profileRef.current = state.profile;

  useEffect(() => {
    let disposed = false;
    let retries = 0;
    let timers: ReturnType<typeof setTimeout>[] = [];
    // Deep links: `?t=2050&p=1` starts at a match moment, `&pause=1` holds it there.
    const q = new URLSearchParams(window.location.search);
    let startAt = q.has('t') ? { clock_s: Number(q.get('t')), period: Number(q.get('p') ?? 0) || undefined } : null;
    const pauseAtStart = q.get('pause') === '1';
    const onMessage = (message: ServerMessage) => {
      if (disposed) return;
      dispatch({ type: 'message', message });
      if (message.type === 'INITIAL_SNAPSHOT' && startAt && Number.isFinite(startAt.clock_s)) {
        const target = startAt;
        startAt = null;
        transportRef.current?.send({ action: 'seek', clock_s: target.clock_s, ...(target.period ? { period: target.period } : {}) });
        if (pauseAtStart && message.data.playback.is_running) transportRef.current?.send({ action: 'toggle_pause' });
      }
    };

    const startDemo = async () => {
      if (disposed) return;
      transportRef.current?.close();
      transportRef.current = null;
      try {
        const fixture = await loadDemoFixture();
        if (disposed) return;
        dispatch({ type: 'status', status: 'demo' });
        transportRef.current = new MockMatchServer(fixture, onMessage, { profile: profileRef.current });
      } catch {
        dispatch({ type: 'message', message: { type: 'ERROR', data: { message: 'The match could not be loaded. Refresh to try again.' } } });
      }
    };

    const startLive = () => {
      if (disposed) return;
      let opened = false;
      const live = new LiveTransport({
        onMessage,
        onOpen: () => {
          opened = true;
          retries = 0;
          dispatch({ type: 'status', status: 'live' });
          // Viewer choices are per connection, so restate them after every (re)connect.
          live.send({ action: 'set_view', ...profileRef.current });
        },
        onClose: (everOpened) => {
          if (disposed) return;
          if (!everOpened && mode === 'auto') return void startDemo();
          dispatch({ type: 'status', status: 'reconnecting' });
          retries += 1;
          if (mode === 'auto' && retries > MAX_RETRIES) return void startDemo();
          timers.push(setTimeout(startLive, RETRY_MS));
        },
      });
      transportRef.current = live;
      if (mode === 'auto') {
        timers.push(
          setTimeout(() => {
            if (!opened && !disposed && transportRef.current === live) void startDemo();
          }, LIVE_TIMEOUT_MS),
        );
      }
    };

    const mode = connectionMode();
    if (mode === 'demo') void startDemo();
    else startLive();

    return () => {
      disposed = true;
      timers.forEach(clearTimeout);
      timers = [];
      transportRef.current?.close();
      transportRef.current = null;
    };
  }, []);

  const send = useCallback((a: Parameters<MatchTransport['send']>[0]) => transportRef.current?.send(a), []);

  const setView = useCallback(
    (changes: Partial<ViewerProfile>) => {
      // The server rejects unknown fields, so send profile fields only.
      const next = { ...profileRef.current, ...changes };
      dispatch({ type: 'profile', changes });
      saveProfile(next);
      send({ action: 'set_view', ...changes });
      // Re-voice the cards already on screen so a language or audience switch shows at once.
      if (('language' in changes || 'persona' in changes) && transportRef.current) {
        const t = transportRef.current;
        const recent = state.cards.filter((c) => c.slot !== 'metric_alert' && c.slot !== 'pitch_tag').slice(-12);
        void Promise.all(
          recent.map((c) => t.getMoment(c.moment_id, next.persona, next.language, next.favourite_team)),
        ).then((cards) => {
          const ok = cards.filter((c): c is OverlayCard => !!c);
          if (ok.length) dispatch({ type: 'replaceCards', cards: ok });
        });
      }
    },
    [send, state.cards],
  );

  const actions = {
    togglePause: () => send({ action: 'toggle_pause' }),
    setSpeed: (speed_multiplier: SpeedMultiplier) => send({ action: 'set_speed', speed_multiplier }),
    reset: () => send({ action: 'reset' }),
    seek: (clock_s: number, period?: number) => send({ action: 'seek', clock_s, ...(period ? { period } : {}) }),
    setView,
    clearError: () => dispatch({ type: 'clearError' }),
    getMoment: (momentId: string, persona: ViewerProfile['persona'], language: ViewerProfile['language']) =>
      transportRef.current?.getMoment(momentId, persona, language, profileRef.current.favourite_team) ??
      Promise.resolve(null),
    loadRecap: async () => {
      const p = profileRef.current;
      const recap = (await transportRef.current?.getRecap(p.persona, p.language)) ?? null;
      dispatch({ type: 'recap', recap });
      return recap;
    },
  };

  return { state, actions };
}

export type MatchActions = ReturnType<typeof useMatch>['actions'];
