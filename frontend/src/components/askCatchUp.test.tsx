import type React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { AskAnswer, AskResult, Bookmark } from '../api/contract';
import { DEFAULT_PROFILE } from '../api/mockServer';
import { I18nProvider } from '../i18n';
import { resetReadAloudForTests, voiceFor } from '../lib/speech';
import { initialMatchState, type MatchViewState } from '../state/matchStore';
import type { MatchActions } from '../state/useMatch';
import { makeFixture } from '../test/fixture';
import { AskStudio } from './AskStudio';
import { audit, fetchStub } from '../test/insights';
import { CatchUpBanner, CatchUpButton, ScoreValue, keyMoments } from './CatchUp';
import { ReadAloudCards, ReadAloudToggle } from './ReadAloud';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const fixture = makeFixture();

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

const matchWith = (over: Partial<MatchViewState> = {}, spoilers = true): MatchViewState => ({
  ...initialMatchState({ ...DEFAULT_PROFILE, spoilers }),
  teams: fixture.teams,
  ...over,
});

const ui = (node: React.ReactNode, lang = 'en') => render(<I18nProvider lang={lang}>{node}</I18nProvider>);

const answer = (over: Partial<AskAnswer> = {}): AskAnswer => ({
  status: 'answered',
  reason: null,
  intent: { kind: 'top_player', team: null, player_id: null, metric: 'xg' },
  understood_by: 'chip',
  answer: 'AAA Striker (AAA Town) leads for xG: 0.31.',
  language: 'en',
  text_language: 'en',
  rtl: false,
  as_of: { clock: '12:00', period: 1, clock_s: 720, ended: false },
  spoilers: true,
  evidence: [{ label: 'AAA Striker', label_key: 'value_xg', value: 0.31, unit: null, source_event_id: null }],
  moment_ids: ['M-1'],
  metric: null,
  produced_by: 'template',
  fact_check: { ok: true, reasons: [] },
  ...over,
});

describe('AskStudio', () => {
  it('sends a chip by id and shows the answer with its evidence and as-of clock', async () => {
    const ask = vi.fn().mockResolvedValue({ ok: true, answer: answer() } satisfies AskResult);
    ui(<AskStudio match={matchWith()} actions={actionsMock({ ask })} />);
    fireEvent.click(screen.getByRole('button', { name: 'Who has the most xG?' }));
    expect(ask).toHaveBeenCalledWith({ chip: 'top_xg' });
    const card = await screen.findByTestId('ask-answer');
    expect(card.textContent).toContain('leads for xG');
    expect(card.textContent).toContain('12:00');
    expect(screen.getByRole('list', { name: 'Numbers behind this answer' }).textContent).toContain('0.31');
  });

  it('says a question is too long (with the count) instead of cutting it, and trims before sending', async () => {
    const ask = vi.fn().mockResolvedValue({ ok: true, answer: answer() });
    ui(<AskStudio match={matchWith()} actions={actionsMock({ ask })} />);
    const box = screen.getByLabelText('Your question') as HTMLInputElement;
    fireEvent.change(box, { target: { value: `  ${'x'.repeat(250)}` } });
    expect(box.value).toHaveLength(252);
    expect(screen.getByTestId('ask-hint').textContent).toContain('up to 200');
    expect((screen.getByRole('button', { name: 'Ask' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.submit(box.closest('form')!);
    expect(ask).not.toHaveBeenCalled();
    // A long paste keeps its real length on the counter (round 2: it used to read "1000 of 200").
    fireEvent.change(box, { target: { value: 'x'.repeat(5000) } });
    expect(box.value).toHaveLength(5000);
    expect(document.body.textContent).toContain('5000 of 200 characters');
    fireEvent.change(box, { target: { value: '  who is fastest  ' } });
    expect(screen.queryByTestId('ask-hint')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    expect(ask).toHaveBeenCalledWith({ question: 'who is fastest' });
    await screen.findByTestId('ask-answer');
  });

  it('an empty or blank question gets a hint, not silence', () => {
    const ask = vi.fn();
    ui(<AskStudio match={matchWith()} actions={actionsMock({ ask })} />);
    const box = screen.getByLabelText('Your question');
    fireEvent.change(box, { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    expect(ask).not.toHaveBeenCalled();
    expect(screen.getByTestId('ask-hint').textContent).toContain('Type a question first');
  });

  it('"Should he have passed?" opens the replay of the moment it cites', async () => {
    const onOpenReplay = vi.fn();
    const ask = vi.fn().mockResolvedValue({ ok: true, answer: answer({ moment_ids: ['M-BO'] }) });
    const match = matchWith({ bookmarks: [{ moment_id: 'M-BO', kind: 'better_option', match_clock: '34:16', clock_s: 2056, period: 1, title: 'Should Asante have passed?' }] });
    ui(<AskStudio match={match} actions={actionsMock({ ask })} onOpenReplay={onOpenReplay} />);
    fireEvent.click(screen.getByRole('button', { name: 'Should he have passed?' }));
    await screen.findByTestId('ask-answer');
    expect(onOpenReplay).toHaveBeenCalledWith('M-BO');
    fireEvent.click(screen.getByRole('button', { name: /Show the replay/ }));
    expect(onOpenReplay).toHaveBeenCalledTimes(2);
  });

  it('renders answers as text, never as markup', async () => {
    const ask = vi.fn().mockResolvedValue({ ok: true, answer: answer({ answer: '<img src=x onerror=alert(1)> bold' }) });
    const { container } = ui(<AskStudio match={matchWith()} actions={actionsMock({ ask })} />);
    fireEvent.click(screen.getByRole('button', { name: 'Who has the most xG?' }));
    await screen.findByTestId('ask-answer');
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByTestId('ask-answer').textContent).toContain('<img src=x');
  });

  it('shows one plain sentence when the question cannot be answered', async () => {
    const ask = vi.fn().mockResolvedValue({ ok: false, failure: 'needs_live' });
    ui(<AskStudio match={matchWith()} actions={actionsMock({ ask })} />);
    fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'who is fastest' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/need the live server/);
  });

  it('shows refusals in the answer language, right to left for Arabic', async () => {
    const ask = vi.fn().mockResolvedValue({ ok: true, answer: answer({ status: 'refused', reason: 'off_topic', answer: 'أجيب فقط عن هذه المباراة.', language: 'ar', text_language: 'ar', rtl: true, evidence: [], moment_ids: [] }) });
    ui(<AskStudio match={matchWith()} actions={actionsMock({ ask })} />, 'ar');
    fireEvent.click(screen.getAllByRole('button')[2]);
    const card = await screen.findByTestId('ask-answer');
    expect(card.querySelector('p[dir="rtl"]')?.getAttribute('lang')).toBe('ar');
    expect(card.textContent).toContain('بلا إجابة');
  });

  it('leaves the score chip out in catch-up mode', () => {
    ui(<AskStudio match={matchWith({}, false)} actions={actionsMock()} />);
    expect(screen.queryByRole('button', { name: 'What is the score?' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Who has the most xG?' })).toBeTruthy();
  });

  it('"how we know" opens the claim audit for the cited moment', async () => {
    const ask = vi.fn().mockResolvedValue({ ok: true, answer: answer({ moment_ids: ['M-2'] }) });
    const fetch = vi.fn(fetchStub({ '/api/match/moment/M-2/audit': audit() }));
    vi.stubGlobal('fetch', fetch);
    try {
      ui(<AskStudio match={matchWith()} actions={actionsMock({ ask })} />);
      fireEvent.click(screen.getByRole('button', { name: 'Who has the most xG?' }));
      fireEvent.click(await screen.findByRole('button', { name: /How we know/ }));
      expect(await screen.findByRole('dialog')).toBeTruthy();
      await waitFor(() => expect(String(fetch.mock.calls[0]?.[0])).toMatch(/\/api\/match\/moment\/M-2\/audit$/));
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

const bm = (id: string, kind: Bookmark['kind'], clock_s: number, period = 1): Bookmark => ({
  moment_id: id,
  kind,
  match_clock: `${Math.floor(clock_s / 60)}:00`,
  clock_s,
  period,
  title: id,
});

describe('catch-up mode', () => {
  it('shows a placeholder, not a number, while the score is hidden', () => {
    ui(<>
      <ScoreValue value={null} />
      <ScoreValue value={2} />
    </>);
    expect(screen.getByTestId('score-hidden').textContent).toContain('?');
    expect(screen.getByText('2')).toBeTruthy();
  });

  it('the header button turns catch-up on with one call; the banner reveals with one call', () => {
    const setSpoilers = vi.fn();
    ui(<CatchUpButton match={matchWith()} actions={actionsMock({ setSpoilers })} />);
    fireEvent.click(screen.getByRole('button', { name: 'Catch up' }));
    expect(setSpoilers).toHaveBeenCalledTimes(1);
    expect(setSpoilers).toHaveBeenCalledWith(false);
    cleanup();
    ui(<CatchUpBanner match={matchWith({}, false)} actions={actionsMock({ setSpoilers })} onStory={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Reveal the score' }));
    expect(setSpoilers).toHaveBeenLastCalledWith(true);
    expect(setSpoilers).toHaveBeenCalledTimes(2);
  });

  it('no banner while the result is shown', () => {
    ui(<CatchUpBanner match={matchWith()} actions={actionsMock()} onStory={vi.fn()} />);
    expect(screen.queryByTestId('catchup-banner')).toBeNull();
  });

  it('key moments are past, spoiler-free and in match order', () => {
    const list = [bm('late', 'big_chance', 3000, 2), bm('goal', 'goal', 100), bm('b', 'better_option', 600), bm('a', 'card', 300), bm('speed', 'speed_burst', 50)];
    expect(keyMoments(list, { clock_s: 900, period: 1 }).map((b) => b.moment_id)).toEqual(['a', 'b']);
    expect(keyMoments(list, { clock_s: 3100, period: 2 }).map((b) => b.moment_id)).toEqual(['a', 'b', 'late']);
  });

  it('watches the key moments in turn, then jumps back to live', () => {
    vi.useFakeTimers();
    const seek = vi.fn();
    const match = matchWith(
      { bookmarks: [bm('a', 'card', 300), bm('b', 'big_chance', 600)], playback: { ...initialMatchState().playback, clock_s: 1200, period: 1 } },
      false,
    );
    ui(<CatchUpBanner match={match} actions={actionsMock({ seek })} onStory={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Watch the key moments' }));
    expect(seek).toHaveBeenLastCalledWith(292, 1);
    expect(screen.getByRole('status').textContent).toContain('Key moment 1 of 2');
    act(() => {
      vi.advanceTimersByTime(15000);
    });
    expect(seek).toHaveBeenLastCalledWith(592, 1);
    fireEvent.click(screen.getByRole('button', { name: 'Jump to live' }));
    expect(seek).toHaveBeenLastCalledWith(1200, 1);
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('opens the story so far', () => {
    const onStory = vi.fn();
    ui(<CatchUpBanner match={matchWith({}, false)} actions={actionsMock()} onStory={onStory} />);
    fireEvent.click(screen.getByRole('button', { name: 'Story so far' }));
    expect(onStory).toHaveBeenCalledTimes(1);
  });
});

// A stand-in for the browser's speechSynthesis with a chosen set of voices.
function fakeSpeech(langs: string[]) {
  const spoken: { text: string; lang: string }[] = [];
  const synth = {
    getVoices: () => langs.map((lang) => ({ lang, localService: true, default: false, name: lang, voiceURI: lang })),
    speak: (u: { text: string; lang: string }) => spoken.push({ text: u.text, lang: u.lang }),
    cancel: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };
  class Utterance {
    voice: unknown = null;
    lang = '';
    constructor(public text: string) {}
  }
  Object.defineProperty(window, 'speechSynthesis', { value: synth, configurable: true });
  vi.stubGlobal('SpeechSynthesisUtterance', Utterance);
  return spoken;
}

describe('read-aloud', () => {
  beforeEach(() => {
    localStorage.clear();
    resetReadAloudForTests();
  });
  afterEach(() => {
    delete (window as { speechSynthesis?: unknown }).speechSynthesis;
    vi.unstubAllGlobals();
    window.history.replaceState(null, '', '/');
  });

  it('picks a voice by language, preferring a local one', () => {
    const voices = [
      { lang: 'es-MX', localService: false, default: false },
      { lang: 'es-ES', localService: true, default: false },
      { lang: 'en-GB', localService: true, default: true },
    ];
    expect(voiceFor('es', voices)?.lang).toBe('es-ES');
    expect(voiceFor('ar', voices)).toBeNull();
    expect(voiceFor('zh-Hans', [{ lang: 'zh_CN', localService: true, default: false }])?.lang).toBe('zh_CN');
  });

  it('uses only on-device voices: a network voice is never chosen, even as the default', () => {
    // Some browsers offer voices that are synthesised by a remote service (localService false):
    // the text would leave the device, so read-aloud treats the language as having no voice.
    const remoteOnly = [
      { lang: 'fr-FR', localService: false, default: true },
      { lang: 'fr-CA', localService: false, default: false },
    ];
    expect(voiceFor('fr', remoteOnly)).toBeNull();
    expect(voiceFor('fr', [...remoteOnly, { lang: 'fr-BE', localService: true, default: false }])?.lang).toBe('fr-BE');
  });

  it('is off by default and hidden when the browser cannot speak', () => {
    ui(<ReadAloudToggle match={matchWith()} />);
    expect(screen.queryByRole('button')).toBeNull();
    fakeSpeech(['en-GB']);
    cleanup();
    ui(<ReadAloudToggle match={matchWith()} />);
    expect(screen.getByRole('button').getAttribute('aria-pressed')).toBe('false');
  });

  it('says plainly when there is no voice for the language (Arabic)', () => {
    fakeSpeech(['en-GB', 'es-ES']);
    ui(<ReadAloudToggle match={matchWith({ profile: { ...DEFAULT_PROFILE, language: 'ar' } })} />, 'ar');
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByRole('status').textContent).toMatch(/لا يوجد في هذا المتصفح صوت/);
  });

  it('reads new card headlines once switched on, and never in capture mode', () => {
    const spoken = fakeSpeech(['en-GB']);
    const card = { ...initialCard(), card_id: 'c1', headline: 'Big chance for AAA' };
    const before = matchWith({ cards: [] });
    const { rerender } = ui(<><ReadAloudToggle match={before} /><ReadAloudCards match={before} /></>);
    fireEvent.click(screen.getByRole('button'));
    const after = matchWith({ cards: [card], playback: { ...before.playback, clock_s: 20 } });
    rerender(<I18nProvider lang="en"><ReadAloudToggle match={after} /><ReadAloudCards match={after} /></I18nProvider>);
    expect(spoken).toEqual([{ text: 'Big chance for AAA', lang: 'en-GB' }]);
    cleanup();
    window.history.replaceState(null, '', '/?capture=1');
    ui(<ReadAloudToggle match={after} />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});

function initialCard() {
  return {
    card_id: 'c0',
    moment_id: 'M-0',
    kind: 'big_chance' as const,
    slot: 'lower_third' as const,
    priority: 80,
    show_at_s: 20,
    duration_s: 8,
    persona: 'casual' as const,
    language: 'en' as const,
    rtl: false,
    headline: '',
    body: '',
    why: '',
    tactical_tag: '',
    evidence: [],
    player_ids: [],
    team: null,
    favourite_side: null,
    produced_by: 'template' as const,
    fallback_reason: null,
    replay: null,
  };
}

