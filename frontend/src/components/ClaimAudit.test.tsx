import type React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import { resetDemoInsights, type InsightMode } from '../api/insights';
import { InsightModeProvider } from '../state/useInsight';
import { ShowWorkingButton, claimFailed, claimSegments } from './ClaimAudit';
import { audit, demoInsights, fetchStub } from '../test/insights';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetDemoInsights();
});

const ui = (node: React.ReactNode, { lang = 'en', mode = 'live' as InsightMode } = {}) =>
  render(
    <I18nProvider lang={lang}>
      <InsightModeProvider mode={mode}>{node}</InsightModeProvider>
    </I18nProvider>,
  );

const open = async (name = 'Show your working') => {
  fireEvent.click(screen.getByRole('button', { name }));
  return screen.findByRole('dialog');
};

describe('claimSegments', () => {
  it('splits a sentence around its bindings in order, keeping every character', () => {
    const c = audit().renderings[0].claims[1];
    const segs = claimSegments(c);
    expect(segs.map((s) => s.text).join('')).toBe(c.sentence);
    expect(segs.filter((s) => s.binding).map((s) => s.text)).toEqual(['2.4', '7']);
  });

  it('tells a failed check from a sentence with nothing to check', () => {
    const [name, failed, nothing] = audit().renderings[0].claims;
    expect([claimFailed(name), claimFailed(failed), claimFailed(nothing)]).toEqual([false, true, false]);
  });
});

describe('Show your working', () => {
  it('loads the audit and shows each sentence with its check, bindings and sources', async () => {
    const fetch = vi.fn(fetchStub({ '/api/match/moment/M-2/audit': audit() }));
    vi.stubGlobal('fetch', fetch);
    ui(<ShowWorkingButton momentId="M-2" persona="casual" language="en" />);
    const dialog = await open();
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(within(dialog).getByRole('heading', { name: 'Show your working' })).toBeTruthy();
    // Honest framing and the legend.
    expect(within(dialog).getByText(/Numeric-claim validation/)).toBeTruthy();
    expect(within(dialog).queryByText(/hallucination/i)).toBeNull();
    expect(within(dialog).getByText('Number matched to a stats-engine fact')).toBeTruthy();
    await within(dialog).findByText('Names verified');
    expect(within(dialog).getByText('Check failed')).toBeTruthy();
    expect(within(dialog).getByText('Not machine-checked')).toBeTruthy();
    // Inline marks: the bound number, the unbound one, the name.
    const marks = dialog.querySelectorAll('mark[data-mark]');
    expect([...marks].map((m) => `${m.getAttribute('data-mark')}:${m.textContent}`)).toEqual(
      expect.arrayContaining(['name:Striker', 'number:2.4', 'unbound:7']),
    );
    expect(within(dialog).getAllByText('times_better').length).toBeGreaterThan(0);
    expect(within(dialog).getByText('not in this moment’s facts')).toBeTruthy();
    expect(within(dialog).getAllByText('T-1-2').length).toBeGreaterThan(0);
    // Parity, trace and limits.
    expect(within(dialog).getByText('Parity flagged')).toBeTruthy();
    expect(within(dialog).getByText(/missing times_better/)).toBeTruthy();
    expect(within(dialog).getByText('12.50 ms')).toBeTruthy();
    expect(within(dialog).getByText('Fallback')).toBeTruthy();
    expect(within(dialog).getByText(/Tone, wording and causal claims/)).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('switches to another language of the same moment, right to left', async () => {
    vi.stubGlobal('fetch', fetchStub({ '/audit': audit() }));
    ui(<ShowWorkingButton momentId="M-2" persona="casual" language="en" />);
    const dialog = await open();
    await within(dialog).findAllByText('Names verified');
    fireEvent.click(within(dialog).getByRole('radio', { name: 'AR' }));
    const sentence = await within(dialog).findByText((_, el) => el?.tagName === 'P' && el.textContent === 'هل كان على AAA أن يمرر؟');
    expect(sentence.getAttribute('dir')).toBe('rtl');
    expect(sentence.getAttribute('lang')).toBe('ar');
  });

  it('closes on Escape and gives focus back to the button', async () => {
    vi.stubGlobal('fetch', fetchStub({ '/audit': audit() }));
    ui(<ShowWorkingButton momentId="M-2" />);
    const dialog = await open();
    expect(document.activeElement?.getAttribute('aria-label')).toBe('Close');
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Show your working' }));
  });

  it('does not close the card it was opened from (events stop at the drawer)', async () => {
    vi.stubGlobal('fetch', fetchStub({ '/audit': audit() }));
    const outer = vi.fn();
    ui(
      <div onClick={outer}>
        <ShowWorkingButton momentId="M-2" />
      </div>,
    );
    const dialog = await open();
    outer.mockClear();
    fireEvent.click(dialog);
    fireEvent.click(dialog.parentElement!);
    expect(outer).not.toHaveBeenCalled();
  });

  it('shows one plain message and a retry when loading fails, then recovers', async () => {
    let fail = true;
    vi.stubGlobal('fetch', fetchStub({ '/audit': () => (fail ? new Response('{}', { status: 500 }) : new Response(JSON.stringify(audit()))) }));
    ui(<ShowWorkingButton momentId="M-2" />);
    const dialog = await open();
    const alert = await within(dialog).findByRole('alert');
    expect(alert.textContent).toMatch(/could not be loaded/);
    fail = false;
    fireEvent.click(within(dialog).getByRole('button', { name: 'Try again' }));
    await within(dialog).findAllByText('Names verified');
  });

  it('says plainly when there is no working for a moment', async () => {
    vi.stubGlobal('fetch', fetchStub({}));
    ui(<ShowWorkingButton momentId="M-404" />);
    const dialog = await open();
    await within(dialog).findByText('We could not find the working for this moment.');
  });

  it('works offline from the recorded bundle, says why there is no trace, and follows VAR links', async () => {
    vi.stubGlobal('fetch', fetchStub({ 'demo-insights.json': { ...demoInsights(), audits: { ...demoInsights().audits, 'M-2': audit({ trace: [], ruled_out_by: 'M-3' }) } } }));
    ui(<ShowWorkingButton momentId="M-2" />, { mode: 'demo' });
    const dialog = await open();
    await within(dialog).findByText(/Offline demo: these claims were checked/);
    expect(within(dialog).getByText(/no crew ran in the recording/)).toBeTruthy();
    expect(within(dialog).getByText('A VAR decision later ruled this moment out:')).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: 'M-3' }));
    await within(dialog).findByText('This VAR decision rules out:');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Back to the previous moment' }));
    await within(dialog).findByText('A VAR decision later ruled this moment out:');
  });

  it('is labelled in Arabic with right-to-left layout', async () => {
    vi.stubGlobal('fetch', fetchStub({ '/audit': audit() }));
    ui(<ShowWorkingButton momentId="M-2" />, { lang: 'ar' });
    const dialog = await open('أرني كيف');
    expect(dialog.parentElement?.getAttribute('dir')).toBe('rtl');
    expect(within(dialog).getByRole('heading', { name: 'أرني كيف' })).toBeTruthy();
    expect(within(dialog).getByRole('button', { name: 'إغلاق' })).toBeTruthy();
  });
});
