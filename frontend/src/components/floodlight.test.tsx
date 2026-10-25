import type React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import { resetDemoInsights } from '../api/insights';
import { InsightModeProvider } from '../state/useInsight';
import type { Bookmark } from '../api/contract';
import { CrewRelayToggle, DESKS, buildRundown } from './CrewRelay';
import { MomentRail, railMarks, ribbonBars } from './MomentRail';
import { REPO_ARCHITECTURE_URL, StudioTour } from './StudioTour';
import { audit, fetchStub } from '../test/insights';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetDemoInsights();
});

const ui = (node: React.ReactNode, lang = 'en') =>
  render(
    <I18nProvider lang={lang}>
      <InsightModeProvider mode="live">{node}</InsightModeProvider>
    </I18nProvider>,
  );

const bm = (over: Partial<Bookmark>): Bookmark => ({ moment_id: 'x', kind: 'goal', match_clock: '10:00', clock_s: 600, period: 1, title: 'Goal', ...over });

describe('crew rundown', () => {
  it('lists the five desks in order, timing only what the trace logged', () => {
    const rows = buildRundown(audit(), 'full_screen', (k) => k);
    expect(rows.map((r) => r.desk)).toEqual([...DESKS]);
    expect(rows[0]).toMatchObject({ ms: 0.13, state: 'ok' });
    expect(rows[2]).toMatchObject({ ms: 12.5, state: 'fallback', why: 'casual/en: template' });
    // No analyst step in the trace: derived from the explanation, never given a made-up time.
    expect(rows[1]).toMatchObject({ ms: null, state: 'template' });
    expect(rows[3].out.vars.slot).toBe('relay.slot.full_screen');
    expect(rows[4].out.vars).toEqual({ ok: 3, n: 3 });
  });

  it('says a step was not logged when the recording has no trace', () => {
    const rows = buildRundown(audit({ trace: [] }), null, (k) => k);
    expect(rows.every((r) => r.ms === null)).toBe(true);
    expect(rows[0].state).toBe('unknown');
    expect(rows[3].out.key).toBe('relay.out.producerNone');
  });

  it('marks a failed number check', () => {
    const a = audit({ trace: [] });
    a.renderings[1] = { ...a.renderings[1], fact_check: { ok: false, reasons: ['x'] } };
    expect(buildRundown(a, null, (k) => k)[4]).toMatchObject({ state: 'rejected', out: { vars: { ok: 2, n: 3 } } });
  });

  it('opens in place from the card, with hand-offs and the stats-engine footer', async () => {
    vi.stubGlobal('fetch', fetchStub({ '/audit': audit() }));
    ui(<CrewRelayToggle momentId="M-2" slot="full_screen" />);
    fireEvent.click(screen.getByRole('button', { name: 'Crew relay' }));
    const rundown = await screen.findByTestId('crew-rundown');
    expect(within(rundown).getAllByRole('listitem')).toHaveLength(5);
    expect(rundown.textContent).toContain('hands to Analyst');
    expect(rundown.textContent).toContain('Put it on air as: full-screen replay');
    expect(screen.getByTestId('rundown-footer').textContent).toBe('Every number comes from the stats engine.');
  });

  it('speaks Arabic', async () => {
    vi.stubGlobal('fetch', fetchStub({ '/audit': audit() }));
    ui(<CrewRelayToggle momentId="M-2" />, 'ar');
    fireEvent.click(screen.getByRole('button', { name: 'جدول الطاقم' }));
    expect((await screen.findByTestId('rundown-footer')).textContent).toBe('كل رقم يأتي من محرك الإحصاءات.');
  });
});

describe('moment rail', () => {
  const marks = [
    bm({ moment_id: 'g', kind: 'goal', clock_s: 2700 }),
    bm({ moment_id: 's', kind: 'rocket_shot', clock_s: 1350, title: 'Rocket' }),
    bm({ moment_id: 'c', kind: 'card', clock_s: 100 }),
    bm({ moment_id: 'v', kind: 'goal', clock_s: 300, ruled_out: true }),
  ];

  it('keeps goals and shots, ordered, placed along the match', () => {
    const m = railMarks(marks, true)!;
    expect(m.map((x) => [x.b.moment_id, x.type, x.at])).toEqual([
      ['s', 'shot', 25],
      ['g', 'goal', 50],
    ]);
  });

  it('never shows a goal or shot the match clock has not reached', () => {
    expect(railMarks(marks, true, { clock_s: 2000, period: 1 })!.map((x) => x.b.moment_id)).toEqual(['s']);
    ui(<MomentRail bookmarks={marks} spoilers nowS={2000} nowPeriod={1} onJump={() => undefined} />);
    expect(screen.queryByRole('button', { name: /^Goal at/ })).toBeNull();
  });

  it('seeks through the jump it is given', () => {
    const onJump = vi.fn();
    ui(<MomentRail bookmarks={marks} spoilers nowS={5400} nowPeriod={2} onJump={onJump} />);
    fireEvent.click(screen.getByRole('button', { name: /^Shot at/ }));
    expect(onJump).toHaveBeenCalledWith(marks[1]);
  });

  const history = [
    { clock_s: 60, momentum: 40 },
    { clock_s: 120, momentum: -30 },
    { clock_s: 4000, momentum: 90 },
  ];
  const colors = { home: '#1155ee', away: '#ee8811' };

  it('withholds every mark, shape and the momentum ribbon in catch-up mode', () => {
    expect(railMarks(marks, false)).toBeNull();
    const { container } = ui(<MomentRail bookmarks={marks} spoilers={false} nowS={200} history={history} colors={colors} onJump={() => undefined} />);
    expect(screen.getByTestId('moment-rail-hidden')).toBeTruthy();
    expect(container.querySelectorAll('button, [data-mark]')).toHaveLength(0);
    expect(container.textContent).not.toMatch(/Goal at|Shot at|GoalShot/);
    expect(container.querySelector('[data-testid="momentum-ribbon"]')).toBeNull();
  });

  it('draws momentum in team colours, never past the playback clock', () => {
    const bars = ribbonBars(history, 200, 5400);
    expect(bars.map((b) => b.m)).toEqual([40, -30]);
    const { container } = ui(<MomentRail bookmarks={[]} spoilers nowS={200} history={history} colors={colors} onJump={() => undefined} />);
    const fills = [...container.querySelectorAll('[data-testid="momentum-ribbon"] rect')].map((r) => r.getAttribute('fill'));
    expect(fills).toEqual([colors.home, colors.away]);
  });
});

describe('studio tour', () => {
  const go = () => ({ studio: vi.fn(() => true), decision: vi.fn(() => false), fanArabic: vi.fn(() => true), audit: vi.fn(() => true) });

  it('walks five stops with progress, each opening a real screen', () => {
    const g = go();
    ui(<StudioTour open onClose={() => undefined} go={g} />);
    expect(screen.getByText('Stop 1 of 5')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Take me there' }));
    expect(g.studio).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Next stop' }));
    fireEvent.click(screen.getByRole('button', { name: 'Take me there' }));
    expect(g.decision).toHaveBeenCalled();
    expect(screen.getByRole('status').textContent).toContain('No decision moment');
    fireEvent.click(screen.getByRole('button', { name: 'Next stop' }));
    fireEvent.click(screen.getByRole('button', { name: 'Take me there' }));
    expect(g.fanArabic).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Next stop' }));
    fireEvent.click(screen.getByRole('button', { name: 'Take me there' }));
    expect(g.audit).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Next stop' }));
    expect(screen.getByText('Stop 5 of 5')).toBeTruthy();
    expect(screen.getByRole('link', { name: /Take me there/ }).getAttribute('href')).toBe(REPO_ARCHITECTURE_URL);
    expect(document.querySelectorAll('[data-visited]')).toHaveLength(3);
  });
});

import { phoneLink, qrPath } from './PhoneQr';

describe('phone QR', () => {
  it('links to the same page, fan view, language and audience, keeping the demo flag', () => {
    const url = phoneLink({ origin: 'https://pp.example', pathname: '/', search: '?demo=1&x=<y>' }, { language: 'ar', persona: 'tactical' });
    expect(url).toBe('https://pp.example/?demo=1&lang=ar&persona=tactical#fan');
  });

  it('draws a local QR matrix', () => {
    const { size, d } = qrPath('https://pp.example/?lang=en#fan');
    expect(size).toBeGreaterThanOrEqual(21);
    expect(d.length).toBeGreaterThan(100);
  });
});

import { keyMoments } from './StudioTour';

describe('studio tour key moments', () => {
  it('picks the top-ranked moments from the data, in match order', () => {
    const list = keyMoments(
      [
        bm({ moment_id: 'a', kind: 'speed_burst', clock_s: 10 }),
        bm({ moment_id: 'b', kind: 'big_chance', clock_s: 20 }),
        bm({ moment_id: 'c', kind: 'goal', clock_s: 900 }),
        bm({ moment_id: 'd', kind: 'better_option', clock_s: 300 }),
        bm({ moment_id: 'e', kind: 'goal', clock_s: 100, ruled_out: true }),
      ],
      2,
    );
    expect(list.map((b) => b.moment_id)).toEqual(['d', 'c']);
  });

  it('shows the run and moves on with Next', () => {
    const onNextKey = vi.fn();
    const go = { studio: () => true, decision: () => true, fanArabic: () => true, audit: () => true };
    ui(
      <StudioTour
        open
        onClose={() => undefined}
        go={go}
        onPlayKeys={() => undefined}
        onNextKey={onNextKey}
        run={{ index: 0, total: 4, current: bm({ match_clock: '12:00', title: 'Rocket' }), paused: true }}
      />,
    );
    expect(screen.getByText('Key moment 1 of 4')).toBeTruthy();
    expect(screen.getByText(/how we know/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Next moment' }));
    expect(onNextKey).toHaveBeenCalled();
  });
});
