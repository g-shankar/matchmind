// The offline demo's cue sheet: a small stand-in for the server's cue compiler
// (backend crew/cues.py) so the overlay sees the same show / update / retract /
// supersede / clear ops without a backend. It only re-sends recorded numbers.
// Simplified on purpose: no layer queueing, no momentum ribbon, no telestration.
import type { Cue, CueLayer, CueReason, CueTime, MomentKind, OverlayCard, Teams, ViewerProfile } from './contract';

export const MAX_DEMO_CUES = 5000;

const STATE_LAYERS: ReadonlySet<CueLayer> = new Set<CueLayer>(['scorebug', 'momentum_ribbon']);
const TRANSIENT: CueLayer[] = ['lower_third', 'side_panel', 'pitch_tag', 'metric_alert', 'full_screen', 'telestration'];

export function demoSheetId(matchId: string, p: ViewerProfile): string {
  let id = `${matchId}/${p.persona}/${p.language}`;
  if (p.favourite_team) id += `/club=${p.favourite_team}`;
  if (p.focus_player_id) id += `/focus=${p.focus_player_id}`;
  if (p.focus_metric) id += `/metric=${p.focus_metric}`;
  return id;
}

export interface DemoCueMoment {
  moment_id: string;
  kind: MomentKind;
  team: string | null;
  player_ids: string[];
  event_id: string;
  retracts?: string[];
  reason?: CueReason | null;
  score?: { home: number; away: number } | null;
}

export class DemoCueSheet {
  readonly sheetId: string;
  seq = 0;
  private cues: Cue[] = [];
  private byMoment = new Map<string, { cueId: string; layer: CueLayer; kind: MomentKind | null }[]>();
  private ruledOut = new Set<string>();
  private retracted = new Set<string>();
  private scorebugOn = false;
  private periodsEnded = new Set<number>();

  constructor(
    matchId: string,
    private readonly profile: ViewerProfile,
    private readonly teams: Teams,
  ) {
    this.sheetId = demoSheetId(matchId, profile);
  }

  /** Cues for one played tick. `moments` are the recorded moments on its event. */
  feed(at: CueTime, eventType: string, moments: DemoCueMoment[], cards: OverlayCard[]): Cue[] {
    const out: Cue[] = [];
    if ((eventType === 'period_end' || eventType === 'match_end') && !this.periodsEnded.has(at.period)) {
      this.periodsEnded.add(at.period);
      const reason: CueReason = eventType === 'match_end' ? 'full_time' : 'period_end';
      out.push(this.next({ cue_id: `clear@${at.period}:${reason}`, op: 'clear', layer: 'all', clears: TRANSIENT, reason, start: at, duration_s: 0, end: at, priority: 100 }));
    }
    for (const m of moments) for (const target of m.retracts ?? []) out.push(...this.retractMoment(target, m, at));
    const byId = new Map(moments.map((m) => [m.moment_id, m]));
    for (const card of cards) {
      if (this.ruledOut.has(card.moment_id) || this.byMoment.has(card.moment_id)) continue;
      const layer = card.slot as CueLayer;
      const cueId = `${card.moment_id}@${layer}`;
      const retracts = card.retracts ?? [];
      const end = shift(at, card.duration_s);
      out.push(
        this.next({
          cue_id: cueId,
          op: retracts.length ? 'supersede' : 'show',
          layer,
          moment_id: card.moment_id,
          kind: card.kind,
          supersedes: retracts.flatMap((mid) => (this.byMoment.get(mid) ?? []).map((x) => x.cueId)),
          reason: retracts.length ? (byId.get(card.moment_id)?.reason ?? 'var_offside') : null,
          start: at,
          duration_s: card.duration_s,
          end,
          priority: card.priority,
          rtl: card.rtl,
          text: { headline: card.headline, body: card.body, why: card.why, text_language: card.text_language ?? card.language },
          evidence: card.evidence,
          source_event_ids: byId.get(card.moment_id) ? [byId.get(card.moment_id)!.event_id] : [],
          team: card.team,
          player_ids: [...card.player_ids],
          produced_by: card.produced_by,
        }),
      );
      this.remember(card.moment_id, cueId, layer, card.kind);
    }
    for (const m of moments) {
      if (this.ruledOut.has(m.moment_id) || !m.score) continue;
      const cueId = `scorebug@${m.moment_id}`;
      out.push(
        this.next({
          cue_id: cueId,
          op: this.scorebugOn ? 'update' : 'show',
          layer: 'scorebug',
          moment_id: m.moment_id,
          kind: m.kind,
          supersedes: m.kind === 'correction' ? (m.retracts ?? []).map((mid) => `scorebug@${mid}`) : [],
          reason: m.kind === 'correction' ? (m.reason ?? 'var_offside') : null,
          start: at,
          priority: 100,
          collision: 'latest',
          source_event_ids: [m.event_id],
          team: m.team,
          scorebug: { home_id: this.teams.home.team_id, away_id: this.teams.away.team_id, score_home: m.score.home, score_away: m.score.away },
        }),
      );
      this.scorebugOn = true;
      this.remember(m.moment_id, cueId, 'scorebug', m.kind);
    }
    const kept = out.filter((c) => c.seq <= MAX_DEMO_CUES);
    this.cues.push(...kept);
    return kept;
  }

  /** What is on air at `t_s`, after every op so far (mirrors the server's active_cues). */
  active(tS: number): Cue[] {
    const on = new Map<string, Cue>();
    for (const c of this.cues) {
      if (c.start.t_s > tS) continue;
      if (c.op === 'clear') {
        for (const [id, x] of on) if (c.clears.includes(x.layer as CueLayer)) on.delete(id);
        continue;
      }
      for (const id of [...c.retracts, ...c.supersedes]) on.delete(id);
      if (c.op === 'retract') continue;
      if (STATE_LAYERS.has(c.layer as CueLayer)) for (const [id, x] of on) if (x.layer === c.layer) on.delete(id);
      on.set(c.cue_id, c);
    }
    return [...on.values()].filter((c) => c.end === null || c.end.t_s > tS);
  }

  private retractMoment(target: string, by: DemoCueMoment, at: CueTime): Cue[] {
    if (this.ruledOut.has(target)) return [];
    this.ruledOut.add(target);
    const out: Cue[] = [];
    for (const { cueId, layer, kind } of this.byMoment.get(target) ?? []) {
      if (this.retracted.has(cueId)) continue;
      this.retracted.add(cueId);
      out.push(
        this.next({
          cue_id: `retract:${cueId}`,
          op: 'retract',
          layer,
          moment_id: target,
          kind,
          retracts: [cueId],
          reason: by.reason ?? 'var_offside',
          start: at,
          duration_s: 0,
          end: at,
          priority: 100,
          source_event_ids: [by.event_id],
          team: by.team,
          player_ids: [...by.player_ids],
        }),
      );
    }
    return out;
  }

  private remember(momentId: string, cueId: string, layer: CueLayer, kind: MomentKind | null) {
    const list = this.byMoment.get(momentId) ?? [];
    list.push({ cueId, layer, kind });
    this.byMoment.set(momentId, list);
  }

  private next(fields: Partial<Cue> & Pick<Cue, 'cue_id' | 'op' | 'layer' | 'start'>): Cue {
    this.seq += 1;
    return {
      schema_version: '1.0',
      seq: this.seq,
      moment_id: null,
      kind: null,
      retracts: [],
      supersedes: [],
      clears: [],
      reason: null,
      duration_s: null,
      end: null,
      priority: 50,
      collision: 'replace',
      persona: this.profile.persona,
      language: this.profile.language,
      rtl: false,
      text: null,
      evidence: [],
      source_event_ids: [],
      team: null,
      player_ids: [],
      produced_by: null,
      scorebug: null,
      ribbon: null,
      telestration: null,
      ...fields,
    };
  }
}

function shift(at: CueTime, seconds: number): CueTime {
  const clock = Math.round((at.clock_s + seconds) * 100) / 100;
  return { period: at.period, clock_s: clock, match_clock: formatClock(clock, at.period), t_s: Math.round((at.t_s + seconds) * 100) / 100 };
}

/** The engine's match clock: "39:11", or "45+1:20" in stoppage time (simulator/script.py). */
export function formatClock(clockS: number, period: number): string {
  const base = period === 1 ? 2700 : 5400;
  const two = (n: number) => String(n).padStart(2, '0');
  if (clockS > base) {
    const extra = clockS - base;
    return `${Math.floor(base / 60)}+${Math.floor(extra / 60)}:${two(Math.floor(extra % 60))}`;
  }
  return `${two(Math.floor(clockS / 60))}:${two(Math.floor(clockS % 60))}`;
}
