// Local copy of a viewer's cue sheet (docs/CUE-SHEET.md). Mirrors the server's
// `active_cues`: ops apply in seq order, a cue id is applied at most once, and a
// moment that was ruled out stays ruled out for the rest of the sheet, so a late
// or repeated "show" for it is dropped. Everything is bounded.
import type { Cue, CueLayer, CueSheetState, CuesData, OverlayCard } from '../api/contract';

export const MAX_SEEN = 600;
export const MAX_RULED_OUT = 50;
export const MAX_LOG = 30;
export const MAX_EXITING = 4;

const CAPACITY: Record<CueLayer, number> = {
  full_screen: 1,
  lower_third: 1,
  side_panel: 2,
  pitch_tag: 3,
  metric_alert: 3,
  telestration: 1,
  scorebug: 1,
  momentum_ribbon: 1,
};
const LATEST: ReadonlySet<CueLayer> = new Set<CueLayer>(['scorebug', 'momentum_ribbon']);

export interface CueViewState {
  sheetId: string | null;
  lastSeq: number;
  /** Cue ids already applied (dedupe for retries and replays). */
  seen: string[];
  /** What is on air, in seq order, within each layer's capacity. */
  onAir: Cue[];
  /** Moment ids that were ruled out (VAR): their cards never show as live again. */
  ruledOut: string[];
  /** The newest cues received, newest last, for the producer panel. */
  log: Cue[];
  /** Cards that were on screen when they were ruled out: they animate out once. */
  exiting: OverlayCard[];
}

export const initialCueState = (): CueViewState => ({
  sheetId: null,
  lastSeq: 0,
  seen: [],
  onAir: [],
  ruledOut: [],
  log: [],
  exiting: [],
});

const unique = (xs: string[], max: number) => [...new Set(xs)].slice(-max);

/** Moment ids a cue rules out: a VAR retract or supersede (not a period-end clear). */
function ruledOutBy(cue: Cue): string[] {
  if (!cue.reason || !cue.reason.startsWith('var_')) return [];
  if (cue.op === 'retract' && cue.moment_id) return [cue.moment_id];
  return [];
}

function place(onAir: Cue[], cue: Cue): Cue[] {
  let next = onAir;
  if (cue.op === 'clear') return next.filter((c) => !cue.clears.includes(c.layer as CueLayer));
  const gone = new Set([...cue.retracts, ...cue.supersedes]);
  if (gone.size) next = next.filter((c) => !gone.has(c.cue_id));
  if (cue.op === 'retract' || cue.layer === 'all') return next;
  const layer = cue.layer;
  if (LATEST.has(layer)) next = next.filter((c) => c.layer !== layer);
  next = [...next.filter((c) => c.cue_id !== cue.cue_id), cue];
  const mine = next.filter((c) => c.layer === layer);
  const over = mine.length - CAPACITY[layer];
  if (over > 0) {
    const drop = new Set(mine.slice(0, over).map((c) => c.cue_id));
    next = next.filter((c) => !drop.has(c.cue_id));
  }
  return next;
}

/** Apply one batch of cues. Duplicates are ignored; cues are applied in seq order. */
export function applyCues(state: CueViewState, data: CuesData): CueViewState {
  let s = state;
  if (data.active !== undefined || (state.sheetId !== null && data.sheet_id !== state.sheetId)) {
    // A new sheet for this viewer: what is on air now replaces local state. Ruled-out
    // moments stay ruled out: a profile change does not undo a VAR decision.
    s = startSheet(state, { sheet_id: data.sheet_id, last_seq: 0, active: data.active ?? [] }, state.ruledOut);
  } else if (state.sheetId === null) {
    s = { ...state, sheetId: data.sheet_id };
  }
  const seen = new Set(s.seen);
  const ruled = new Set(s.ruledOut);
  let onAir = s.onAir;
  let lastSeq = s.lastSeq;
  const fresh: Cue[] = [];
  for (const cue of [...data.cues].sort((a, b) => a.seq - b.seq)) {
    if (seen.has(cue.cue_id)) continue;
    seen.add(cue.cue_id);
    for (const id of ruledOutBy(cue)) ruled.add(id);
    // A late or replayed show for a ruled-out moment is a tombstoned cue: never on air.
    if (cue.op !== 'retract' && cue.moment_id && ruled.has(cue.moment_id) && cue.kind !== 'correction') continue;
    onAir = place(onAir, cue);
    lastSeq = Math.max(lastSeq, cue.seq);
    fresh.push(cue);
  }
  if (!fresh.length && ruled.size === s.ruledOut.length) return s;
  return {
    ...s,
    seen: [...seen].slice(-MAX_SEEN),
    onAir: onAir.filter((c) => !c.moment_id || c.kind === 'correction' || !ruled.has(c.moment_id)),
    lastSeq,
    ruledOut: unique([...ruled], MAX_RULED_OUT),
    log: [...s.log, ...fresh].slice(-MAX_LOG),
  };
}

/** Start from a snapshot's cue sheet (connect, reconnect, seek, reset). */
export function startSheet(state: CueViewState, sheet: CueSheetState | null | undefined, ruledOut: string[]): CueViewState {
  if (!sheet) return { ...initialCueState(), ruledOut: unique(ruledOut, MAX_RULED_OUT) };
  const active = [...sheet.active].sort((a, b) => a.seq - b.seq);
  const ruled = unique([...ruledOut, ...active.flatMap(ruledOutBy)], MAX_RULED_OUT);
  return {
    sheetId: sheet.sheet_id,
    lastSeq: Math.max(sheet.last_seq, ...active.map((c) => c.seq), 0),
    seen: active.map((c) => c.cue_id).slice(-MAX_SEEN),
    onAir: active,
    ruledOut: ruled,
    log: state.sheetId === sheet.sheet_id ? state.log : [],
    exiting: [],
  };
}

/** Moment ids that cards themselves rule out (a correction card lists the goal it overturns). */
export const retractedByCards = (cards: OverlayCard[]) => cards.flatMap((c) => c.retracts ?? []);

/** Record newly ruled-out moments; cards of theirs that are still on screen animate out. */
export function ruleOut(state: CueViewState, ids: string[], cards: OverlayCard[], clockS: number): CueViewState {
  const fresh = ids.filter((id) => !state.ruledOut.includes(id));
  if (!fresh.length) return state;
  const leaving = cards.filter(
    (c) => fresh.includes(c.moment_id) && clockS >= c.show_at_s - 1 && clockS <= c.show_at_s + c.duration_s,
  );
  return {
    ...state,
    ruledOut: unique([...state.ruledOut, ...fresh], MAX_RULED_OUT),
    onAir: state.onAir.filter((c) => !c.moment_id || !fresh.includes(c.moment_id) || c.kind === 'correction'),
    exiting: [...state.exiting, ...leaving].slice(-MAX_EXITING),
  };
}
