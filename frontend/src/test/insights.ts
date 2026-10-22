import type { AutoEventingStatus, BasicStats, CrewStatus, DatasetIndex, MetricRegistry, MomentAudit } from '../api/contract';
import type { DemoInsights } from '../api/insights';

const claimsFor = (lang: string) => [
  {
    sentence: lang === 'ar' ? 'هل كان على AAA أن يمرر؟' : 'Should Striker have passed?',
    field: 'headline' as const,
    fact_keys: ['player_short'],
    numbers: [],
    source_event_ids: ['T-1-2'],
    check: 'verified_name' as const,
    reason: 'names matched to facts (Striker); wording not machine-checked',
    origin: 'matched' as const,
    bindings: [{ text: lang === 'ar' ? 'AAA' : 'Striker', kind: 'name' as const, fact_key: 'player_short', value: 'Striker', unit: null, entity_id: 'AAA-9' }],
  },
  {
    sentence: 'The pass was worth 2.4x the shot, 7 more.',
    field: 'body' as const,
    fact_keys: ['times_better'],
    numbers: ['2.4', '7'],
    source_event_ids: ['T-1-2'],
    check: 'unverified_text' as const,
    reason: 'number 7 is not in the facts',
    origin: 'matched' as const,
    bindings: [
      { text: '2.4', kind: 'number' as const, fact_key: 'times_better', value: 2.4, unit: 'x', entity_id: null },
      { text: '7', kind: 'number' as const, fact_key: null, value: null, unit: null, entity_id: null },
    ],
  },
  {
    sentence: 'Something may have to give.',
    field: 'why' as const,
    fact_keys: [],
    numbers: [],
    source_event_ids: ['T-1-2'],
    check: 'unverified_text' as const,
    reason: 'no number or squad name to check; tone and wording are not machine-verified',
    origin: 'matched' as const,
    bindings: [],
  },
];

export const rendering = (persona: 'casual' | 'tactical', language: 'en' | 'ar') => ({
  persona,
  language,
  text_language: language,
  source: 'template_sweep' as const,
  produced_by: 'template' as const,
  fallback_reason: null,
  translated_by: null,
  headline: 'Should Striker have passed?',
  body: 'The pass was worth 2.4x the shot.',
  why: 'Something may have to give.',
  fact_check: { ok: true, reasons: [] },
  claims: claimsFor(language),
});

export const audit = (over: Partial<MomentAudit> = {}): MomentAudit => ({
  moment_id: 'M-2',
  kind: 'better_option',
  match_clock: '34:16',
  period: 1,
  team: 'AAA',
  player_ids: ['AAA-9'],
  facts: { player: 'AAA Striker', player_short: 'Striker', times_better: 2.4 },
  source_event_ids: ['T-1-2'],
  explanation: {
    moment_id: 'M-2',
    why: 'Something may have to give.',
    tactical_tag: 'decision_making',
    evidence: [{ label: 'Pass vs shot', label_key: 'times_better', value: 2.4, unit: 'x', source_event_id: 'T-1-2' }],
    produced_by: 'template',
    fallback_reason: null,
  },
  renderings: [rendering('casual', 'en'), rendering('casual', 'ar'), rendering('tactical', 'en')],
  parity: {
    ok: false,
    key_facts: ['player', 'times_better'],
    anchors: [['player']],
    renderings: 3,
    withheld: 0,
    stated: { 'casual/en': ['player', 'times_better'], 'casual/ar': ['player'], 'tactical/en': ['player', 'times_better'] },
    problems: ['casual/ar: key facts differ from casual/en (missing times_better)'],
  },
  trace: [
    { agent: 'spotter', ms: 0.13, status: 'ok', detail: 'better_option' },
    { agent: 'commentator', ms: 12.5, status: 'fallback', detail: 'casual/en: template' },
  ],
  not_checked: ['Tone, wording and causal claims (why something happened) are not machine-verified.'],
  retracts: [],
  ruled_out_by: null,
  ...over,
});

export const crewStatus = (over: Partial<CrewStatus> = {}): CrewStatus => ({
  mode: 'template',
  model: null,
  provider: 'templates',
  orchestrator: 'in_process',
  breakers_open: [],
  moments: 12,
  fallbacks: 0,
  rejections: 1,
  translator: { mode: 'off', available: false, breaker_open: false, cache_hits: 0, translated: 0, fallbacks: 0, rejections: 0 },
  health: {
    window: 256,
    latency: [
      { agent: 'analyst', samples: 40, p50_ms: 0.4, p95_ms: 1.9, max_ms: 3 },
      { agent: 'producer', samples: 40, p50_ms: 0.8, p95_ms: 2.2, max_ms: 4 },
    ],
    model_steps: 80,
    fallback_steps: 0,
    fallback_rate: 0,
    checks: 120,
    rejected_checks: 3,
    rejection_rate: 0.025,
    moments_per_min: 1.5,
  },
  ...over,
});

const row = (kind: 'pass' | 'tackle', f1: number) => ({
  kind,
  support: 10,
  detected: 10,
  matched: 9,
  precision: 0.9,
  recall: 0.9,
  f1,
  precision_ci: [0.6, 0.98] as [number, number],
  recall_ci: [0.6, 0.98] as [number, number],
});

export const autoEventing = (): AutoEventingStatus => ({
  source: 'synthetic_tracking',
  label: 'Detected from synthetic tracking, not video',
  passes_detected_pct: 99.4,
  speed_mae_kmh: 1.11,
  events_checked: 1364,
  match_id: 'T-1',
  speed_mae_ci_kmh: [1.0, 1.2],
  classes: [row('pass', 0.996), row('tackle', 0.895)],
  pressure: null,
  confusion: { rows: ['pass', 'tackle', 'spurious'], columns: ['pass', 'tackle', 'missed'], counts: [[9, 0, 1], [0, 8, 2], [1, 1, 0]] },
  baseline: { name: 'Naive baseline', classes: [row('pass', 0.795), row('tackle', 0.128)] },
  pixel_path: {
    label: 'Rendered synthetic top-down video',
    window_s: 30,
    frames: 750,
    width_px: 320,
    height_px: 208,
    player_error_m: 0.018,
    ball_error_m: 0.055,
    ball_found_pct: 99.9,
    coordinate: [row('pass', 0.95), { ...row('tackle', 0), support: 0 }],
    pixels: [row('pass', 0.9), { ...row('tackle', 0), support: 0 }],
    speed_mae_kmh_coordinate: 1.23,
    speed_mae_kmh_pixels: 1.03,
  },
  caveat: 'Circular by construction.',
});

export const metrics = (): MetricRegistry => ({
  quality_flags: {
    counted: 'Direct count.',
    calibrated: 'Calibrated constants.',
    heuristic: 'Hand-weighted rule.',
    estimated_from_synthetic_tracking: 'From synthetic tracking.',
  },
  metrics: [
    {
      id: 'pass_distance_m', name: 'Pass distance', scope: 'event', formula: 'Straight line.', symbols: 'd = |end - start|', units: 'm',
      source_events: ['pass'], window: 'per event', range: '0-125', quality: 'counted', limitations: '2D only.', edge_cases: '', fields: [],
    },
    {
      id: 'pressure_index', name: 'Pressure index', scope: 'window', formula: 'Weighted pressing.', symbols: '', units: '0-100',
      source_events: ['tackle'], window: '5 min', range: '0-100', quality: 'heuristic', limitations: 'Hand weights.', edge_cases: 'None.', fields: [],
    },
  ],
  not_computed: [{ id: 'half_space', name: 'Half-space occupation', reason: 'Planned.' }],
});

export const dataset = (): DatasetIndex => ({
  synthetic: true,
  note: 'Synthetic.',
  schema_version: '1.0',
  pitch: { length_m: 105, width_m: 68, home_attacks: '+x' },
  formats: ['jsonl', 'csv', 'zip'],
  tracking: { hz: 25, max_window_s: 60, formats: ['zip'] },
  scenarios: { demo_storyline: 'Scripted demo.' },
  seeded: { seed_start: 1000, seed_end: 1001, match_id: 'MM-GEN-<seed>' },
  matches: [
    { match_id: 'MM-DEMO-001', kind: 'bundled', scenario: 'demo_storyline', seed: 100, home: 'NBR', away: 'HCY', score: '2-3', events: 2142 },
    { match_id: 'MM-GEN-01000', kind: 'seeded', scenario: 'chance_model', seed: 1000, home: 'NBR', away: 'HCY', score: null, events: null },
  ],
});

export const basicStats = (): BasicStats => {
  const team = (id: string) => ({
    team_id: id, name: `${id} Town`, possession_pct: 50, passes_completed: 100, passes_attempted: 120, pass_accuracy_pct: 83.3,
    shots: 5, shots_on_target: 2, goals: 1, tackles_won: 8, tackles_attempted: 12, interceptions: 6, fouls: 3, ppda: 9.5,
    ppda_opponent_passes: 95, ppda_defensive_actions: 10, distance_km: 52.1, top_speed_kmh: 33.2,
  });
  return {
    match_id: 'T-1', clock: '45:00', period: 1, pass_accuracy_denominator: 'every pass attempt',
    physical_source: 'synthetic_tracking', physical_label: 'Estimated from synthetic tracking',
    teams: { AAA: team('AAA'), BBB: team('BBB') },
    players: [
      { player_id: 'AAA-9', team: 'AAA', name: 'AAA Striker', number: 9, position: 'ST', passes_completed: 10, passes_attempted: 14, pass_accuracy_pct: 71.4, shots: 3, shots_on_target: 1, goals: 1, tackles_won: 0, tackles_attempted: 1, interceptions: 0, distance_km: 5.2, sprints: 9, top_speed_kmh: 33.2 },
    ],
  };
};

export const demoInsights = (): DemoInsights => ({
  insights_version: 1,
  match_id: 'T-1',
  note: 'Recorded.',
  audits: { 'M-2': audit(), 'M-3': audit({ moment_id: 'M-3', kind: 'correction', retracts: ['M-2'] }) },
  metrics: metrics(),
  auto_eventing: autoEventing(),
  dataset: dataset(),
});

/** A fetch stub answering by URL path. */
export function fetchStub(routes: Record<string, unknown | ((url: string) => Response)>) {
  return async (input: RequestInfo | URL) => {
    const url = String(input);
    for (const [path, body] of Object.entries(routes)) {
      if (url.includes(path)) {
        if (typeof body === 'function') return (body as (u: string) => Response)(url);
        return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });
      }
    }
    return new Response('{"detail":"not found"}', { status: 404 });
  };
}
