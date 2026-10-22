import { describe, expect, it } from 'vitest';
import type { Cue, CueTime } from '../api/contract';
import { applyCues, initialCueState, MAX_SEEN, ruleOut, startSheet } from './cues';

const at = (t: number): CueTime => ({ period: 1, clock_s: t, match_clock: '00:00', t_s: t });

function cue(seq: number, over: Partial<Cue>): Cue {
  return {
    schema_version: '1.0',
    cue_id: `c${seq}`,
    seq,
    op: 'show',
    layer: 'lower_third',
    moment_id: null,
    kind: null,
    retracts: [],
    supersedes: [],
    clears: [],
    reason: null,
    start: at(seq),
    duration_s: 8,
    end: at(seq + 8),
    priority: 50,
    collision: 'replace',
    persona: 'casual',
    language: 'en',
    rtl: false,
    text: null,
    evidence: [],
    source_event_ids: [],
    team: null,
    player_ids: [],
    produced_by: 'template',
    scorebug: null,
    ribbon: null,
    telestration: null,
    ...over,
  };
}

const SHEET = 'MM/casual/en';
const goalShow = cue(1, { cue_id: 'goal-1@full_screen', layer: 'full_screen', moment_id: 'goal-1', kind: 'goal' });
const bug1 = cue(2, { cue_id: 'scorebug@goal-1', layer: 'scorebug', moment_id: 'goal-1', kind: 'goal', op: 'show', collision: 'latest', end: null, scorebug: { home_id: 'H', away_id: 'A', score_home: 2, score_away: 0 } });
const retractCard = cue(3, { cue_id: 'retract:goal-1@full_screen', op: 'retract', layer: 'full_screen', moment_id: 'goal-1', kind: 'goal', retracts: ['goal-1@full_screen'], reason: 'var_offside' });
const retractBug = cue(4, { cue_id: 'retract:scorebug@goal-1', op: 'retract', layer: 'scorebug', moment_id: 'goal-1', kind: 'goal', retracts: ['scorebug@goal-1'], reason: 'var_offside' });
const correction = cue(5, { cue_id: 'correction-9@full_screen', op: 'supersede', layer: 'full_screen', moment_id: 'correction-9', kind: 'correction', supersedes: ['goal-1@full_screen'], reason: 'var_offside' });
const bug2 = cue(6, { cue_id: 'scorebug@correction-9', op: 'update', layer: 'scorebug', moment_id: 'correction-9', kind: 'correction', collision: 'latest', end: null, supersedes: ['scorebug@goal-1'], reason: 'var_offside', scorebug: { home_id: 'H', away_id: 'A', score_home: 1, score_away: 0 } });

const ids = (cs: Cue[]) => cs.map((c) => c.cue_id);

describe('cue sheet state', () => {
  it('retract and supersede take the goal off air and revert the scorebug', () => {
    let s = applyCues(initialCueState(), { sheet_id: SHEET, cues: [goalShow, bug1] });
    expect(ids(s.onAir)).toEqual(['goal-1@full_screen', 'scorebug@goal-1']);
    s = applyCues(s, { sheet_id: SHEET, cues: [retractCard, retractBug, correction, bug2] });
    expect(ids(s.onAir)).toEqual(['correction-9@full_screen', 'scorebug@correction-9']);
    expect(s.onAir[1].scorebug?.score_home).toBe(1);
    expect(s.ruledOut).toEqual(['goal-1']);
    expect(s.lastSeq).toBe(6);
  });

  it('ignores duplicates (retry, double delivery)', () => {
    const once = applyCues(initialCueState(), { sheet_id: SHEET, cues: [goalShow, bug1, retractCard] });
    const twice = applyCues(once, { sheet_id: SHEET, cues: [goalShow, bug1, retractCard] });
    expect(twice).toBe(once);
  });

  it('out of order: a late show for a ruled-out goal never goes on air', () => {
    let s = applyCues(initialCueState(), { sheet_id: SHEET, cues: [retractCard, correction] });
    s = applyCues(s, { sheet_id: SHEET, cues: [goalShow] });
    expect(ids(s.onAir)).toEqual(['correction-9@full_screen']);
    // Within one batch the ops are applied in seq order whatever order they arrived in.
    const shuffled = applyCues(initialCueState(), { sheet_id: SHEET, cues: [bug2, correction, retractBug, retractCard, bug1, goalShow] });
    expect(ids(shuffled.onAir)).toEqual(['correction-9@full_screen', 'scorebug@correction-9']);
  });

  it('a clear empties the transient layers but keeps the scorebug', () => {
    const clear = cue(7, { cue_id: 'clear@1:period_end', op: 'clear', layer: 'all', clears: ['lower_third', 'full_screen'], reason: 'period_end' });
    const s = applyCues(initialCueState(), { sheet_id: SHEET, cues: [goalShow, bug1, clear] });
    expect(ids(s.onAir)).toEqual(['scorebug@goal-1']);
    expect(s.ruledOut).toEqual([]); // a period-end clear rules nothing out
  });

  it('a new sheet (active present) replaces local state but keeps VAR decisions', () => {
    let s = applyCues(initialCueState(), { sheet_id: SHEET, cues: [goalShow, retractCard] });
    s = applyCues(s, { sheet_id: 'MM/fantasy/en', cues: [], active: [{ ...bug2, seq: 3 }] });
    expect(s.sheetId).toBe('MM/fantasy/en');
    expect(ids(s.onAir)).toEqual(['scorebug@correction-9']);
    expect(s.ruledOut).toEqual(['goal-1']);
  });

  it('starts from a snapshot and forgets what is ahead of a backwards seek', () => {
    const after = startSheet(initialCueState(), { sheet_id: SHEET, last_seq: 6, active: [correction, bug2] }, ['goal-1']);
    expect(after.ruledOut).toEqual(['goal-1']);
    const before = startSheet(after, { sheet_id: SHEET, last_seq: 2, active: [goalShow, bug1] }, []);
    expect(before.ruledOut).toEqual([]);
    expect(ids(before.onAir)).toEqual(['goal-1@full_screen', 'scorebug@goal-1']);
  });

  it('ruleOut sends on-screen cards out once and is idempotent', () => {
    const card = { moment_id: 'goal-1', show_at_s: 10, duration_s: 8 } as never;
    const s = ruleOut(initialCueState(), ['goal-1'], [card], 12);
    expect(s.exiting).toHaveLength(1);
    expect(ruleOut(s, ['goal-1'], [card], 12)).toBe(s);
    expect(ruleOut(initialCueState(), ['goal-1'], [card], 40).exiting).toHaveLength(0); // already off screen
  });

  it('stays bounded', () => {
    let s = initialCueState();
    for (let i = 1; i <= MAX_SEEN + 50; i++) s = applyCues(s, { sheet_id: SHEET, cues: [cue(i, { cue_id: `p${i}`, layer: 'pitch_tag' })] });
    expect(s.seen.length).toBeLessThanOrEqual(MAX_SEEN);
    expect(s.onAir.filter((c) => c.layer === 'pitch_tag')).toHaveLength(3);
    expect(s.log.length).toBeLessThanOrEqual(30);
  });
});
