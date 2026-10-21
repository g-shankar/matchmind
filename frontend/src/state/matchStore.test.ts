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
