// Read-only "under the hood" data for the trust panels: the claim audit, crew
// health, the metric registry, basic stats, the auto-eventing benchmark and the
// dataset index. Live mode reads the match server's REST routes; the offline demo
// reads public/demo/demo-insights.json (built by scripts/build_demo_fixture.py),
// loaded only when a panel first needs it. Nothing here computes a number.
import type {
  AutoEventingStatus,
  BasicStats,
  CrewStatus,
  DatasetFormat,
  DatasetIndex,
  MetricRegistry,
  MomentAudit,
} from './contract';
import { apiBase } from './transport';

export type InsightMode = 'live' | 'demo';

export type InsightResult<T> =
  | { status: 'ready'; data: T; source: InsightMode }
  /** The offline demo cannot answer this: it needs the match server. */
  | { status: 'needs_server' }
  /** The server (or the recording) has nothing for this request. */
  | { status: 'missing' }
  /** Rate limited: try again in a few seconds. */
  | { status: 'busy' }
  | { status: 'error' };

export interface DemoInsights {
  insights_version: number;
  match_id: string;
  note: string;
  audits: Record<string, MomentAudit>;
  metrics: MetricRegistry;
  auto_eventing: AutoEventingStatus | null;
  dataset: DatasetIndex;
}

const MOMENT_ID = /^[A-Za-z0-9_:.-]{1,96}$/;
const MATCH_ID = /^[A-Z0-9][A-Z0-9-]{2,31}$/;

let demoBundle: Promise<DemoInsights> | null = null;

export function demoInsightsUrl(): string {
  return `${import.meta.env.BASE_URL}demo/demo-insights.json`;
}

/** The offline bundle, fetched once; a failed load is retried on the next call. */
export function loadDemoInsights(url = demoInsightsUrl()): Promise<DemoInsights> {
  if (!demoBundle) {
    demoBundle = fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`demo insights ${res.status}`);
        return res.json() as Promise<DemoInsights>;
      })
      .catch((err: unknown) => {
        demoBundle = null;
        throw err;
      });
  }
  return demoBundle;
}

/** Tests only: forget the cached bundle. */
export function resetDemoInsights() {
  demoBundle = null;
}

export async function getJson<T>(path: string, base = apiBase()): Promise<InsightResult<T>> {
  try {
    const res = await fetch(`${base}${path}`, { headers: { accept: 'application/json' } });
    if (res.status === 404) return { status: 'missing' };
    if (res.status === 429) return { status: 'busy' };
    if (!res.ok) return { status: 'error' };
    const data = (await res.json()) as T;
    if (data === null || typeof data !== 'object') return { status: 'error' };
    return { status: 'ready', data, source: 'live' };
  } catch {
    return { status: 'error' };
  }
}

async function fromDemo<T>(pick: (b: DemoInsights) => T | null | undefined): Promise<InsightResult<T>> {
  try {
    const value = pick(await loadDemoInsights());
    return value == null ? { status: 'missing' } : { status: 'ready', data: value, source: 'demo' };
  } catch {
    return { status: 'error' };
  }
}

export const insights = {
  audit(mode: InsightMode, momentId: string): Promise<InsightResult<MomentAudit>> {
    if (!MOMENT_ID.test(momentId)) return Promise.resolve({ status: 'missing' });
    if (mode === 'demo') return fromDemo((b) => (Object.prototype.hasOwnProperty.call(b.audits, momentId) ? b.audits[momentId] : null));
    return getJson<MomentAudit>(`/api/match/moment/${encodeURIComponent(momentId)}/audit`);
  },
  crewStatus(mode: InsightMode): Promise<InsightResult<CrewStatus>> {
    if (mode === 'demo') return Promise.resolve({ status: 'needs_server' });
    return getJson<CrewStatus>('/api/crew/status');
  },
  metrics(mode: InsightMode): Promise<InsightResult<MetricRegistry>> {
    if (mode === 'demo') return fromDemo((b) => b.metrics);
    return getJson<MetricRegistry>('/api/metrics');
  },
  basicStats(mode: InsightMode, spoilers = true): Promise<InsightResult<BasicStats>> {
    if (mode === 'demo') return Promise.resolve({ status: 'needs_server' });
    // Catch-up mode: the server leaves goals out (a team's goals are the score).
    return getJson<BasicStats>(spoilers ? '/api/match/stats/basic' : '/api/match/stats/basic?spoilers=false');
  },
  autoEventing(mode: InsightMode): Promise<InsightResult<AutoEventingStatus>> {
    if (mode === 'demo') return fromDemo((b) => b.auto_eventing);
    return getJson<AutoEventingStatus>('/api/auto-eventing');
  },
  dataset(mode: InsightMode): Promise<InsightResult<DatasetIndex>> {
    if (mode === 'demo') return fromDemo((b) => b.dataset);
    return getJson<DatasetIndex>('/api/dataset');
  },
};

/** A download link for one dataset match (a plain GET the browser saves). */
export function datasetExportUrl(matchId: string, format: DatasetFormat, base = apiBase()): string | null {
  if (!MATCH_ID.test(matchId)) return null;
  return `${base}/api/dataset/export?${new URLSearchParams({ match_id: matchId, format })}`;
}

export function mcpUrl(base = apiBase()): string {
  return `${base}/mcp`;
}

export function cueSheetUrl(persona: string, language: string, base = apiBase()): string {
  return `${base}/api/match/cue-sheet?${new URLSearchParams({ persona, lang: language, since_seq: '0' })}`;
}

/** The OBS / vMix Browser Source address for this app (docs/OBS.md). */
export function captureUrl(persona: string, language: string, demo: boolean, loc: Pick<Location, 'origin' | 'pathname'> = window.location): string {
  const q = new URLSearchParams({ capture: '1', persona, lang: language });
  if (demo) q.set('demo', '1');
  return `${loc.origin}${loc.pathname}?${q}#overlay`;
}

/** True when the page asked for the offline demo on purpose (`?demo=1`), not as a fallback. */
export function demoRequested(search = window.location.search): boolean {
  try {
    return new URLSearchParams(search).get('demo') === '1';
  } catch {
    return false;
  }
}
