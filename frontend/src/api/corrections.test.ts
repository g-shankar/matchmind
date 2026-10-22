// The recorded demo's VAR overturn, through the offline mock server and the store:
// live play, seek across the overturn, reconnect, and a profile change.
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Cue, ServerMessage } from './contract';
import { MockMatchServer, type DemoFixture } from './mockServer';
import { activeCards, initialMatchState, matchReducer, type MatchViewState } from '../state/matchStore';
import recording from '../../public/demo/demo-match.json?raw';

const fixture = JSON.parse(recording) as DemoFixture;
const correction = fixture.moments.find((m) => m.kind === 'correction')!;
const goalId = correction.retracts![0];
const goal = fixture.moments.find((m) => m.moment_id === goalId)!;
const ticks = fixture.ticks;
const varIndex = ticks.findIndex((t) => t.event.type === 'var_review');
const goalIndex = ticks.findIndex((t) => t.event.event_id === goal.event_id);

const flush = () => new Promise((r) => setTimeout(r, 0));
let server: MockMatchServer | null = null;
afterEach(() => server?.close());

async function connect(profile = {}) {
  vi.useFakeTimers({ toFake: ['setInterval'] });
  const messages: ServerMessage[] = [];
  server = new MockMatchServer(fixture, (m) => messages.push(m), { profile, speed: 60, autoplay: false });
  await flush();
  return { s: server, messages };
}

const fold = (messages: ServerMessage[], state: MatchViewState = initialMatchState()) =>
  messages.reduce((st, message) => matchReducer(st, { type: 'message', message }), state);

const cuesOf = (messages: ServerMessage[]): Cue[] => messages.flatMap((m) => (m.type === 'CUES' ? m.data.cues : []));

/** Seek to tick `from` and play forward through tick `to` (inclusive). */
function playThrough(s: MockMatchServer, from: number, to: number) {
  s.send({ action: 'seek', clock_s: ticks[from].event.clock_s, period: ticks[from].event.period });
  if (!(s as unknown as { running: boolean }).running) s.send({ action: 'toggle_pause' });
  let guard = 0;
  while (guard++ < 10_000) {
    s.step(0.05);
    if ((s as unknown as { next: number }).next > to) break;
  }
}

describe('VAR correction in the offline demo', () => {
  it('the recording has one overturned goal, ruled out by a correction moment', () => {
    expect(fixture.moments.filter((m) => m.kind === 'correction')).toHaveLength(1);
    expect(goal.kind).toBe('goal');
    expect(correction.reason).toBe('var_offside');
    expect(ticks[goalIndex].score).toEqual({ home: 2, away: 0 });
    expect(ticks[varIndex].score).toEqual({ home: 1, away: 0 });
    expect(ticks[varIndex].event.reviewed_event_id).toBe(goal.event_id);
    expect(ticks[ticks.length - 1].score).toEqual({ home: 2, away: 3 });
    const recap = fixture.recaps.casual!.en!;
    expect(recap.key_moments.map((k) => k.moment_id)).not.toContain(goalId);
  });

  it('live: the goal goes on air, then retract + supersede take it off and revert the scorebug', async () => {
    const { s, messages } = await connect();
    playThrough(s, goalIndex - 1, varIndex);
    const cues = cuesOf(messages);
    const ops = cues.map((c) => `${c.op}:${c.layer}:${c.moment_id}`);
    expect(ops).toContain(`show:${goal.slot}:${goalId}`);
    expect(ops).toContain(`retract:${goal.slot}:${goalId}`);
    expect(ops).toContain(`retract:scorebug:${goalId}`);
    expect(ops).toContain(`supersede:full_screen:${correction.moment_id}`);
    const bugs = cues.filter((c) => c.layer === 'scorebug');
    expect(bugs.at(-1)!.scorebug).toMatchObject({ score_home: 1, score_away: 0 });
    expect(bugs.at(-1)!.supersedes).toContain(`scorebug@${goalId}`);

    const view = fold(messages);
    expect(view.score).toEqual({ home: 1, away: 0 });
    expect(view.cue.ruledOut).toEqual([goalId]);
    const clock = ticks[varIndex].event.clock_s;
    const onAir = activeCards(view.cards, clock, undefined, view.cue.ruledOut).map((c) => c.moment_id);
    expect(onAir).toContain(correction.moment_id);
    expect(onAir).not.toContain(goalId);
    expect(view.cue.onAir.map((c) => c.moment_id)).not.toContain(goalId);
  });

  it('seek past the overturn: the snapshot never shows the goal as live', async () => {
    const { s, messages } = await connect();
    s.send({ action: 'seek', clock_s: ticks[varIndex + 2].event.clock_s, period: 1 });
    const snap = messages.at(-1)!;
    if (snap.type !== 'INITIAL_SNAPSHOT') throw new Error('expected a snapshot');
    expect([snap.data.home_score, snap.data.away_score]).toEqual([1, 0]);
    expect(snap.data.recent_cards.map((c) => c.moment_id)).not.toContain(goalId);
    expect(snap.data.cue_sheet!.active.map((c) => c.moment_id)).not.toContain(goalId);
    const bug = snap.data.cue_sheet!.active.find((c) => c.layer === 'scorebug')!;
    expect(bug.scorebug).toMatchObject({ score_home: 1, score_away: 0 });
    expect(snap.data.bookmarks.filter((b) => b.ruled_out).map((b) => b.moment_id)).toEqual([goalId]);
    const view = fold(messages);
    expect(view.cue.ruledOut).toEqual([goalId]);
  });

  it('seek back before the goal: nothing is ruled out yet, and replaying gives the same cues', async () => {
    const first = await connect();
    playThrough(first.s, goalIndex - 1, varIndex);
    const live = cuesOf(first.messages).filter((c) => c.op === 'retract' || c.op === 'supersede');
    const view = fold(first.messages);
    expect(view.cue.ruledOut).toEqual([goalId]);
    first.messages.length = 0;
    first.s.send({ action: 'seek', clock_s: ticks[goalIndex - 5].event.clock_s, period: 1 });
    const back = fold(first.messages, view);
    expect(back.cue.ruledOut).toEqual([]);
    expect(back.score).toEqual(ticks[goalIndex - 6].score);
    playThrough(first.s, goalIndex - 1, varIndex);
    const again = cuesOf(first.messages).filter((c) => c.op === 'retract' || c.op === 'supersede');
    expect(again.map((c) => c.cue_id)).toEqual(live.map((c) => c.cue_id));
  });

  it('a duplicate or replayed batch changes nothing', async () => {
    const { s, messages } = await connect();
    playThrough(s, goalIndex - 1, varIndex);
    const once = fold(messages);
    const cueMsgs = messages.filter((m) => m.type === 'CUES');
    const twice = fold([...cueMsgs].reverse(), once);
    expect(twice.cue.onAir).toEqual(once.cue.onAir);
    expect(twice.cue.ruledOut).toEqual(once.cue.ruledOut);
  });

  it('a profile change starts a new sheet that already knows the goal was ruled out', async () => {
    const { s, messages } = await connect();
    s.send({ action: 'seek', clock_s: ticks[varIndex + 1].event.clock_s, period: 1 });
    s.send({ action: 'set_view', persona: 'tactical' });
    s.send({ action: 'toggle_pause' });
    s.step(0.2);
    const cuesMsg = messages.find((m) => m.type === 'CUES');
    if (cuesMsg?.type !== 'CUES') throw new Error('expected CUES');
    expect(cuesMsg.data.sheet_id).toBe(`${fixture.match_id}/tactical/en`);
    expect(cuesMsg.data.active).toBeDefined();
    expect(cuesMsg.data.active!.map((c) => c.moment_id)).not.toContain(goalId);
  });
});
