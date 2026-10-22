import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

afterEach(cleanup);
import { I18nProvider } from '../i18n';
import { initialMatchState, type MatchViewState } from '../state/matchStore';
import type { MatchActions } from '../state/useMatch';
import type { OverlayCard, PlayerStats } from '../api/contract';
import { makeFixture, state } from '../test/fixture';
import { MyMatch, perspectiveScore } from './MyMatch';

const teams = makeFixture().teams;
const base = initialMatchState();

const mockActions = () =>
  ({
    togglePause: vi.fn(),
    setSpeed: vi.fn(),
    reset: vi.fn(),
    seek: vi.fn(),
    setView: vi.fn(),
    clearError: vi.fn(),
    retryNow: vi.fn(),
    getMoment: vi.fn(),
    loadRecap: vi.fn(),
    setSpoilers: vi.fn(),
    ask: vi.fn().mockResolvedValue({ ok: false, failure: 'unavailable' }),
  }) as unknown as MatchActions;

const matchWith = (over: Partial<MatchViewState> = {}, profile: Partial<MatchViewState['profile']> = {}): MatchViewState => ({
  ...base,
  teams,
  score: { home: 2, away: 1 },
  state: state(600, { score_home: 2, score_away: 1, xg_home: 1.2, xg_away: 0.4 }),
  ...over,
  profile: { ...base.profile, ...profile },
});

const renderView = (m: MatchViewState, actions = mockActions(), lang = 'en') =>
  render(
    <I18nProvider lang={lang}>
      <MyMatch match={m} actions={actions} />
    </I18nProvider>,
  );

const card = (id: string, team: string, over: Partial<OverlayCard> = {}): OverlayCard => ({
  card_id: `c-${id}`, moment_id: id, kind: 'big_chance', slot: 'side_panel', priority: 50, show_at_s: 100, duration_s: 10,
  persona: 'casual', language: 'en', rtl: false, headline: `Headline ${id}`, body: '', why: '', tactical_tag: '', evidence: [],
  player_ids: [], team, favourite_side: null, produced_by: 'template', fallback_reason: null, replay: null, ...over,
});

describe('MyMatch', () => {
  it('favourite pick calls setView with the team_id', () => {
    const actions = mockActions();
    renderView(matchWith(), actions);
    fireEvent.click(screen.getByRole('button', { name: /BBB Town/ }));
    expect(actions.setView).toHaveBeenCalledWith({ favourite_team: 'BBB' });
    fireEvent.click(screen.getByRole('button', { name: 'No favourite' }));
    expect(actions.setView).toHaveBeenCalledWith({ favourite_team: null });
  });

  it('shows the score from the favourite perspective, flipped for the away team', () => {
    expect(perspectiveScore({ home: 2, away: 1 }, 'away')).toEqual({ us: 1, them: 2 });
    renderView(matchWith({}, { favourite_team: 'BBB' }));
    expect(screen.getByText('Your club: BBB Town')).toBeTruthy();
    expect(screen.getByTestId('perspective-score').getAttribute('aria-label')).toBe('BBB Town 1, AAA Town 2');
  });

  it('home favourite keeps the score as is', () => {
    renderView(matchWith({}, { favourite_team: 'AAA' }));
    expect(screen.getByTestId('perspective-score').getAttribute('aria-label')).toBe('AAA Town 2, BBB Town 1');
  });

  it('single-metric choice calls setView with focus_metric', () => {
    const actions = mockActions();
    renderView(matchWith(), actions);
    fireEvent.click(screen.getByRole('radio', { name: 'Momentum' }));
    expect(actions.setView).toHaveBeenCalledWith({ focus_metric: 'momentum' });
    fireEvent.click(screen.getByRole('radio', { name: 'Off' }));
    expect(actions.setView).toHaveBeenCalledWith({ focus_metric: null });
  });

  it('top_speed tile shows the max from players', () => {
    const p = (id: string, team: string, top: number) => ({ player_id: id, team, top_speed_kmh: top }) as PlayerStats;
    const players = { 'AAA-9': p('AAA-9', 'AAA', 31.2), 'BBB-10': p('BBB-10', 'BBB', 34.6), 'AAA-10': p('AAA-10', 'AAA', 29) };
    renderView(matchWith({ players }, { focus_metric: 'top_speed' }));
    const tile = screen.getByTestId('metric-top-speed');
    expect(tile.textContent).toContain('34.6');
    expect(tile.textContent).toContain('BBB Playmaker');
    expect(screen.getByText('Alerts are sent by the crew when this number moves')).toBeTruthy();
  });

  it('lists the favourite side cards first', () => {
    const cards = [card('M-1', 'BBB'), card('M-2', 'AAA'), card('M-3', 'BBB', { favourite_side: true })];
    renderView(matchWith({ cards }, { favourite_team: 'BBB' }));
    const heads = screen
      .getAllByRole('heading', { level: 3 })
      .map((h) => h.textContent)
      .filter((x) => x?.startsWith('Headline'));
    expect(heads).toEqual(['Headline M-3', 'Headline M-1', 'Headline M-2']);
  });

  it('renders in Arabic', () => {
    renderView(matchWith({}, { favourite_team: 'AAA', focus_metric: 'pressure' }), mockActions(), 'ar');
    expect(screen.getByText('ناديك: AAA Town')).toBeTruthy();
  });
});

describe('MyMatch club styles in the interface language', () => {
  const styled = (style: string) => Object.fromEntries(Object.entries(teams).map(([id, tm]) => [id, { ...tm, style }]));

  it('shows a known roster style in French', () => {
    renderView(matchWith({ teams: styled('Possession 4-3-3, patient build-up through the half-spaces') }), mockActions(), 'fr');
    expect(screen.getAllByText('Possession en 4-3-3, construction patiente par les demi-espaces').length).toBeGreaterThan(0);
    expect(screen.queryByText(/patient build-up/)).toBeNull();
  });

  it('shows an unknown style as English and marks it as English', () => {
    renderView(matchWith({ teams: styled('Low block 5-4-1') }), mockActions(), 'ja');
    const el = screen.getAllByText('Low block 5-4-1')[0];
    expect(el.getAttribute('lang')).toBe('en');
  });
});
