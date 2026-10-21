// Pure reducer from contract messages to what the screens show. Every number
// here comes from a server (or recorded) payload; nothing is recomputed.
import type {
  AutoEventingStatus,
  Bookmark,
  ControlChaosState,
  CrewStatus,
  MatchEvent,
  MatchState,
  OverlayCard,
  Playback,
  PlayerStats,
  Recap,
  ServerMessage,
  Teams,
  ViewerProfile,
  XY,
} from '../api/contract';
import { DEFAULT_PROFILE } from '../api/mockServer';

export type ConnectionStatus = 'connecting' | 'live' | 'reconnecting' | 'demo';

export interface PlayerPosition extends XY {
  clock_s: number;
}

export interface MetricSample {
  clock_s: number;
  match_clock: string;
  momentum: number;
  pressure_home: number;
  pressure_away: number;
  xg_home: number;
  xg_away: number;
}

export interface MatchViewState {
  status: ConnectionStatus;
  matchId: string | null;
  clock: string;
  period: number;
  score: { home: number; away: number };
  teams: Teams | null;
  state: MatchState | null;
  controlChaos: ControlChaosState | null;
  profile: ViewerProfile;
  playback: Playback;
  events: MatchEvent[];
  lastEvent: MatchEvent | null;
  cards: OverlayCard[];
  players: Record<string, PlayerStats>;
  positions: Record<string, PlayerPosition>;
  trails: Record<string, XY[]>;
  history: MetricSample[];
  bookmarks: Bookmark[];
  crew: CrewStatus | null;
  autoEventing: AutoEventingStatus | null;
  recap: Recap | null;
  error: string | null;
}

export const MAX_EVENTS = 60;
export const MAX_CARDS = 80;
export const MAX_TRAIL = 16;
export const MAX_HISTORY = 400;

export const initialMatchState = (profile: ViewerProfile = DEFAULT_PROFILE): MatchViewState => ({
  status: 'connecting',
  matchId: null,
  clock: '00:00',
  period: 1,
  score: { home: 0, away: 0 },
  teams: null,
  state: null,
  controlChaos: null,
  profile,
  playback: { is_running: false, speed_multiplier: 10, clock_s: 0, match_clock: '00:00', period: 1, ended: false },
  events: [],
  lastEvent: null,
  cards: [],
  players: {},
  positions: {},
  trails: {},
  history: [],
  bookmarks: [],
  crew: null,
  autoEventing: null,
  recap: null,
  error: null,
});

export type MatchAction =
  | { type: 'message'; message: ServerMessage }
  | { type: 'status'; status: ConnectionStatus }
  | { type: 'profile'; changes: Partial<ViewerProfile> }
  | { type: 'recap'; recap: Recap | null }
  | { type: 'replaceCards'; cards: OverlayCard[] }
  | { type: 'clearError' };

const sample = (s: MatchState): MetricSample => ({
  clock_s: s.clock_s,
  match_clock: s.match_clock,
  momentum: s.momentum,
  pressure_home: s.home.pressure_index,
  pressure_away: s.away.pressure_index,
  xg_home: s.xg_home,
  xg_away: s.xg_away,
});

function trackPositions(state: MatchViewState, e: MatchEvent) {
  const positions = { ...state.positions };
  const trails = { ...state.trails };
  const put = (id: string | null, p: XY | null) => {
    if (!id || !p) return;
    positions[id] = { x: p.x, y: p.y, clock_s: e.clock_s };
    trails[id] = [...(trails[id] ?? []), { x: p.x, y: p.y }].slice(-MAX_TRAIL);
  };
  const moves = e.type === 'carry' || e.type === 'dribble' || e.type === 'run';
  put(e.player_id, e.start);
  if (moves) put(e.player_id, e.end);
  if (e.type === 'pass' && e.outcome === 'complete') put(e.receiver_id, e.end);
  return { positions, trails };
}

function mergePlayers(base: Record<string, PlayerStats>, changed: PlayerStats[]) {
  if (!changed.length) return base;
  const next = { ...base };
  for (const p of changed) next[p.player_id] = p;
  return next;
}

export function matchReducer(state: MatchViewState, action: MatchAction): MatchViewState {
  switch (action.type) {
    case 'status':
      return { ...state, status: action.status };
    case 'profile':
      return { ...state, profile: { ...state.profile, ...action.changes } };
    case 'recap':
      return { ...state, recap: action.recap };
    case 'clearError':
      return { ...state, error: null };
    case 'replaceCards': {
      const byMoment = new Map(action.cards.map((c) => [c.moment_id, c]));
      return { ...state, cards: state.cards.map((c) => byMoment.get(c.moment_id) ?? c) };
    }
    case 'message':
      return applyMessage(state, action.message);
  }
}

function applyMessage(state: MatchViewState, m: ServerMessage): MatchViewState {
  switch (m.type) {
    case 'INITIAL_SNAPSHOT': {
      const d = m.data;
      const players: Record<string, PlayerStats> = {};
      for (const p of d.players) players[p.player_id] = p;
      const sameMatch = state.matchId === d.match_id;
      // After a seek or reset the timeline restarts, so history behind the new clock is dropped.
      const history = sameMatch ? state.history.filter((h) => h.clock_s <= d.state.clock_s) : [];
      return {
        ...state,
        matchId: d.match_id,
        clock: d.clock,
        period: d.period,
        score: { home: d.home_score, away: d.away_score },
        teams: d.teams,
        state: d.state,
        controlChaos: d.control_chaos,
        profile: d.profile,
        playback: d.playback,
        events: [],
        lastEvent: null,
        cards: d.recent_cards,
        players,
        positions: {},
        trails: {},
        history: [...history, sample(d.state)].slice(-MAX_HISTORY),
        bookmarks: d.bookmarks,
        crew: d.crew,
        autoEventing: d.auto_eventing,
        recap: d.playback.ended ? state.recap : null,
      };
    }
    case 'MATCH_TICK': {
      const d = m.data;
      const { positions, trails } = trackPositions(state, d.event);
      return {
        ...state,
        clock: d.clock,
        period: d.period,
        score: d.score,
        state: d.state,
        controlChaos: d.control_chaos,
        events: [...state.events, d.event].slice(-MAX_EVENTS),
        lastEvent: d.event,
        cards: d.cards.length ? [...state.cards, ...d.cards].slice(-MAX_CARDS) : state.cards,
        players: mergePlayers(state.players, d.players_changed),
        positions,
        trails,
        history: [...state.history, sample(d.state)].slice(-MAX_HISTORY),
        playback: { ...state.playback, clock_s: d.event.clock_s, match_clock: d.clock, period: d.period },
      };
    }
    case 'PLAYBACK_CONTROL':
      return { ...state, playback: m.data };
    case 'MATCH_RESET':
      return {
        ...initialMatchState(state.profile),
        status: state.status,
        teams: state.teams,
        bookmarks: state.bookmarks,
        crew: state.crew,
      };
    case 'PROFILE_CHANGED':
      return { ...state, profile: m.data };
    case 'PERSONA_CHANGED':
      return { ...state, profile: { ...state.profile, persona: m.data.persona } };
    case 'MATCH_END':
      return { ...state, recap: m.data.recap, playback: { ...state.playback, ended: true, is_running: false } };
    case 'ERROR':
      return { ...state, error: m.data.message };
  }
}

// Cards to show right now for a slot: newest first, highest priority first, still on screen.
export function activeCards(cards: OverlayCard[], clockS: number, slot?: OverlayCard['slot']) {
  return cards
    .filter((c) => (!slot || c.slot === slot) && clockS >= c.show_at_s - 1 && clockS <= c.show_at_s + c.duration_s)
    .sort((a, b) => b.priority - a.priority || b.show_at_s - a.show_at_s);
}
