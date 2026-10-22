import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

afterEach(cleanup);
import { I18nProvider } from '../i18n';
import { initialMatchState, type MatchViewState } from '../state/matchStore';
import type { MatchActions } from '../state/useMatch';
import type { PlayerStats } from '../api/contract';
import { event, makeFixture } from '../test/fixture';
import { PlayerFocus, defaultFocusId } from './PlayerFocus';

const teams = makeFixture().teams;

const mockActions = () =>
  ({
    togglePause: vi.fn(),
    setSpeed: vi.fn(),
    reset: vi.fn(),
    seek: vi.fn(),
    setView: vi.fn(),
    clearError: vi.fn(),
    getMoment: vi.fn(),
    loadRecap: vi.fn(),
    setSpoilers: vi.fn(),
    ask: vi.fn().mockResolvedValue({ ok: false, failure: 'unavailable' }),
    isDemo: vi.fn(() => false),
  }) as unknown as MatchActions;

const stats = (over: Partial<PlayerStats> = {}): PlayerStats => ({
  player_id: 'AAA-9', team: 'AAA', touches: 14, passes: 9, passes_completed: 7, pass_accuracy: 78, key_passes: 2,
  shots: 3, goals: 1, assists: 0, xg: 0.47, xa: 0.12, tackles_won: 1, interceptions: 2, top_speed_kmh: 33.4,
  sprints: 5, distance_km: 1.83, carry_distance_m: 120, ...over,
});

const matchWith = (over: Partial<MatchViewState> = {}): MatchViewState => ({ ...initialMatchState(), teams, ...over });

const renderView = (m: MatchViewState, actions = mockActions(), lang = 'en') =>
  render(
    <I18nProvider lang={lang}>
      <PlayerFocus match={m} actions={actions} />
    </I18nProvider>,
  );

describe('PlayerFocus', () => {
  it('defaults to the home side first forward without sending anything', () => {
    expect(defaultFocusId(teams, null)).toBe('AAA-9');
    expect(defaultFocusId(teams, 'BBB-10')).toBe('BBB-10');
    expect(defaultFocusId(teams, 'nobody')).toBe('AAA-9');
    const actions = mockActions();
    renderView(matchWith(), actions);
    expect(actions.setView).not.toHaveBeenCalled();
    expect(screen.getByText('Suggested pick. Choose any player to follow them.')).toBeTruthy();
  });

  it('picking a player calls setView with focus_player_id', () => {
    const actions = mockActions();
    renderView(matchWith(), actions);
    fireEvent.click(screen.getByRole('button', { name: /BBB Playmaker/ }));
    expect(actions.setView).toHaveBeenCalledWith({ focus_player_id: 'BBB-10' });
  });

  it('filters the squads by text', () => {
    renderView(matchWith());
    fireEvent.change(screen.getByPlaceholderText('Name, number or position'), { target: { value: 'playmaker' } });
    expect(screen.queryByRole('button', { name: /AAA Striker/ })).toBeNull();
    expect(screen.getByRole('button', { name: /BBB Playmaker/ })).toBeTruthy();
  });

  it('stat card shows values from match.players', () => {
    const m = matchWith({ players: { 'AAA-9': stats() }, profile: { ...initialMatchState().profile, focus_player_id: 'AAA-9' } });
    const { container } = renderView(m);
    const stat = (k: string) => container.querySelector(`[data-stat="${k}"]`)?.textContent;
    expect(stat('fan.stat.touches')).toBe('14');
    expect(stat('fan.stat.passes')).toBe('7/9');
    expect(stat('fan.stat.accuracy')).toBe('78%');
    expect(stat('fan.stat.xg')).toBe('0.47');
    expect(stat('fan.stat.topSpeed')).toBe('33.4 km/h');
    expect(stat('fan.stat.distance')).toBe('1.83 km');
    expect(screen.getAllByText('Distance (on the ball and tracked runs)', { selector: 'span' }).length).toBeGreaterThan(0);
  });

  it('shows tracked distance with its label, speed bands and tackles won of tried', () => {
    const tracked = stats({
      distance_km: 10.84, walk_km: 2.85, jog_km: 6.91, run_km: 0.97, sprint_km: 0.08, physical_source: 'synthetic_tracking',
      tackles_won: 2, tackles_lost: 1, tackles_attempted: 3, tackle_success_pct: 66.7,
    });
    const m = matchWith({ players: { 'AAA-9': tracked }, profile: { ...initialMatchState().profile, focus_player_id: 'AAA-9' } });
    const { container } = renderView(m);
    const stat = (k: string) => container.querySelector(`[data-stat="${k}"]`)?.textContent;
    expect(stat('fan.stat.distance')).toBe('10.8 km');
    expect(screen.getAllByText('Distance covered', { selector: 'span' }).length).toBeGreaterThan(0);
    expect(screen.getByTestId('tracking-label').textContent).toBe('Estimated from synthetic tracking');
    expect(stat('fan.stat.tacklesOf')).toBe('2/3');
    expect(stat('fan.stat.sprints')).toBe('5');
    expect(stat('fan.stat.topSpeed')).toBe('33.4 km/h');
    const bands = screen.getByRole('img', { name: /Walk 2.85 km, jog 6.91 km, run 0.97 km, sprint 0.08 km/ });
    expect(bands.children).toHaveLength(4);
    expect(container.querySelector('[data-band="sprint"]')?.textContent).toBe('0.08');
  });

  it('labels the event estimate plainly and has no speed bands without tracking', () => {
    const m = matchWith({ players: { 'AAA-9': stats() }, profile: { ...initialMatchState().profile, focus_player_id: 'AAA-9' } });
    renderView(m);
    expect(screen.queryByTestId('tracking-label')).toBeNull();
    expect(screen.queryByTestId('speed-bands')).toBeNull();
  });

  it('shows a keeper with no touches yet but distance covered', () => {
    const keeper = stats({ touches: 0, distance_km: 2.1, physical_source: 'synthetic_tracking', walk_km: 1, jog_km: 1.1, run_km: 0, sprint_km: 0 });
    const m = matchWith({ players: { 'AAA-9': keeper }, profile: { ...initialMatchState().profile, focus_player_id: 'AAA-9' } });
    const { container } = renderView(m);
    expect(container.querySelector('[data-stat="fan.stat.distance"]')?.textContent).toBe('2.1 km');
  });

  it('says no touches yet without stats', () => {
    renderView(matchWith());
    expect(screen.getByText('No touches yet')).toBeTruthy();
  });

  it('player cam toggles the spotlight persona and back', () => {
    const actions = mockActions();
    const { unmount } = renderView(matchWith(), actions);
    fireEvent.click(screen.getByRole('button', { name: /Player cam/ }));
    expect(actions.setView).toHaveBeenCalledWith({ persona: 'player_spotlight', focus_player_id: 'AAA-9' });
    unmount();
    const on = matchWith({ profile: { ...initialMatchState().profile, persona: 'player_spotlight', focus_player_id: 'AAA-9' } });
    const actions2 = mockActions();
    renderView(on, actions2);
    fireEvent.click(screen.getByRole('button', { name: /Player cam/ }));
    expect(actions2.setView).toHaveBeenCalledWith({ persona: 'casual' });
  });

  it('lists only actions by the player and renders in Arabic', () => {
    const events = [
      event(1, 10, { player_id: 'AAA-9', type: 'shot', match_clock: '00:10' }),
      event(2, 20, { player_id: 'AAA-10', match_clock: '00:20' }),
      event(3, 30, { player_id: 'AAA-9', type: 'carry', match_clock: '00:30' }),
    ];
    renderView(matchWith({ events, lastEvent: events[2] }), mockActions(), 'ar');
    expect(screen.getAllByText('00:30').length).toBeGreaterThan(0);
    expect(screen.queryByText('00:20')).toBeNull();
    expect(document.documentElement.dir).toBe('rtl');
  });
});
