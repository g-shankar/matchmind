import type React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { Bookmark, OverlayCard } from './api/contract';
import { DEFAULT_PROFILE, cardForMoment } from './api/mockServer';
import { I18nProvider } from './i18n';
import { TOASTS } from './i18n/toasts';
import { initialMatchState, type MatchViewState } from './state/matchStore';
import type { MatchActions } from './state/useMatch';
import { makeFixture } from './test/fixture';
import { Shell } from './App';

const fixture = makeFixture();
const goal = cardForMoment(fixture.moments[0], DEFAULT_PROFILE)!;

const special: OverlayCard = {
  ...goal,
  card_id: 'R-1',
  moment_id: 'M-BO',
  kind: 'better_option',
  slot: 'full_screen',
  headline: 'Missed assist chance for Nine',
  evidence: [
    { label: 'Teammate chance quality', value: 0.24, unit: 'xG', source_event_id: 'T-1-2' },
    { label: 'Times better', value: 4, unit: 'x', source_event_id: 'T-1-2' },
  ],
  replay: {
    shot_event_id: 'T-1-2', shooter_id: 'AAA-9', teammate_id: 'AAA-10', shot_chance_quality: 0.05, alt_chance_quality: 0.238,
    pass_success: 0.83, alt_value: 0.198, times_better: 4.0, pass_distance_m: 16.4, nearest_marker_m: 9.5,
    shooter_pos: { x: 90, y: 30 }, teammate_pos: { x: 95, y: 36 }, defenders: [], keeper: null,
  },
};

const bookmark = (over: Partial<Bookmark> = {}): Bookmark => ({
  moment_id: 'M-BO', kind: 'better_option', match_clock: '34:16', clock_s: 2056, period: 1, title: 'Should Nine have passed?', ...over,
});

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
  status: 'live',
  teams: fixture.teams,
  ...over,
});

const shell = (match: MatchViewState, actions: MatchActions, lang = 'en') => {
  const view = (m: MatchViewState) => (
    <I18nProvider lang={lang}>
      <Shell match={m} actions={actions} />
    </I18nProvider>
  );
  const r = render(view(match));
  return { ...r, update: (m: MatchViewState) => r.rerender(view(m)) };
};

beforeEach(() => {
  window.history.replaceState(null, '', '/');
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ source: 'file' }) }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('jumping to a moment', () => {
  it('on a paused match lands on the moment itself, keeps the pitch in view and opens the replay', async () => {
    const getMoment = vi.fn().mockResolvedValue(special);
    const actions = actionsMock({ getMoment });
    const paused = matchWith({
      bookmarks: [bookmark()],
      playback: { is_running: false, speed_multiplier: 1, clock_s: 600, match_clock: '10:00', period: 1, ended: false },
    });
    const { update } = shell(paused, actions);
    fireEvent.click(screen.getByRole('button', { name: /34:16/ }));
    expect(actions.seek).toHaveBeenCalledWith(2057, 1);
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    expect(screen.getByTestId('moment-focus').textContent).toContain('Jumped to');
    // The server's snapshot arrives: the clock is now past the moment, so its card is fetched.
    update({ ...paused, playback: { ...paused.playback, clock_s: 2057, match_clock: '34:17' } });
    await waitFor(() => expect(getMoment).toHaveBeenCalledWith('M-BO', 'casual', 'en'));
    const dialog = await screen.findByRole('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.textContent).toContain('Missed assist chance for Nine');
    // The story uses the evidence's own rounding: 0.24 and 4, never 0.238 next to 0.24.
    expect(dialog.textContent).not.toContain('0.238');
    expect(dialog.textContent).toContain('0.24');
    // The focused card is the one picked, with its own "Show your working".
    expect(screen.getByTestId('moment-focus').textContent).toContain('Missed assist chance for Nine');
  });

  it('while playing, plays into the moment and shows its card when it lands in the feed', async () => {
    const actions = actionsMock();
    const b = bookmark({ moment_id: 'M-1', kind: 'goal', match_clock: '00:20', clock_s: 20, title: 'Goal for AAA' });
    const playing = matchWith({ bookmarks: [b], playback: { is_running: true, speed_multiplier: 1, clock_s: 30, match_clock: '00:30', period: 1, ended: false } });
    const { update } = shell(playing, actions);
    fireEvent.click(screen.getByRole('button', { name: /Goal for AAA/ }));
    expect(actions.seek).toHaveBeenCalledWith(12, 1);
    update({ ...playing, playback: { ...playing.playback, clock_s: 12 } });
    expect(screen.getByTestId('moment-focus').textContent).toContain('Playing into the moment');
    update({ ...playing, cards: [goal], playback: { ...playing.playback, clock_s: 21 } });
    await waitFor(() => expect(screen.getByTestId('moment-focus').textContent).toContain('Goal for AAA'));
    expect(screen.queryByRole('dialog')).toBeNull(); // not a replay moment
  });
});

describe('replay modal', () => {
  it('takes focus, keeps Tab inside, closes on Esc and on the Back button', async () => {
    const actions = actionsMock({ getMoment: vi.fn().mockResolvedValue(special) });
    const m = matchWith({ bookmarks: [bookmark()], playback: { is_running: false, speed_multiplier: 1, clock_s: 3000, match_clock: '50:00', period: 2, ended: false } });
    shell(m, actions);
    fireEvent.click(screen.getByRole('button', { name: /34:16/ }));
    const dialog = await screen.findByRole('dialog');
    // The modal moves focus in an effect after it opens; wait for it rather than racing it.
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
    expect(dialog.getAttribute('aria-labelledby')).toBe('replay-R-1');
    fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    // Open again from the focused card, then use the browser Back button.
    fireEvent.click(screen.getAllByRole('button', { name: /Show the replay|Watch the replay|replay/i })[0]);
    await screen.findByRole('dialog');
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});

describe('first visit', () => {
  it('at full time offers to watch from kick-off or read the recap', () => {
    const actions = actionsMock();
    shell(matchWith({ playback: { is_running: false, speed_multiplier: 60, clock_s: 5700, match_clock: '90:00', period: 2, ended: true } }), actions);
    expect(screen.getByTestId('full-time-banner')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Watch from kick-off' }));
    expect(actions.reset).toHaveBeenCalled();
    expect(screen.queryByTestId('full-time-banner')).toBeNull();
  });

  it('calls a bundled match a synthetic replay, never "live engine"', async () => {
    shell(matchWith(), actionsMock());
    expect((await screen.findAllByText('Synthetic replay')).length).toBeGreaterThan(0);
    expect(screen.queryByText(/live engine/i)).toBeNull();
    expect(document.body.textContent).not.toMatch(/Your AI studio crew/);
  });

  it('labels the audience picker apart from the view tabs', () => {
    shell(matchWith(), actionsMock());
    const audience = screen.getByRole('radiogroup', { name: "I'm a" });
    expect(audience.querySelectorAll('[role="radio"]')).toHaveLength(3);
    const nav = screen.getByRole('navigation', { name: 'Views' });
    expect(nav.contains(audience)).toBe(false);
  });

  it('shows rate-limit toasts in the page language', () => {
    shell(matchWith({ error: 'Changing the view too fast. Wait a moment and try again.', errorCode: 'view_too_fast', profile: { ...DEFAULT_PROFILE, language: 'ar' } }), actionsMock(), 'ar');
    expect(screen.getByRole('alert').textContent).toBe(TOASTS.ar.view_too_fast);
  });

  it('has an About this demo footer that says the data is synthetic and links to how it works', () => {
    shell(matchWith(), actionsMock());
    const footer = screen.getByRole('contentinfo');
    expect(footer.textContent).toContain('About this demo');
    expect(footer.textContent).toContain('synthetic data');
    fireEvent.click(screen.getByRole('button', { name: /How it works/ }));
    expect(window.location.hash).toBe('#lab');
  });

  it('keeps the score home-away on a right-to-left page', () => {
    shell(matchWith({ score: { home: 2, away: 1 }, profile: { ...DEFAULT_PROFILE, language: 'ar' } }), actionsMock(), 'ar');
    const strip = screen.getByText('AAA').parentElement!;
    expect(strip.getAttribute('dir')).toBe('ltr');
    expect(strip.textContent?.startsWith('AAA')).toBe(true);
  });
});

export type { React };
