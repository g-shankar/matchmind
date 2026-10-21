import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import { cardForMoment, DEFAULT_PROFILE } from '../api/mockServer';
import { initialMatchState, type MatchViewState } from '../state/matchStore';
import type { MatchActions } from '../state/useMatch';
import { makeFixture } from '../test/fixture';
import { BroadcastOverlay } from './BroadcastOverlay';

afterEach(cleanup);

const actions = new Proxy({}, { get: () => vi.fn() }) as unknown as MatchActions;

function matchAt(clock_s: number, over: Partial<MatchViewState> = {}): MatchViewState {
  const fx = makeFixture();
  const card = cardForMoment(fx.moments[0], DEFAULT_PROFILE)!;
  const base = initialMatchState();
  return {
    ...base,
    status: 'demo',
    teams: fx.teams,
    crew: fx.crew,
    cards: [card],
    score: { home: 1, away: 0 },
    clock: '00:21',
    playback: { ...base.playback, clock_s },
    controlChaos: { home_control_pct: 58, away_control_pct: 42, chaos_index: 0, current_tempo: 'Controlled', rolling_momentum_home: 0 },
    ...over,
  };
}

const renderAt = (match: MatchViewState, lang = 'en') =>
  render(
    <I18nProvider lang={lang}>
      <BroadcastOverlay match={match} actions={actions} />
    </I18nProvider>,
  );

describe('BroadcastOverlay', () => {
  it('shows the lower third for an active card and hides it after its duration', () => {
    const { rerender } = renderAt(matchAt(22));
    expect(screen.getByTestId('lower-third').textContent).toContain('Goal for AAA');
    expect(screen.getByText('AI crew card · fact-checked template')).toBeTruthy();
    // show_at_s 20 + duration_s 8 -> gone at 29s.
    rerender(
      <I18nProvider lang="en">
        <BroadcastOverlay match={matchAt(29)} actions={actions} />
      </I18nProvider>,
    );
    expect(screen.queryByTestId('lower-third')).toBeNull();
  });

  it('scorebug shows short names and score from the payload', () => {
    renderAt(matchAt(22));
    const bug = screen.getByTestId('scorebug');
    expect(bug.textContent).toContain('AAA');
    expect(bug.textContent).toContain('BBB');
    expect(bug.textContent).toContain('1 - 0');
    expect(bug.textContent).toContain('58%');
  });

  it('highlights a favourite-side card in the favourite team colour', () => {
    const fx = makeFixture();
    const card = cardForMoment(fx.moments[0], { ...DEFAULT_PROFILE, favourite_team: 'AAA' })!;
    renderAt(matchAt(22, { cards: [card], profile: { ...DEFAULT_PROFILE, favourite_team: 'AAA' } }));
    expect(screen.getByText('Your team')).toBeTruthy();
  });

  it('producer toggle hides a layer', () => {
    renderAt(matchAt(22));
    const toggle = screen.getByRole('button', { name: 'Show or hide the Lower third layer' });
    expect(toggle.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(toggle);
    expect(screen.queryByTestId('lower-third')).toBeNull();
    expect(toggle.getAttribute('aria-pressed')).toBe('false');
  });

  it('labels the backdrop honestly and renders in Arabic', () => {
    renderAt(matchAt(22), 'ar');
    expect(screen.getByText('بث مباراة اصطناعية')).toBeTruthy();
    expect(screen.getByTestId('scorebug').textContent).toContain('AAA');
    expect(screen.queryByText(/4K/)).toBeNull();
  });
});
