import { afterEach, describe, expect, it, vi } from 'vitest';
import { captureUrl, cueSheetUrl, datasetExportUrl, demoRequested, getJson, insights, mcpUrl, resetDemoInsights, type DemoInsights } from './insights';
import type { DemoFixture } from './mockServer';
import { claimFailed } from '../components/ClaimAudit';
import { demoInsights, fetchStub } from '../test/insights';
import bundleRaw from '../../public/demo/demo-insights.json?raw';
import fixtureRaw from '../../public/demo/demo-match.json?raw';

afterEach(() => {
  vi.unstubAllGlobals();
  resetDemoInsights();
});

const status = (code: number) => () => new Response('{}', { status: code });

describe('insights client', () => {
  it('maps HTTP answers to one plain state each', async () => {
    vi.stubGlobal('fetch', fetchStub({ '/a': { ok: 1 }, '/b': status(404), '/c': status(429), '/d': status(500), '/e': () => new Response('null') }));
    expect(await getJson('/a', 'http://x')).toEqual({ status: 'ready', data: { ok: 1 }, source: 'live' });
    expect((await getJson('/b', 'http://x')).status).toBe('missing');
    expect((await getJson('/c', 'http://x')).status).toBe('busy');
    expect((await getJson('/d', 'http://x')).status).toBe('error');
    expect((await getJson('/e', 'http://x')).status).toBe('error');
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('offline')));
    expect((await getJson('/a', 'http://x')).status).toBe('error');
  });

  it('reads the audit route in live mode and refuses malformed ids without a request', async () => {
    const fetch = vi.fn(fetchStub({ '/api/match/moment/M-2/audit': { moment_id: 'M-2' } }));
    vi.stubGlobal('fetch', fetch);
    expect((await insights.audit('live', 'M-2')).status).toBe('ready');
    expect((await insights.audit('live', '../../etc')).status).toBe('missing');
    expect((await insights.audit('live', 'x'.repeat(200))).status).toBe('missing');
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('answers from the offline bundle in demo mode, loads it once, and says what needs the server', async () => {
    const fetch = vi.fn(fetchStub({ 'demo-insights.json': demoInsights() }));
    vi.stubGlobal('fetch', fetch);
    const a = await insights.audit('demo', 'M-2');
    expect(a.status === 'ready' && a.source).toBe('demo');
    expect((await insights.audit('demo', 'nope')).status).toBe('missing');
    expect((await insights.audit('demo', 'constructor')).status).toBe('missing');
    expect((await insights.metrics('demo')).status).toBe('ready');
    expect((await insights.autoEventing('demo')).status).toBe('ready');
    expect((await insights.dataset('demo')).status).toBe('ready');
    expect((await insights.crewStatus('demo')).status).toBe('needs_server');
    expect((await insights.basicStats('demo')).status).toBe('needs_server');
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('retries the offline bundle after a failed load', async () => {
    vi.stubGlobal('fetch', fetchStub({ 'demo-insights.json': status(500) }));
    expect((await insights.metrics('demo')).status).toBe('error');
    vi.stubGlobal('fetch', fetchStub({ 'demo-insights.json': demoInsights() }));
    expect((await insights.metrics('demo')).status).toBe('ready');
  });

  it('builds links: dataset exports only for well-formed ids, MCP, cue sheet and the OBS capture URL', () => {
    expect(datasetExportUrl('MM-DEMO-001', 'csv', 'http://h')).toBe('http://h/api/dataset/export?match_id=MM-DEMO-001&format=csv');
    expect(datasetExportUrl('mm"><script>', 'csv', 'http://h')).toBeNull();
    expect(mcpUrl('http://h')).toBe('http://h/mcp');
    expect(cueSheetUrl('tactical', 'es', 'http://h')).toBe('http://h/api/match/cue-sheet?persona=tactical&lang=es&since_seq=0');
    const loc = { origin: 'https://pp.example', pathname: '/' };
    expect(captureUrl('casual', 'ar', false, loc)).toBe('https://pp.example/?capture=1&persona=casual&lang=ar#overlay');
    expect(captureUrl('casual', 'en', true, loc)).toContain('&demo=1#overlay');
    expect(demoRequested('?demo=1')).toBe(true);
    expect(demoRequested('?live=1')).toBe(false);
  });
});

// The recorded bundle the offline demo ships (built by scripts/build_demo_fixture.py).
describe('public/demo/demo-insights.json', () => {
  const bundle = JSON.parse(bundleRaw) as DemoInsights;
  const fixture = JSON.parse(fixtureRaw) as DemoFixture;

  it('has an audit for every demo moment, for the same match', () => {
    expect(bundle.match_id).toBe(fixture.match_id);
    expect(Object.keys(bundle.audits).sort()).toEqual(fixture.moments.map((m) => m.moment_id).sort());
  });

  it('audits the exact text the demo shows, and every version passed the fact-checker', () => {
    for (const m of fixture.moments) {
      const a = bundle.audits[m.moment_id];
      expect(a.trace).toEqual([]);
      for (const r of a.renderings) {
        const text = m.texts[r.persona]?.[r.language];
        expect(text, `${m.moment_id} ${r.persona}/${r.language}`).toBeTruthy();
        expect(r.headline).toBe(text!.headline);
        expect(r.fact_check.ok, `${m.moment_id} ${r.persona}/${r.language}`).toBe(true);
        expect(r.claims.filter(claimFailed)).toEqual([]);
      }
    }
  });

  it('links the VAR correction to the goal it rules out, both ways', () => {
    const corrections = Object.values(bundle.audits).filter((a) => a.retracts?.length);
    expect(corrections.length).toBeGreaterThan(0);
    for (const c of corrections) for (const id of c.retracts!) expect(bundle.audits[id].ruled_out_by).toBe(c.moment_id);
  });

  it('labels the benchmark as synthetic tracking and keeps the registry and dataset', () => {
    expect(bundle.auto_eventing?.label).toMatch(/synthetic tracking, not video/i);
    expect(bundle.metrics.metrics.length).toBeGreaterThan(10);
    expect(bundle.dataset.synthetic).toBe(true);
  });
});
