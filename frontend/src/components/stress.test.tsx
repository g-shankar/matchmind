import type React from 'react';
import recordingJson from '../../public/demo/demo-stress.json';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { I18nProvider, translate } from '../i18n';
import { resetDemoStress, stressTest, type DemoStress } from '../api/insights';
import { InsightModeProvider } from '../state/useInsight';
import { STRESS_FAULTS, type Bookmark, type StressResult } from '../api/contract';
import { StressSteps, StressTestButton, stepText } from './StressTest';
import { fetchStub } from '../test/insights';

const recording = recordingJson as unknown as DemoStress;
const [firstId] = Object.keys(recording.results);
const sample = (fault = 'wrong_number' as const, lang = 'en'): StressResult => recording.results[firstId][lang][fault]!;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  resetDemoStress();
});

const ui = (node: React.ReactNode, lang = 'en', mode: 'live' | 'demo' = 'live') =>
  render(
    <I18nProvider lang={lang}>
      <InsightModeProvider mode={mode}>{node}</InsightModeProvider>
    </I18nProvider>,
  );

const bm = (id: string): Bookmark => ({ moment_id: id, kind: 'goal', match_clock: '10:00', clock_s: 600, period: 1, title: 'Goal' });

describe('stress test recording', () => {
  it('holds every fault in every studio language, each ending in a safe template card', () => {
    expect(Object.keys(recording.results).length).toBeGreaterThanOrEqual(3);
    for (const langs of Object.values(recording.results))
      for (const lang of ['en', 'es', 'fr', 'ar', 'ja'])
        for (const f of STRESS_FAULTS) {
          const r = langs[lang][f]!;
          expect(r.safe).toBe(true);
          expect(r.card?.produced_by).toBe('template');
          expect(r.steps.at(-1)?.agent).toBe('producer');
        }
  });

  it('shows the fact-checker rejecting the injected number, which never reaches the card', () => {
    const r = sample();
    const injected = r.steps.find((s) => s.status === 'injected')!.detail!;
    expect(r.steps.find((s) => s.agent === 'fact_checker')).toMatchObject({ status: 'rejected', detail: injected });
    expect(r.card!.body).not.toContain(injected);
  });

  it('every step code has a translation in every language', () => {
    for (const lang of ['en', 'es', 'fr', 'ar', 'ja'] as const)
      for (const langs of Object.values(recording.results))
        for (const r of Object.values(langs.en))
          for (const s of r!.steps) {
            const text = stepText((k, v) => translate(lang, k, v), s);
            expect(text).not.toMatch(/^stress\./);
            expect(translate(lang, `stress.status.${s.status}`)).not.toMatch(/^stress\./);
          }
  });
});

describe('stress test client', () => {
  it('sends only the enums and the moment id, as JSON', async () => {
    const spy = vi.fn(fetchStub({ '/api/match/stress-test': sample() }));
    vi.stubGlobal('fetch', spy);
    const r = await stressTest('live', 'big_chance-MM-1', 'model_down', 'ar', '');
    expect(r.status).toBe('ready');
    const [, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ moment_id: 'big_chance-MM-1', fault: 'model_down', lang: 'ar' });
  });

  it('refuses odd ids and faults without a request, and maps 429 to busy', async () => {
    const spy = vi.fn(fetchStub({ '/api/match/stress-test': () => new Response('{}', { status: 429 }) }));
    vi.stubGlobal('fetch', spy);
    expect((await stressTest('live', '<script>', 'model_down', 'en', '')).status).toBe('missing');
    expect((await stressTest('live', 'x', 'drop' as never, 'en', '')).status).toBe('missing');
    expect(spy).not.toHaveBeenCalled();
    expect((await stressTest('live', 'x', 'model_down', 'en', '')).status).toBe('busy');
  });

  it('plays the recording offline and says when a moment is not recorded', async () => {
    vi.stubGlobal('fetch', fetchStub({ 'demo-stress.json': recording }));
    expect((await stressTest('demo', firstId, 'bad_handoff', 'ja')).status).toBe('ready');
    expect((await stressTest('demo', 'not-recorded', 'bad_handoff', 'en')).status).toBe('needs_server');
  });
});

describe('stress test panel', () => {
  it('reveals the steps one by one, then the safe card', () => {
    vi.useFakeTimers();
    ui(<StressSteps result={sample()} />);
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    for (let i = 0; i < 10; i++) act(() => void vi.advanceTimersByTime(450));
    expect(screen.getAllByRole('listitem')).toHaveLength(sample().steps.length);
    expect(screen.getByTestId('stress-steps').textContent).toContain('is not in this moment');
    expect(screen.getByTestId('stress-card').textContent).toContain('Safe card');
  });

  it('opens from one button, runs the demo recording and speaks Arabic', async () => {
    vi.stubGlobal('fetch', fetchStub({ 'demo-stress.json': recording }));
    ui(<StressTestButton bookmarks={[bm(firstId), bm('unrecorded')]} spoilers />, 'ar', 'demo');
    fireEvent.click(screen.getByRole('button', { name: 'اختبر الطاقم تحت الضغط' }));
    const select = (await screen.findByRole('combobox')) as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual([firstId]);
    fireEvent.click(screen.getByRole('button', { name: 'شغّل الاختبار' }));
    expect(await screen.findByTestId('stress-steps')).toBeTruthy();
  });

  it('is hidden in catch-up mode', () => {
    ui(<StressTestButton bookmarks={[bm('a')]} spoilers={false} />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});
