// First-time-user testing, round 2 (R2-01 .. R2-13): what a new viewer sees and can reach.
import type React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { AskAnswer, Bookmark, OverlayCard } from './api/contract';
import { DEFAULT_PROFILE, cardForMoment } from './api/mockServer';
import { I18nProvider } from './i18n';
import { initialMatchState, type MatchViewState } from './state/matchStore';
import type { MatchActions } from './state/useMatch';
import { makeFixture } from './test/fixture';
import { Shell } from './App';
import { AskStudio, TYPED_CAP, nextBetterOption } from './components/AskStudio';
import { MomentsList } from './components/MomentsList';
import { NarrativeFeed } from './components/NarrativeFeed';
import { LanguagePicker } from './components/LanguagePicker';

const fixture = makeFixture();

const actionsMock = (over: Partial<MatchActions> = {}): MatchActions => ({
  togglePause: vi.fn(),
  setSpeed: vi.fn(),
  reset: vi.fn(),
  seek: vi.fn(),
  setView: vi.fn(),
  clearError: vi.fn(),
  retryNow: vi.fn(),
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

const ui = (node: React.ReactNode, lang = 'en') => render(<I18nProvider lang={lang}>{node}</I18nProvider>);

const bm = (over: Partial<Bookmark> = {}): Bookmark => ({
  moment_id: 'M-1', kind: 'momentum_swing', match_clock: '13:38', clock_s: 818, period: 1, title: 'AAA take control', ...over,
});
const asante = bm({ moment_id: 'M-BO', kind: 'better_option', match_clock: '34:16', clock_s: 2056, title: 'Should Nine have passed?' });
const run = bm({ moment_id: 'M-UR', kind: 'unfound_run', match_clock: '61:12', clock_s: 3672, period: 2, title: "Ten's run went unseen" });
const many: Bookmark[] = [
  ...Array.from({ length: 30 }, (_, i) => bm({ moment_id: `M-${i}`, match_clock: `${10 + i}:00`, clock_s: (10 + i) * 60, title: `Momentum ${i}` })),
  asante,
  run,
];

const betterNone = (over: Partial<AskAnswer> = {}): AskAnswer => ({
  status: 'answered',
  reason: null,
  intent: { kind: 'better_option', team: null, player_id: null, metric: null },
  understood_by: 'chip',
  answer: "No 'should he have passed' moments yet at 00:35. Each one is marked in the moments list before it happens, so you can jump straight to it.",
  language: 'en',
  text_language: 'en',
  rtl: false,
  as_of: { clock: '00:35', period: 1, clock_s: 35, ended: false },
  spoilers: true,
  evidence: [],
  moment_ids: [],
  metric: null,
  produced_by: 'template',
  fact_check: { ok: true, reasons: [] },
  ...over,
});

beforeEach(() => {
  window.history.replaceState(null, '', '/');
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ source: 'file' }) }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('R2-01 "Should he have passed?" before the first one', () => {
  it('finds the next one from the jump list, never one already past', () => {
    expect(nextBetterOption(many, { clock_s: 35, period: 1 })?.moment_id).toBe('M-BO');
    expect(nextBetterOption(many, { clock_s: 2100, period: 1 })).toBeNull();
  });

  it('says when it comes and offers a jump instead of a dead end', async () => {
    const onJump = vi.fn();
    const ask = vi.fn().mockResolvedValue({ ok: true, answer: betterNone() });
    ui(<AskStudio match={matchWith({ bookmarks: many })} actions={actionsMock({ ask })} onJump={onJump} onOpenReplay={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Should he have passed?' }));
    const next = await screen.findByTestId('ask-upcoming');
    expect(next.textContent).toContain('34:16');
    fireEvent.click(screen.getByRole('button', { name: 'Jump to 34:16' }));
    expect(onJump).toHaveBeenCalledWith(asante);
  });

  it('after the moment, links to its replay (and no jump offer)', async () => {
    const onOpenReplay = vi.fn();
    const ask = vi.fn().mockResolvedValue({
      ok: true,
      answer: betterNone({ answer: 'Latest, at 34:16 ...', moment_ids: ['M-BO'], as_of: { clock: '40:00', period: 1, clock_s: 2400, ended: false } }),
    });
    ui(<AskStudio match={matchWith({ bookmarks: many })} actions={actionsMock({ ask })} onJump={vi.fn()} onOpenReplay={onOpenReplay} />);
    fireEvent.click(screen.getByRole('button', { name: 'Should he have passed?' }));
    await screen.findByTestId('ask-answer');
    expect(screen.queryByTestId('ask-upcoming')).toBeNull();
    expect(screen.getByRole('button', { name: /Show the replay/ })).toBeTruthy();
  });
});

describe('R2-02 key replays first', () => {
  // Past every moment, so the list shows their titles (upcoming ones stay spoiler-free).
  const late = { is_running: true, speed_multiplier: 1 as const, clock_s: 4000, match_clock: '66:40', period: 2, ended: false };
  it('puts the replay moments in their own row and folds the long list away', () => {
    const onJump = vi.fn();
    ui(<MomentsList match={matchWith({ bookmarks: many, playback: late })} actions={actionsMock()} onJump={onJump} />);
    const row = screen.getByTestId('key-replays');
    expect(row.textContent).toContain('Key replays');
    expect(row.querySelectorAll('button')).toHaveLength(2);
    expect(row.textContent).toContain('Should Nine have passed?');
    expect(screen.queryByText('Momentum 3')).toBeNull();
    const toggle = screen.getByRole('button', { name: /All moments/ });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(toggle);
    expect(screen.getByRole('button', { name: /Hide the full list/ }).getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('Momentum 3')).toBeTruthy();
    fireEvent.click(row.querySelectorAll('button')[0]);
    expect(onJump).toHaveBeenCalledWith(asante);
  });

  it('shows the full list straight away when a match has no replay moments', () => {
    ui(<MomentsList match={matchWith({ bookmarks: many.slice(0, 3), playback: late })} actions={actionsMock()} />);
    expect(screen.queryByTestId('key-replays')).toBeNull();
    expect(screen.getByText('Momentum 1')).toBeTruthy();
  });
});

describe('R2-03 About from the header', () => {
  it('opens About this demo as a dialog from the top bar', async () => {
    ui(<Shell match={matchWith()} actions={actionsMock()} />);
    fireEvent.click(screen.getByTestId('more-open'));
    fireEvent.click(screen.getByTestId('about-open'));
    const dialog = await screen.findByRole('dialog', { name: 'About this demo' });
    expect(dialog.textContent).toContain('synthetic data');
    expect(dialog.textContent).toContain('hackathon');
    fireEvent.keyDown(document.activeElement ?? dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});

describe('R2-05 replay label by the clock', () => {
  it('says the match is a synthetic replay at its speed, and pause is for everyone', async () => {
    ui(<Shell match={matchWith({ playback: { is_running: true, speed_multiplier: 10, clock_s: 60, match_clock: '01:00', period: 1, ended: false } })} actions={actionsMock()} />);
    const label = await screen.findByTestId('replay-speed');
    expect(label.textContent).toContain('Replay 10x');
    expect(label.getAttribute('title')).toContain('everyone watching');
    expect(screen.getByRole('button', { name: /Pause the replay \(pauses it for everyone watching\)/ })).toBeTruthy();
  });

  it('never calls the live stream a replay', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ source: 'eventhubs' }) }));
    ui(<Shell match={matchWith()} actions={actionsMock()} />);
    await screen.findAllByText('Live feed');
    expect(screen.queryByTestId('replay-speed')).toBeNull();
  });
});

describe('R2-06 audience change', () => {
  const card: OverlayCard = cardForMoment(fixture.moments[0], DEFAULT_PROFILE)!;

  it('says who each story is written for and that "Why it matters" is shared', () => {
    ui(<NarrativeFeed match={matchWith({ cards: [card] })} actions={actionsMock()} onOpenReplay={vi.fn()} />);
    expect(screen.getByTestId('card-voice').textContent).toBe('Written for: Fan');
    if (card.why) expect(document.body.textContent).toContain('same for everyone');
    expect(screen.queryByTestId('audience-note')).toBeNull(); // nothing on first load
  });

  it('shows a short note when the audience changes, then lets it go', () => {
    vi.useFakeTimers();
    const view = (m: MatchViewState) => (
      <I18nProvider lang="en">
        <NarrativeFeed match={m} actions={actionsMock()} onOpenReplay={vi.fn()} />
      </I18nProvider>
    );
    const m = matchWith({ cards: [card] });
    const r = render(view(m));
    r.rerender(view({ ...m, profile: { ...m.profile, persona: 'tactical' }, cards: [{ ...card, persona: 'tactical' }] }));
    expect(screen.getByTestId('audience-note').textContent).toContain('Now explaining for: Analyst');
    expect(screen.getByTestId('card-voice').textContent).toBe('Written for: Analyst');
    act(() => {
      vi.advanceTimersByTime(9000);
    });
    expect(screen.queryByTestId('audience-note')).toBeNull();
  });
});

describe('R2-07 R2-09 R2-10 R2-13 small fixes', () => {
  it('every speed button is at least 44 by 44', () => {
    ui(<Shell match={matchWith()} actions={actionsMock()} />);
    fireEvent.click(screen.getByTestId('more-open'));
    for (const group of screen.getAllByRole('radiogroup', { name: 'Playback speed' })) {
      for (const b of group.querySelectorAll('button')) expect(b.className).toMatch(/min-h-\[44px\] min-w-\[44px\]/);
    }
  });

  it('shows a visible loading label and the scorebug shape before the first snapshot', () => {
    ui(<Shell match={{ ...matchWith(), teams: null }} actions={actionsMock()} />);
    expect(screen.getByTestId('loading-label').textContent).toBe('Loading match…');
    expect(screen.getByTestId('scoreline-placeholder')).toBeTruthy();
  });

  it('keeps the crew pill on one line', () => {
    ui(<Shell match={matchWith({ crew: fixture.crew })} actions={actionsMock()} />, 'es');
    fireEvent.click(screen.getByTestId('more-open'));
    expect(screen.getByText('Equipo IA: modo plantilla').className).toContain('whitespace-nowrap');
  });

  it('sizes the language box to the chosen language, not its longest option', () => {
    ui(
      <LanguagePicker
        value="ar"
        onChange={vi.fn()}
        languages={[
          { code: 'ar', name: 'العربية', source: 'studio', available: true, reason: null },
          { code: 'pt', name: 'Português', source: 'translator', available: false, reason: 'off' },
        ] as never}
      />,
      'ar',
    );
    expect(screen.getByTestId('language-picker').className).toContain('[field-sizing:content]');
  });
});

describe('R2-11 Ask counter', () => {
  it('shows the real length of a long paste, and says when it was cut', () => {
    ui(<AskStudio match={matchWith()} actions={actionsMock()} />);
    const box = screen.getByLabelText('Your question') as HTMLInputElement;
    fireEvent.change(box, { target: { value: 'x'.repeat(5000) } });
    expect(document.body.textContent).toContain('5000 of 200 characters');
    fireEvent.change(box, { target: { value: 'x'.repeat(TYPED_CAP + 50) } });
    expect(box.value).toHaveLength(TYPED_CAP);
    expect(document.body.textContent).toContain(`${TYPED_CAP}+ of 200 characters`);
  });
});

describe('R2-14 replay rounding', () => {
  it('shows chance values with two decimals, like the crew text (0.20 next to 0.24)', async () => {
    const { evidenceText } = await import('./components/ReplayCard');
    const i18n = { num: (v: number, d = 0) => v.toFixed(d), t: (k: string) => k };
    expect(evidenceText({ label: 'Pass expected value', label_key: 'alt_value', value: 0.2, unit: 'xG', source_event_id: null }, i18n)).toBe('0.20');
    expect(evidenceText({ label: 'Teammate chance xG', label_key: 'alt_xg', value: 0.24, unit: 'xG', source_event_id: null }, i18n)).toBe('0.24');
    expect(evidenceText({ label: 'Pass vs shot', label_key: 'times_better', value: 4, unit: 'x', source_event_id: null }, i18n)).toBe('4');
  });
});

describe('studio panels', () => {
  it('moves between tabs with the arrow keys, Home and End', () => {
    ui(<Shell match={matchWith()} actions={actionsMock()} />);
    const list = screen.getByRole('tablist', { name: 'Studio panels' });
    expect(screen.getByTestId('panel-tab-story').getAttribute('aria-selected')).toBe('true');
    fireEvent.keyDown(list, { key: 'ArrowRight' });
    expect(screen.getByTestId('panel-tab-ask').getAttribute('aria-selected')).toBe('true');
    fireEvent.keyDown(list, { key: 'End' });
    expect(screen.getByTestId('panel-tab-stats').getAttribute('aria-selected')).toBe('true');
    fireEvent.keyDown(list, { key: 'Home' });
    expect(screen.getByTestId('panel-tab-story').getAttribute('aria-selected')).toBe('true');
  });

  it('lists matches, tour, source and About in the More menu', () => {
    ui(<Shell match={matchWith()} actions={actionsMock()} />);
    fireEvent.click(screen.getByTestId('more-open'));
    const menu = screen.getByTestId('more-menu');
    for (const id of ['more-matches', 'more-tour', 'about-open']) expect(menu.querySelector(`[data-testid="${id}"]`)).toBeTruthy();
  });
});
