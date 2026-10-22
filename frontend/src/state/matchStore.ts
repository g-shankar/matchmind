// Pure reducer from contract messages to what the screens show. Every number
// here comes from a server (or recorded) payload; nothing is recomputed.
import type {
  AutoEventingStatus,
  Bookmark,
  ControlChaosState,
  CrewStatus,
  LanguageInfo,
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
import { DEFAULT_PROFILE } from '../api/defaults';
import { defaultLanguages } from '../lib/languages';
import { applyCues, initialCueState, retractedByCards, ruleOut, startSheet, type CueViewState } from './cues';

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
  /** Null sides while the viewer is in catch-up mode (spoilers off). */
  score: { home: number | null; away: number | null };
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
  /** Languages the viewer can pick and whether each can be shown now (from the server). */
  languages: LanguageInfo[];
  autoEventing: AutoEventingStatus | null;
  recap: Recap | null;
  /** This viewer's cue sheet and the moments ruled out (VAR) so far. */
  cue: CueViewState;
  error: string | null;
  /** Stable code of the last server error (src/i18n/toasts.ts), when it sent one. */
  errorCode: string | null;
}

export const MAX_EVENTS = 60;
export const MAX_CARDS = 80;
export const MAX_TRAIL = 16;
export const MAX_HISTORY = 400;
export const MAX_PLAYERS = 60;
export const MAX_BOOKMARKS = 200;

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
  playback: { is_running: false, speed_multiplier: 1, clock_s: 0, match_clock: '00:00', period: 1, ended: false },
  events: [],
  lastEvent: null,
  cards: [],
  players: {},
  positions: {},
  trails: {},
  history: [],
  bookmarks: [],
  crew: null,
  languages: defaultLanguages(),
  autoEventing: null,
  recap: null,
  cue: initialCueState(),
  error: null,
  errorCode: null,
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

function trackPositions(state: Pick<MatchViewState, 'positions' | 'trails'>, e: MatchEvent) {
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
      return { ...state, error: null, errorCode: null };
    case 'replaceCards': {
      const byMoment = new Map(action.cards.map((c) => [c.moment_id, c]));
      return { ...state, cards: state.cards.map((c) => byMoment.get(c.moment_id) ?? c) };
    }
    case 'message':
      try {
        return applyMessage(state, action.message);
      } catch {
        // A frame that does not match the contract is dropped; the next snapshot or tick restores state.
        return state;
      }
  }
}

function applyMessage(state: MatchViewState, m: ServerMessage): MatchViewState {
  switch (m.type) {
    case 'INITIAL_SNAPSHOT': {
      const d = m.data;
      const players: Record<string, PlayerStats> = {};
      for (const p of d.players.slice(0, MAX_PLAYERS)) players[p.player_id] = p;
      const sameMatch = state.matchId === d.match_id;
      // The last events played place the players and ball at once (after a jump, while paused).
      const recentEvents = (d.recent_events ?? []).slice(-MAX_EVENTS);
      let placed: Pick<MatchViewState, 'positions' | 'trails'> = { positions: {}, trails: {} };
      for (const e of recentEvents) placed = trackPositions(placed, e);
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
        events: recentEvents,
        lastEvent: recentEvents[recentEvents.length - 1] ?? null,
        cards: d.recent_cards.slice(-MAX_CARDS),
        players,
        positions: placed.positions,
        trails: placed.trails,
        history: [...history, sample(d.state)].slice(-MAX_HISTORY),
        bookmarks: d.bookmarks.slice(0, MAX_BOOKMARKS),
        crew: d.crew,
        languages: d.languages?.length ? d.languages : state.languages,
        autoEventing: d.auto_eventing,
        recap: d.playback.ended ? state.recap : null,
        // The snapshot is the truth after a seek or reconnect: the server already left
        // ruled-out cards out; the corrections still on screen say which moments they were.
        cue: startSheet(state.cue, d.cue_sheet, retractedByCards(d.recent_cards)),
      };
    }
    case 'MATCH_TICK': {
      const d = m.data;
      const { positions, trails } = trackPositions(state, d.event);
      const cards = d.cards.length ? [...state.cards, ...d.cards].slice(-MAX_CARDS) : state.cards;
      return {
        ...state,
        clock: d.clock,
        period: d.period,
        score: d.score ?? { home: null, away: null },
        state: d.state,
        controlChaos: d.control_chaos,
        events: [...state.events, d.event].slice(-MAX_EVENTS),
        lastEvent: d.event,
        cards,
        cue: ruleOut(state.cue, retractedByCards(d.cards), state.cards, d.event.clock_s),
        players: mergePlayers(state.players, d.players_changed),
        positions,
        trails,
        history: [...state.history, sample(d.state)].slice(-MAX_HISTORY),
        playback: { ...state.playback, clock_s: d.event.clock_s, match_clock: d.clock, period: d.period },
      };
    }
    case 'CUES': {
      const next = applyCues(state.cue, m.data);
      if (next === state.cue) return state;
      const fresh = next.ruledOut.filter((id) => !state.cue.ruledOut.includes(id));
      // Ruled out by the cue stream: drop them from what is on air, animating out any still showing.
      const cue = fresh.length ? ruleOut({ ...next, ruledOut: state.cue.ruledOut }, fresh, state.cards, state.playback.clock_s) : next;
      return { ...state, cue };
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
        languages: state.languages,
      };
    case 'PROFILE_CHANGED':
      return { ...state, profile: m.data };
    case 'PERSONA_CHANGED':
      return { ...state, profile: { ...state.profile, persona: m.data.persona } };
    case 'MATCH_END':
      return { ...state, recap: m.data.recap, playback: { ...state.playback, ended: true, is_running: false } };
    case 'ERROR':
      return { ...state, error: m.data.message, errorCode: m.data.code ?? null };
  }
}

// Cards to show right now for a slot: newest first, highest priority first, still on screen,
// never one whose moment was ruled out (VAR).
export function activeCards(cards: OverlayCard[], clockS: number, slot?: OverlayCard['slot'], ruledOut: readonly string[] = []) {
  return cards
    .filter(
      (c) =>
        (!slot || c.slot === slot) &&
        clockS >= c.show_at_s - 1 &&
        clockS <= c.show_at_s + c.duration_s &&
        !ruledOut.includes(c.moment_id),
    )
    .sort((a, b) => b.priority - a.priority || b.show_at_s - a.show_at_s);
}
