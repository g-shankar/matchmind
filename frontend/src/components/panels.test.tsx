import type React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import { resetDemoInsights, type InsightMode } from '../api/insights';
import { DEFAULT_PROFILE, cardForMoment } from '../api/mockServer';
import { InsightModeProvider } from '../state/useInsight';
import { initialMatchState, type MatchViewState } from '../state/matchStore';
import type { MatchActions } from '../state/useMatch';
import { makeFixture } from '../test/fixture';
import { basicStats, crewStatus, demoInsights, fetchStub } from '../test/insights';
import { CrewHealth, HEALTH_POLL_MS } from './CrewHealth';
import { Lab, MCP_TOOLS } from '../views/Lab';
import { SplitView } from '../views/SplitView';
import { compareNumbers, printedNumbers, sameEvidence } from './ClubHeart';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  resetDemoInsights();
});

const fixture = makeFixture();
const matchWith = (over: Partial<MatchViewState> = {}): MatchViewState => ({ ...initialMatchState(DEFAULT_PROFILE), teams: fixture.teams, ...over });
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
const ui = (node: React.ReactNode, { lang = 'en', mode = 'live' as InsightMode } = {}) =>
  render(
    <I18nProvider lang={lang}>
      <InsightModeProvider mode={mode}>{node}</InsightModeProvider>
    </I18nProvider>,
  );

describe('CrewHealth', () => {
  it('shows provider, orchestrator, rates with their counts and per-agent latency', async () => {
    vi.stubGlobal('fetch', fetchStub({ '/api/crew/status': crewStatus() }));
    ui(<CrewHealth match={matchWith()} />);
    await screen.findByText('analyst');
    const provider = screen.getByRole('list', { name: 'Who writes the text' });
    expect(within(provider).getByText('Fact-checked templates').closest('li')?.getAttribute('aria-current')).toBe('true');
    expect(within(provider).getAllByText('Off until deployed')).toHaveLength(2);
    expect(screen.getByText('Microsoft Agent Framework')).toBeTruthy();
    expect(screen.getByText('2.5% (3 of 120)')).toBeTruthy();
    expect(screen.getByText('0.0% (0 of 80)')).toBeTruthy();
    expect(screen.getByText(/no model is asked/)).toBeTruthy();
    expect(screen.getByText('1.9 ms')).toBeTruthy();
    expect(screen.getByText(/Azure AI Translator: off until deployed/)).toBeTruthy();
    expect(screen.getByRole('table', { name: /Latency per agent/ })).toBeTruthy();
  });

  it('says "none yet" instead of a rate when there is nothing to divide by', async () => {
    const base = crewStatus();
    vi.stubGlobal('fetch', fetchStub({ '/api/crew/status': { ...base, health: { ...base.health!, checks: 0, rejected_checks: 0, rejection_rate: null } } }));
    ui(<CrewHealth match={matchWith()} />);
    await screen.findByText('none yet (0 of 0)');
  });

  it('refreshes in place and keeps the last good numbers when a refresh fails', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let n = 0;
    vi.stubGlobal('fetch', fetchStub({ '/api/crew/status': () => (n++ === 0 ? new Response(JSON.stringify(crewStatus())) : new Response('{}', { status: 500 })) }));
    ui(<CrewHealth match={matchWith()} />);
    await screen.findByText('analyst');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(HEALTH_POLL_MS + 10);
    });
    expect(n).toBeGreaterThan(1);
    expect(screen.getByText('analyst')).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('in the offline demo shows the recorded crew mode and says what needs the server', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    ui(<CrewHealth match={matchWith({ crew: fixture.crew })} />, { mode: 'demo' });
    await screen.findByText(/no crew is running/);
    expect(screen.getByText('Fact-checked templates')).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('shows one message with a retry when the server fails', async () => {
    vi.stubGlobal('fetch', fetchStub({ '/api/crew/status': () => new Response('{}', { status: 503 }) }));
    ui(<CrewHealth match={matchWith()} />);
    expect((await screen.findByRole('alert')).textContent).toMatch(/could not be loaded/);
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy();
  });

  it('is fully translated in Arabic', async () => {
    vi.stubGlobal('fetch', fetchStub({ '/api/crew/status': crewStatus() }));
    ui(<CrewHealth match={matchWith()} />, { lang: 'ar' });
    await screen.findByText('صحة الطاقم');
    expect((await screen.findAllByText('متوقف حتى النشر')).length).toBe(3);
  });
});

describe('Under the hood (#lab)', () => {
  const live = () =>
    fetchStub({
      '/api/metrics': demoInsights().metrics,
      '/api/match/stats/basic': basicStats(),
      '/api/auto-eventing': demoInsights().auto_eventing,
      '/api/dataset': demoInsights().dataset,
    });

  it('live: registry with quality badges, stats, benchmark, downloads, MCP and outputs', async () => {
    vi.stubGlobal('fetch', live());
    ui(<Lab match={matchWith()} actions={actionsMock()} />);
    await screen.findByText('Pass distance');
    expect(screen.getAllByText('Heuristic').length).toBeGreaterThan(0);
    expect(screen.getByText('Half-space occupation')).toBeTruthy();
    // Filtering by quality.
    fireEvent.click(screen.getByRole('radio', { name: /Heuristic 1/ }));
    expect(screen.queryByText('Pass distance')).toBeNull();
    expect(screen.getByText('Pressure index')).toBeTruthy();
    // Basic stats.
    await screen.findByRole('table', { name: 'Basic stats per club' });
    expect(screen.getAllByText('83.3%').length).toBe(2);
    // Benchmark: label, confusion heatmap, baseline, pixel path (a dash where nothing could be scored).
    expect(screen.getByText('Detected from synthetic tracking, not video')).toBeTruthy();
    expect(screen.getByRole('table', { name: 'Confusion matrix' })).toBeTruthy();
    expect(screen.getByText('0.128')).toBeTruthy();
    expect(screen.getByText('Rendered synthetic top-down video, not broadcast footage')).toBeTruthy();
    expect(screen.getByLabelText(/Rendered synthetic top-down video of simulated players/)).toBeTruthy();
    // Downloads are real links for allow-listed ids.
    const zip = screen.getByRole('link', { name: 'Download MM-DEMO-001 as ZIP' });
    expect(zip.getAttribute('href')).toContain('/api/dataset/export?match_id=MM-DEMO-001&format=zip');
    expect(screen.queryByText('MM-GEN-01000')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Show 1 seeded matches/ }));
    expect(screen.getByText('MM-GEN-01000')).toBeTruthy();
    // MCP and broadcast outputs.
    expect(screen.getByText(`${window.location.origin}/mcp`)).toBeTruthy();
    expect(screen.getByText('matchmind-mcp')).toBeTruthy();
    for (const tool of MCP_TOOLS) expect(screen.getByText(tool)).toBeTruthy();
    expect(screen.getByRole('link', { name: /capture=1&persona=casual&lang=en#overlay/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Copy HTTP endpoint (this server)' })).toBeTruthy();
  });

  it('offline demo: recorded parts work, the rest says it needs the live server', async () => {
    vi.stubGlobal('fetch', fetchStub({ 'demo-insights.json': demoInsights() }));
    ui(<Lab match={matchWith()} actions={actionsMock()} />, { mode: 'demo' });
    await screen.findByText('Pass distance');
    expect(screen.getByText(/Works here: the metric registry/)).toBeTruthy();
    expect(screen.getByText(/Basic stats come from the live match server/)).toBeTruthy();
    expect(await screen.findByText('Detected from synthetic tracking, not video')).toBeTruthy();
    await screen.findByText('MM-DEMO-001');
    expect(screen.queryByRole('link', { name: /Download MM-DEMO-001/ })).toBeNull();
    expect(screen.getAllByText(/Downloads need the live match server/).length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: /demo=1#overlay/ })).toBeTruthy();
  });

  it('catch-up: no result or storyline anywhere on the page, even when the payloads carry them', async () => {
    const data = demoInsights().dataset;
    data.scenarios = { demo_storyline: 'Scripted demo storyline: home club 2-0 up, away win 3-2 in stoppage time.' };
    vi.stubGlobal('fetch', fetchStub({ '/api/metrics': demoInsights().metrics, '/api/match/stats/basic': basicStats(), '/api/auto-eventing': demoInsights().auto_eventing, '/api/dataset': data }));
    ui(<Lab match={matchWith({ profile: { ...DEFAULT_PROFILE, spoilers: false } })} actions={actionsMock()} />);
    await screen.findByText('MM-DEMO-001');
    await screen.findByRole('table', { name: 'Basic stats per club' });
    // Ranges like "0-100" or seeds "1000–1001" are fine; a scoreline between two clubs is not.
    expect(document.body.textContent).not.toMatch(/[A-Z]{3}\s?\d+\s?[-–]\s?\d+\s?[A-Z]{3}/);
    expect(document.getElementById('lab-data')?.textContent).toContain('NBR–HCY (Hidden)');
    expect(document.body.textContent).not.toMatch(/away win|2-0 up|2-3|3-2/);
    expect(screen.queryByRole('rowheader', { name: /goals/i })).toBeNull();
    expect(screen.getAllByText(/Hidden/).length).toBeGreaterThanOrEqual(2);
  });

  it('says plainly when the benchmark did not run', async () => {
    vi.stubGlobal('fetch', fetchStub({ '/api/metrics': demoInsights().metrics, '/api/dataset': demoInsights().dataset, '/api/match/stats/basic': basicStats() }));
    ui(<Lab match={matchWith()} actions={actionsMock()} />);
    await screen.findByText('The benchmark has not run for this match.');
  });

  it('shows skeletons while loading, never a blank wait', () => {
    vi.stubGlobal('fetch', () => new Promise(() => {}));
    ui(<Lab match={matchWith()} actions={actionsMock()} />);
    expect(screen.getAllByRole('status').length).toBeGreaterThanOrEqual(4);
  });

  it('renders in Arabic, right to left, with the section navigation labelled', async () => {
    vi.stubGlobal('fetch', live());
    ui(<Lab match={matchWith()} actions={actionsMock()} />, { lang: 'ar' });
    expect(screen.getByRole('navigation', { name: 'الأقسام' })).toBeTruthy();
    await screen.findByText('مرصود من تتبع اصطناعي، لا من الفيديو');
    expect(document.documentElement.dir).toBe('rtl');
  });
});

describe('Club-heart comparison', () => {
  const goal = cardForMoment(fixture.moments[0], DEFAULT_PROFILE)!;

  it('reads printed numbers and compares them as multisets', () => {
    const a = { ...goal, headline: 'AAA 2-1', body: 'A 0,31 chance.', why: '' };
    const b = { ...goal, headline: 'AAA 2-1', body: 'A 0.31 chance, 2 shots.', why: '' };
    expect(printedNumbers(a)).toEqual(['2', '1', '0.31']);
    expect(compareNumbers(a, b)).toEqual({ same: ['2', '1', '0.31'], onlyA: [], onlyB: ['2'] });
    expect(sameEvidence(a, b)).toEqual({ same: 1, total: 1 });
  });

  it('asks for the same moment once per club, shows priority, and highlights identical numbers', async () => {
    const getMoment = vi.fn((_id: string, persona: string, language: string, club?: string | null) => {
      const m = fixture.moments[0];
      return Promise.resolve(cardForMoment(m, { ...DEFAULT_PROFILE, persona: persona as 'casual', language: language as 'en', favourite_team: club ?? null }));
    });
    const match = matchWith({ cards: [goal], status: 'demo' });
    ui(<SplitView match={match} actions={actionsMock({ getMoment })} />);
    fireEvent.click(screen.getByRole('radio', { name: 'AAA fan vs BBB fan' }));
    await screen.findByText('Identical numbers in both versions (1 printed)');
    expect(getMoment).toHaveBeenCalledWith('M-1', 'casual', 'en', 'AAA');
    expect(getMoment).toHaveBeenCalledWith('M-1', 'casual', 'en', 'BBB');
    const aaa = screen.getByRole('region', { name: 'AAA fan' });
    const bbb = screen.getByRole('region', { name: 'BBB fan' });
    expect(within(aaa).getByText('Their club’s moment')).toBeTruthy();
    expect(within(bbb).getByText('The other club’s moment')).toBeTruthy();
    expect(within(aaa).getByText('Priority 100')).toBeTruthy();
    expect(within(bbb).getByText('Priority 95')).toBeTruthy();
    expect(aaa.querySelector('mark[data-same-number]')?.textContent).toBe('0.31');
    expect(screen.getByText(/Offline demo: the recording keeps one text per audience/)).toBeTruthy();
  });

  it('flags a number that only one club’s version prints', async () => {
    const getMoment = vi.fn((_id: string, _p: string, _l: string, club?: string | null) =>
      Promise.resolve({ ...goal, favourite_side: club === 'AAA', body: club === 'AAA' ? 'A 0.31 chance.' : 'A 0.32 chance.' }),
    );
    ui(<SplitView match={matchWith({ cards: [goal] })} actions={actionsMock({ getMoment })} />);
    fireEvent.click(screen.getByRole('radio', { name: 'AAA fan vs BBB fan' }));
    await screen.findByText('2 numbers appear in only one version');
    await waitFor(() => expect(document.querySelectorAll('mark[data-own-number]').length).toBe(2));
  });
});

describe('Studio feed', () => {
  it('puts "Show your working" on every story card, as a 44 px control', async () => {
    const { NarrativeFeed } = await import('./NarrativeFeed');
    const goal = cardForMoment(fixture.moments[0], DEFAULT_PROFILE)!;
    ui(<NarrativeFeed match={matchWith({ cards: [goal, { ...goal, card_id: 'c2', moment_id: 'M-9' }] })} actions={actionsMock()} onOpenReplay={vi.fn()} />);
    const buttons = screen.getAllByRole('button', { name: 'Show your working' });
    expect(buttons).toHaveLength(2);
    expect(buttons[0].className).toContain('min-h-[44px]');
    expect(buttons[0].getAttribute('aria-haspopup')).toBe('dialog');
  });
});
