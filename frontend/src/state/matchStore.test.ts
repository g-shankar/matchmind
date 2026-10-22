import { describe, expect, it } from 'vitest';
import { activeCards, initialMatchState, matchReducer, MAX_EVENTS } from './matchStore';
import { event, makeFixture, state } from '../test/fixture';
import { cardForMoment, DEFAULT_PROFILE } from '../api/mockServer';
import type { TickData } from '../api/contract';
import { defaultLanguages } from '../lib/languages';

const tick = (seq: number, clock_s: number, over = {}): TickData => ({
  event: event(seq, clock_s, over), clock: '00:10', period: 1, score: { home: 0, away: 0 }, state: state(clock_s),
  control_chaos: { home_control_pct: 50, away_control_pct: 50, chaos_index: 0, current_tempo: 'Controlled', rolling_momentum_home: 0 },
  cards: [], players_changed: [],
});

describe('matchReducer', () => {
  it('tracks the receiver of a completed pass and caps the event list', () => {
    let s = initialMatchState();
    for (let i = 0; i < MAX_EVENTS + 5; i++) s = matchReducer(s, { type: 'message', message: { type: 'MATCH_TICK', data: tick(i, i) } });
    expect(s.events).toHaveLength(MAX_EVENTS);
    expect(s.positions['AAA-9']).toMatchObject({ x: 70, y: 32 });
    expect(s.history.length).toBe(MAX_EVENTS + 5);
  });

  it('a snapshot after a seek clears the trail and trims history past the new clock', () => {
    let s = initialMatchState();
    s = matchReducer(s, { type: 'message', message: { type: 'MATCH_TICK', data: tick(1, 100) } });
    const f = makeFixture();
    s = { ...s, matchId: 'T-1' };
    s = matchReducer(s, {
      type: 'message',
      message: {
        type: 'INITIAL_SNAPSHOT',
        data: {
          match_id: 'T-1', clock: '00:50', period: 1, home_score: 0, away_score: 0, teams: f.teams, state: state(50),
          control_chaos: f.ticks[0].control_chaos, profile: DEFAULT_PROFILE,
          playback: { is_running: true, speed_multiplier: 10, clock_s: 50, match_clock: '00:50', period: 1, ended: false },
          recent_cards: [], bookmarks: [], players: [], crew: f.crew, auto_eventing: null,
        },
      },
    });
    expect(s.positions).toEqual({});
    expect(s.history.every((h) => h.clock_s <= 50)).toBe(true);
    // No language list from an older server: keep the default (world languages off).
    expect(s.languages.find((l) => l.code === 'pt')).toMatchObject({ available: false, reason: 'translator_off' });
  });

  it('places players and ball from the snapshot\'s recent events, so a jump or pause never shows an empty pitch', () => {
    const f = makeFixture();
    const s = matchReducer(initialMatchState(), {
      type: 'message',
      message: {
        type: 'INITIAL_SNAPSHOT',
        data: {
          match_id: 'T-1', clock: '34:06', period: 1, home_score: 1, away_score: 0, teams: f.teams, state: state(2046),
          control_chaos: f.ticks[0].control_chaos, profile: DEFAULT_PROFILE,
          playback: { is_running: false, speed_multiplier: 1, clock_s: 2046, match_clock: '34:06', period: 1, ended: false },
          recent_cards: [], bookmarks: [], players: [], crew: f.crew, auto_eventing: null,
          recent_events: [event(40, 2040), event(41, 2046, { player_id: 'BBB-9', team: 'BBB', receiver_id: 'BBB-10' })],
        },
      },
    });
    expect(s.lastEvent?.seq).toBe(41);
    expect(s.events).toHaveLength(2);
    expect(Object.keys(s.positions).sort()).toEqual(['AAA-10', 'AAA-9', 'BBB-10', 'BBB-9']);
  });

  it('keeps the error code next to the message for a translated toast', () => {
    const s = matchReducer(initialMatchState(), { type: 'message', message: { type: 'ERROR', data: { message: 'x', code: 'jump_too_fast' } } });
    expect(s.errorCode).toBe('jump_too_fast');
    expect(matchReducer(s, { type: 'clearError' }).errorCode).toBeNull();
  });

  it('takes the language list from the snapshot', () => {
    const f = makeFixture();
    const live = defaultLanguages(true);
    const s = matchReducer(initialMatchState(), {
      type: 'message',
      message: {
        type: 'INITIAL_SNAPSHOT',
        data: {
          match_id: 'T-1', clock: '00:00', period: 1, home_score: 0, away_score: 0, teams: f.teams, state: state(0),
          control_chaos: f.ticks[0].control_chaos, profile: DEFAULT_PROFILE,
          playback: { is_running: true, speed_multiplier: 10, clock_s: 0, match_clock: '00:00', period: 1, ended: false },
          recent_cards: [], bookmarks: [], players: [], crew: f.crew, languages: live, auto_eventing: null,
        },
      },
    });
    expect(s.languages).toBe(live);
    expect(s.languages.filter((l) => l.source === 'translator').every((l) => l.available)).toBe(true);
  });

  it('replaces re-voiced cards in place', () => {
    const m = makeFixture().moments[0];
    const en = cardForMoment(m, DEFAULT_PROFILE)!;
    const es = cardForMoment(m, { ...DEFAULT_PROFILE, language: 'es' })!;
    let s = { ...initialMatchState(), cards: [en] };
    s = matchReducer(s, { type: 'replaceCards', cards: [es] });
    expect(s.cards[0].headline).toBe('Gol de AAA');
  });
});

describe('activeCards', () => {
  it('keeps a card on screen for its duration only', () => {
    const card = cardForMoment(makeFixture().moments[0], DEFAULT_PROFILE)!;
    expect(activeCards([card], 22, 'lower_third')).toHaveLength(1);
    expect(activeCards([card], 40, 'lower_third')).toHaveLength(0);
    expect(activeCards([card], 22, 'side_panel')).toHaveLength(0);
  });
});

describe('malformed frames', () => {
  it('drops a snapshot that does not match the contract instead of throwing', () => {
    const s = initialMatchState();
    const bad = { type: 'INITIAL_SNAPSHOT', data: { players: null } } as never;
    expect(matchReducer(s, { type: 'message', message: bad })).toBe(s);
  });
});

describe('catch-up guard (extreme cases EC-3)', () => {
  // On every (re)connect the server's first snapshot is for the default audience: it
  // carries the result until the set_view sent on open reaches the server.
  const f = makeFixture();
  const goal = cardForMoment(f.moments[0], DEFAULT_PROFILE)!;
  const snapshot = (profile = DEFAULT_PROFILE, score: number | null = 2) => ({
    type: 'INITIAL_SNAPSHOT' as const,
    data: {
      match_id: 'T-1', clock: '50:00', period: 2, home_score: score, away_score: score === null ? null : 1, teams: f.teams,
      state: state(3000, score === null ? { score_home: null, score_away: null } : { score_home: score, score_away: 1 }),
      control_chaos: f.ticks[0].control_chaos, profile,
      playback: { is_running: true, speed_multiplier: 10 as const, clock_s: 3000, match_clock: '50:00', period: 2, ended: false },
      recent_cards: [goal], bookmarks: [], players: [], crew: f.crew, auto_eventing: null,
    },
  });
  const catchUp = () => initialMatchState({ ...DEFAULT_PROFILE, spoilers: false });

  it('a default-audience snapshot never shows the result to a catch-up viewer', () => {
    expect(goal.kind).toBe('goal');
    const s = matchReducer(catchUp(), { type: 'message', message: snapshot() });
    expect(s.score).toEqual({ home: null, away: null });
    expect(s.state?.score_home ?? null).toBeNull();
    expect(s.cards).toEqual([]);
    expect(s.profile.spoilers).toBe(false);
  });

  it('the last events in a default-audience snapshot lose their score and shot outcome', () => {
    const shot = event(7, 2990, { type: 'shot', outcome: 'goal', details: { score_home: 2, score_away: 1, assist_id: 'AAA-10' } });
    const base = snapshot();
    const s = matchReducer(catchUp(), { type: 'message', message: { ...base, data: { ...base.data, recent_events: [shot] } } });
    expect(s.events).toHaveLength(1);
    expect(s.events[0].outcome).toBeNull();
    expect(s.events[0].details).not.toHaveProperty('score_home');
    expect(s.events[0].details).not.toHaveProperty('assist_id');
    expect(s.lastEvent?.outcome).toBeNull();
  });

  it('a tick or cue that races ahead of set_view is scrubbed or dropped', () => {
    let s = matchReducer(catchUp(), { type: 'message', message: snapshot() });
    const data: TickData = { ...f.ticks[1], cards: [], score: { home: 2, away: 1 } };
    s = matchReducer(s, { type: 'message', message: { type: 'MATCH_TICK', data } });
    expect(s.score).toEqual({ home: null, away: null });
    const before = s;
    s = matchReducer(s, { type: 'message', message: { type: 'CUES', data: { cues: [], active: null } } as never });
    expect(s).toBe(before);
  });

  it('a racing VAR review tick is dropped, and racing snapshot events lose shot end points', () => {
    const shot = event(7, 2990, { type: 'shot', outcome: 'goal', end: { x: 105, y: 34 } });
    const review = event(8, 2995, { type: 'var_review', outcome: 'overturned', reviewed_event_id: 'T-1-7', review_reason: 'offside' });
    const base = snapshot();
    let s = matchReducer(catchUp(), { type: 'message', message: { ...base, data: { ...base.data, recent_events: [shot, review] } } });
    expect(s.events.map((e) => e.type)).toEqual(['shot']);
    expect(s.events[0].end).toBeNull();
    const before = s;
    const data: TickData = { ...f.ticks[1], event: review, cards: [], score: { home: 2, away: 1 } };
    s = matchReducer(s, { type: 'message', message: { type: 'MATCH_TICK', data } });
    expect(s).toBe(before);
  });

  it('a profile echo does not switch catch-up off; the viewer revealing does', () => {
    let s = matchReducer(catchUp(), { type: 'message', message: { type: 'PROFILE_CHANGED', data: DEFAULT_PROFILE } });
    expect(s.profile.spoilers).toBe(false);
    s = matchReducer(s, { type: 'profile', changes: { spoilers: true } });
    s = matchReducer(s, { type: 'message', message: snapshot() });
    expect(s.score).toEqual({ home: 2, away: 1 });
  });

  it('the server-confirmed catch-up snapshot passes through unchanged', () => {
    const s = matchReducer(catchUp(), { type: 'message', message: snapshot({ ...DEFAULT_PROFILE, spoilers: false }, null) });
    expect(s.cards.map((c) => c.moment_id)).toEqual([goal.moment_id]);
    expect(s.profile.spoilers).toBe(false);
  });
});
