import { useCallback, useEffect, useReducer, useRef } from 'react';
import type { AskChip, AskResult, ClientAction, OverlayCard, ServerMessage, SpeedMultiplier, ViewerProfile } from '../api/contract';
import { LiveTransport } from '../api/liveTransport';
import { DEFAULT_PROFILE, MockMatchServer, loadDemoFixture } from '../api/mockServer';
import type { MatchTransport } from '../api/transport';
import { initialMatchState, matchReducer } from './matchStore';
import { ALL_LANGUAGES } from '../lib/languages';
import { JumpPacer, ViewPacer } from './pacer';

const PROFILE_KEY = 'pitchpulse.profile';
const LIVE_TIMEOUT_MS = 2500;
const RETRY_MS = 2000;
const MAX_RETRIES = 3;

const PERSONAS = ['casual', 'tactical', 'fantasy', 'player_spotlight'];
const LANGUAGES: string[] = ALL_LANGUAGES;
const METRICS = ['pressure', 'xg', 'pass_difficulty', 'top_speed', 'momentum'];
const ID = /^[A-Za-z0-9_-]{1,32}$/;

// Keeps only known profile fields with allowed values; anything else falls back to the default.
export function sanitizeProfile(raw: unknown): ViewerProfile {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const pick = <T,>(v: unknown, ok: boolean, fallback: T): T => (ok ? (v as T) : fallback);
  const idOrNull = (v: unknown) => (v === null || (typeof v === 'string' && ID.test(v)) ? (v as string | null) : null);
  return {
    persona: pick(r.persona, PERSONAS.includes(r.persona as string), DEFAULT_PROFILE.persona),
    language: pick(r.language, LANGUAGES.includes(r.language as string), DEFAULT_PROFILE.language),
    favourite_team: idOrNull(r.favourite_team),
    focus_player_id: idOrNull(r.focus_player_id),
    focus_metric: pick(r.focus_metric, METRICS.includes(r.focus_metric as string), null),
    spoilers: typeof r.spoilers === 'boolean' ? r.spoilers : true,
  };
}

// The viewer's own saved choices, without anything a link pinned.
function savedProfile(): ViewerProfile {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (raw) return sanitizeProfile(JSON.parse(raw));
  } catch {
    // Private windows and blocked storage fall back to defaults.
  }
  return DEFAULT_PROFILE;
}

function storedProfile(): ViewerProfile {
  return urlProfile(savedProfile());
}

// `?persona=tactical&lang=es&club=NBR` pins the audience in the link itself, so an OBS or
// vMix Browser Source (its own empty browser storage) shows the right sheet. Checked like
// anything else from outside: each value is checked on its own, and an unknown one leaves
// the saved choice in place. Pinned values are never written back to storage.
// `?catchup=1` (or `?spoilers=0`) opens in catch-up mode: the result stays hidden.
export function urlProfile(base: ViewerProfile, search = window.location.search): ViewerProfile {
  const q = new URLSearchParams(search);
  const catchUp = q.get('catchup') === '1' || q.get('spoilers') === '0';
  const checked = sanitizeProfile({ persona: q.get('persona'), language: q.get('lang'), favourite_team: q.get('club') });
  return {
    ...base,
    persona: q.get('persona') !== null && checked.persona === q.get('persona') ? checked.persona : base.persona,
    language: q.get('lang') !== null && checked.language === q.get('lang') ? checked.language : base.language,
    favourite_team: q.get('club') && checked.favourite_team === q.get('club') ? checked.favourite_team : base.favourite_team,
    spoilers: catchUp ? false : base.spoilers,
  };
}

// Saves only what the viewer changed on top of their saved choices, so a link's pinned
// persona, language or club does not stick to the next visit.
export function saveProfileChanges(changes: Partial<ViewerProfile>) {
  try {
    localStorage.setItem(PROFILE_KEY, JSON.stringify(sanitizeProfile({ ...savedProfile(), ...changes })));
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
  // The app's own requests, spaced to fit the server's limits (state/pacer.ts).
  const viewPacer = useRef<ViewPacer<ViewerProfile> | null>(null);
  viewPacer.current ??= new ViewPacer<ViewerProfile>((changes) => transportRef.current?.send({ action: 'set_view', ...changes }));
  const jumpPacer = useRef<JumpPacer<ClientAction> | null>(null);
  jumpPacer.current ??= new JumpPacer<ClientAction>((action) => transportRef.current?.send(action));

  useEffect(() => {
    let disposed = false;
    let retries = 0;
    let timers: ReturnType<typeof setTimeout>[] = [];
    // Deep links: `?t=2050&p=1` starts at a match moment, `&pause=1` holds it there.
    // Playback is shared by everyone on the match, so the seek and pause apply to all viewers.
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
        dispatch({
          type: 'message',
          message: { type: 'ERROR', data: { message: 'The match could not be loaded. Refresh to try again.', code: 'load_failed' } },
        });
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
          viewPacer.current?.restart(1);
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
      viewPacer.current?.dispose();
      jumpPacer.current?.dispose();
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
      saveProfileChanges(changes);
      viewPacer.current?.push(changes);
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
    reset: () => jumpPacer.current?.push({ action: 'reset' }),
    seek: (clock_s: number, period?: number) => jumpPacer.current?.push({ action: 'seek', clock_s, ...(period ? { period } : {}) }),
    setView,
    clearError: () => dispatch({ type: 'clearError' }),
    // `favouriteTeam` overrides the viewer's club for this one request (the club-heart comparison).
    getMoment: (momentId: string, persona: ViewerProfile['persona'], language: ViewerProfile['language'], favouriteTeam?: string | null) =>
      transportRef.current?.getMoment(momentId, persona, language, favouriteTeam === undefined ? profileRef.current.favourite_team : favouriteTeam) ??
      Promise.resolve(null),
    loadRecap: async () => {
      const p = profileRef.current;
      const recap = (await transportRef.current?.getRecap(p.persona, p.language, p.spoilers)) ?? null;
      dispatch({ type: 'recap', recap });
      return recap;
    },
    // Catch-up mode on or off. One set_view per real change (the server rate-limits set_view),
    // and the server answers with a fresh snapshot that hides or reveals the result.
    setSpoilers: (spoilers: boolean) => {
      if (profileRef.current.spoilers === spoilers) return;
      profileRef.current = { ...profileRef.current, spoilers };
      setView({ spoilers });
    },
    // Ask the studio, answered as of the match clock in the viewer's language and spoiler setting.
    ask: (input: { question: string } | { chip: AskChip }): Promise<AskResult> => {
      const t = transportRef.current;
      if (!t) return Promise.resolve({ ok: false, failure: 'unavailable' });
      const p = profileRef.current;
      return t.ask({ ...input, lang: p.language, spoilers: p.spoilers });
    },
  };

  return { state, actions };
}

export type MatchActions = ReturnType<typeof useMatch>['actions'];
