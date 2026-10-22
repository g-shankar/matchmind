import type React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { Bookmark, OverlayCard } from '../api/contract';
import { DEFAULT_PROFILE, cardForMoment } from '../api/mockServer';
import { I18nProvider } from '../i18n';
import { initialMatchState, type MatchViewState } from '../state/matchStore';
import type { MatchActions } from '../state/useMatch';
import { event, makeFixture, state } from '../test/fixture';
import { NarrativeFeed } from './NarrativeFeed';
import { ControlChaosGauge } from './ControlChaosGauge';
import { MomentsList, compareMoments } from './MomentsList';
import { SplitView } from '../views/SplitView';

afterEach(cleanup);

const fixture = makeFixture();
const goal = cardForMoment(fixture.moments[0], DEFAULT_PROFILE)!;

const actionsMock = (over: Partial<MatchActions> = {}): MatchActions => ({
  togglePause: vi.fn(),
  setSpeed: vi.fn(),
  reset: vi.fn(),
  seek: vi.fn(),
  setView: vi.fn(),
  clearError: vi.fn(),
  getMoment: vi.fn().mockResolvedValue(null),
  loadRecap: vi.fn().mockResolvedValue(null),
  setSpoilers: vi.fn(),
  ask: vi.fn().mockResolvedValue({ ok: false, failure: 'unavailable' }),
  ...over,
});

const matchWith = (over: Partial<MatchViewState> = {}): MatchViewState => ({
  ...initialMatchState(DEFAULT_PROFILE),
  teams: fixture.teams,
  ...over,
});

const ui = (node: React.ReactNode, lang = 'en') => render(<I18nProvider lang={lang}>{node}</I18nProvider>);

describe('NarrativeFeed', () => {
  const replayCard: OverlayCard = {
    ...goal,
    card_id: 'R-1',
    moment_id: 'M-2',
    kind: 'better_option',
    slot: 'full_screen',
    headline: 'Should have squared it',
    evidence: [{ label: 'times_better', value: 2.4, unit: null, source_event_id: 'T-1-2' }],
    replay: {
      shot_event_id: 'T-1-2', shooter_id: 'AAA-9', teammate_id: 'AAA-10', shot_chance_quality: 0.1, alt_chance_quality: 0.4,
      pass_success: 0.8, alt_value: 0.32, times_better: 2.4, pass_distance_m: 9, nearest_marker_m: 4,
      shooter_pos: { x: 90, y: 30 }, teammate_pos: { x: 95, y: 36 }, defenders: [], keeper: null,
    },
  };

  it('shows evidence values and a replay button only on cards with a replay', () => {
    const onOpenReplay = vi.fn();
    const match = matchWith({ cards: [goal, replayCard], events: [event(2, 20, { match_clock: '00:20' })] });
    ui(<NarrativeFeed match={match} actions={actionsMock()} onOpenReplay={onOpenReplay} />);
    expect(screen.getByText('Goal for AAA')).toBeTruthy();
    const buttons = screen.getAllByRole('button', { name: /Show the replay/ });
    expect(buttons).toHaveLength(1);
    fireEvent.click(buttons[0]);
    expect(onOpenReplay).toHaveBeenCalledWith(replayCard);

    // Newest first: the replay card is on top, the goal card second.
    fireEvent.click(screen.getAllByRole('button', { name: /Evidence \(1\)/ })[1]);
    expect(screen.getByText('0.31')).toBeTruthy();
    expect(screen.getByText('Source event T-1-2')).toBeTruthy();
    expect(screen.getAllByText('00:20').length).toBeGreaterThan(0);
  });

  it('lists live events newest first on the second tab', () => {
    const shot = event(2, 20, { match_clock: '00:20', type: 'shot', metrics: { ...event(0, 0).metrics, progressive: false, chance_quality: 0.31 } });
    const match = matchWith({ events: [event(1, 10, { match_clock: '00:10' }), shot] });
    ui(<NarrativeFeed match={match} actions={actionsMock()} onOpenReplay={vi.fn()} />);
    expect(screen.getByText('Waiting for kick-off…')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: /Live events/ }));
    const rows = screen.getAllByRole('listitem');
    expect(rows[0].textContent).toContain('Shot');
    expect(rows[0].textContent).toContain('xG 0.31');
    expect(rows[1].textContent).toContain('Progressive pass');
  });
});

describe('ControlChaosGauge', () => {
  it('shows team short names and possession from state', () => {
    const s = state(600, {
      home: { ...state(0).home, possession_pct: 62 },
      away: { ...state(0).away, possession_pct: 38 },
      control_chaos: 0.4,
      tempo: 'Probing',
    });
    ui(<ControlChaosGauge match={matchWith({ state: s })} actions={actionsMock()} />);
    expect(screen.getAllByText('AAA').length).toBeGreaterThan(0);
    expect(screen.getAllByText('BBB').length).toBeGreaterThan(0);
    expect(screen.getByText('62%')).toBeTruthy();
    expect(screen.getByText('38%')).toBeTruthy();
    expect(screen.getAllByText('Probing').length).toBeGreaterThan(0);
  });

  it('renders in Arabic', () => {
    ui(<ControlChaosGauge match={matchWith({ state: state(60) })} actions={actionsMock()} />, 'ar');
    expect(screen.getByText('السيطرة مقابل الفوضى')).toBeTruthy();
  });
});

describe('NarrativeFeed corrections', () => {
  it('strikes through a ruled-out goal and labels it', () => {
    const match = matchWith({ cards: [goal], cue: { ...initialMatchState().cue, ruledOut: [goal.moment_id] } });
    ui(<NarrativeFeed match={match} actions={actionsMock()} onOpenReplay={vi.fn()} />);
    expect(screen.getByText('Ruled out by VAR')).toBeTruthy();
    expect(screen.getByText('Goal for AAA').className).toContain('line-through');
  });
});

describe('MomentsList', () => {
  const bm = (moment_id: string, kind: Bookmark['kind'], clock_s: number, title: string, period: number) =>
    ({ moment_id, kind, match_clock: '00:00', clock_s, title, period }) as Bookmark;

  it('seeks to eight seconds before the moment, in its period', () => {
    const actions = actionsMock();
    const match = matchWith({
      bookmarks: [bm('M-1', 'goal', 20, 'Goal for AAA', 1), bm('M-0', 'better_option', 5, 'Shot or pass', 1), bm('M-9', 'goal', 3000, 'Late winner', 2)],
      playback: { is_running: true, speed_multiplier: 10, clock_s: 30, match_clock: '00:00', period: 1, ended: false },
    });
    ui(<MomentsList match={match} actions={actions} />);
    fireEvent.click(screen.getByRole('button', { name: /Goal for AAA/ }));
    expect(actions.seek).toHaveBeenCalledWith(12, 1);
    fireEvent.click(screen.getByRole('button', { name: /Shot or pass/ }));
    expect(actions.seek).toHaveBeenLastCalledWith(0, 1);
    expect(screen.getByText('Should he have passed?')).toBeTruthy();
    // Upcoming goals are not spoiled.
    expect(screen.queryByText('Late winner')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Coming up/ }));
    expect(actions.seek).toHaveBeenLastCalledWith(2992, 2);
  });

  it('flags a goal ruled out by VAR only once the decision is in the past (no spoilers)', () => {
    const marks = [{ ...bm('M-1', 'goal', 20, 'Goal for AAA', 1), ruled_out: true }, bm('C-1', 'correction', 90, 'No goal! VAR rules out Nine', 1)];
    const at = (clock_s: number) =>
      matchWith({ bookmarks: marks, playback: { is_running: true, speed_multiplier: 10, clock_s, match_clock: '00:00', period: 1, ended: false } });
    ui(<MomentsList match={at(40)} actions={actionsMock()} />);
    expect(screen.queryByTestId('moment-ruled-out')).toBeNull();
    cleanup();
    ui(<MomentsList match={at(120)} actions={actionsMock()} />);
    expect(screen.getByTestId('moment-ruled-out').textContent).toBe('Ruled out by VAR');
  });

  it('orders by period before clock', () => {
    expect(compareMoments({ period: 2, clock_s: 2710 }, { period: 1, clock_s: 2760 })).toBeGreaterThan(0);
    expect(compareMoments({ clock_s: 100 }, { clock_s: 200 })).toBeLessThan(0);
  });
});

describe('SplitView', () => {
  it('loads the moment for both audiences and shows both headlines', async () => {
    const getMoment = vi.fn((id: string, persona: OverlayCard['persona'], language: OverlayCard['language']) =>
      Promise.resolve(cardForMoment(fixture.moments.find((m) => m.moment_id === id)!, { ...DEFAULT_PROFILE, persona, language })),
    );
    const actions = actionsMock({ getMoment: getMoment as unknown as MatchActions['getMoment'] });
    const match = matchWith({ cards: [goal], playback: { is_running: true, speed_multiplier: 10, clock_s: 30, match_clock: '00:00', period: 1, ended: false } });
    await act(async () => {
      ui(<SplitView match={match} actions={actions} />);
    });
    await waitFor(() => expect(screen.getByText('Finish from 0.31 xG')).toBeTruthy());
    expect(screen.getByText('Goal for AAA')).toBeTruthy();
    expect(getMoment).toHaveBeenCalledWith('M-1', 'casual', 'en');
    expect(getMoment).toHaveBeenCalledWith('M-1', 'tactical', 'en');
    expect(getMoment).toHaveBeenCalledWith('M-1', 'casual', 'es');
    expect(getMoment).toHaveBeenCalledWith('M-1', 'casual', 'ar');
    expect(screen.getByText('Gol de AAA')).toBeTruthy();
  });

  it('says so plainly when there is no moment yet', () => {
    ui(<SplitView match={matchWith()} actions={actionsMock()} />);
    expect(screen.getByText(/No key moment yet/)).toBeTruthy();
  });
});
