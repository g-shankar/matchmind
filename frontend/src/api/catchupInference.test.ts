// Catch-up mode over the whole recorded demo, through the offline mock server: nothing in the
// stream marks a goal by itself (the live server is checked the same way in
// backend/tests/test_spoilers.py::test_catch_up_stream_has_no_goal_marker).
import { describe, expect, it, vi } from 'vitest';
import type { MatchEvent, ServerMessage } from './contract';
import { MockMatchServer, type DemoFixture } from './mockServer';
import recording from '../../public/demo/demo-match.json?raw';

const fixture = JSON.parse(recording) as DemoFixture;
const flush = () => new Promise((r) => setTimeout(r, 0));
// Unique to each event, so trivially "separating": they say nothing about outcomes.
const IDENTITY = new Set(['event_id', 'match_clock', 'clock_s', 'player_id', 'receiver_id']);

function flat(o: Record<string, unknown>, prefix = '', out: Record<string, unknown> = {}) {
  for (const [k, v] of Object.entries(o)) {
    if (v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length) flat(v as Record<string, unknown>, `${prefix}${k}.`, out);
    else out[`${prefix}${k}`] = v;
  }
  return out;
}

/** Fields one rule on a single value tells goals from other shots with. */
function separating(goals: MatchEvent[], others: MatchEvent[]): string[] {
  const g = goals.map((e) => flat(e as unknown as Record<string, unknown>));
  const o = others.map((e) => flat(e as unknown as Record<string, unknown>));
  const keys = new Set([...g, ...o].flatMap((e) => Object.keys(e)));
  const found: string[] = [];
  for (const key of keys) {
    if (IDENTITY.has(key)) continue;
    const gv = g.map((e) => e[key]);
    const ov = o.map((e) => e[key]);
    if ([...gv, ...ov].every((v) => typeof v === 'number')) {
      const [gn, on] = [gv as number[], ov as number[]];
      if (Math.min(...gn) > Math.max(...on) || Math.max(...gn) < Math.min(...on)) found.push(key);
    } else {
      const seen = new Set(ov.map((v) => JSON.stringify(v ?? null)));
      if (!gv.some((v) => seen.has(JSON.stringify(v ?? null)))) found.push(key);
    }
  }
  return found;
}

describe('catch-up stream of the recorded demo', () => {
  it('has no kick-off, no numbering and no single field that marks a goal', async () => {
    vi.useFakeTimers({ toFake: ['setInterval'] });
    const messages: ServerMessage[] = [];
    const server = new MockMatchServer(fixture, (m) => messages.push(m), { profile: { spoilers: false }, speed: 60, autoplay: true });
    await flush();
    let guard = 0;
    while (!messages.some((m) => m.type === 'MATCH_END') && guard++ < 100_000) server.step(1);
    server.close();
    vi.useRealTimers();

    const events = messages.flatMap((m) => (m.type === 'MATCH_TICK' ? [m.data.event] : []));
    const snapshotEvents = messages.flatMap((m) => (m.type === 'INITIAL_SNAPSHOT' ? m.data.recent_events ?? [] : []));
    expect(events.length).toBeGreaterThan(2000);
    for (const e of [...events, ...snapshotEvents]) {
      expect(e.seq).toBeNull();
      expect(e.event_id).toMatch(/^ev-[0-9a-f]{16}$/);
      expect(e.type).not.toBe('var_review');
      if (e.type === 'pass') {
        expect(e.start).not.toBeNull();
        expect(e.details.pass_type).not.toBe('kickoff');
      }
    }
    expect(new Set(events.map((e) => e.event_id)).size).toBe(events.length);

    // Which played shots were goals, from the recording itself (the stream no longer says).
    const rawShots = fixture.ticks.map((t) => t.event).filter((e) => e.type === 'shot');
    const goalsAt = new Set(rawShots.filter((e) => e.outcome === 'goal').map((e) => `${e.period}:${e.clock_s}`));
    const shots = events.filter((e) => e.type === 'shot');
    const goals = shots.filter((e) => goalsAt.has(`${e.period}:${e.clock_s}`));
    const others = shots.filter((e) => !goalsAt.has(`${e.period}:${e.clock_s}`));
    expect(goals.length).toBe(goalsAt.size);
    expect(goals.length).toBeGreaterThanOrEqual(5);
    expect(separating(goals, others)).toEqual([]);

    // Cards point at the same catch-up ids as the events on the pitch.
    const ids = new Set(events.map((e) => e.event_id));
    const sources = messages.flatMap((m) => (m.type === 'MATCH_TICK' ? m.data.cards.flatMap((c) => c.evidence.map((v) => v.source_event_id)) : []));
    const linked = sources.filter((s): s is string => !!s);
    expect(linked.length).toBeGreaterThan(0);
    expect(linked.every((s) => s.startsWith('ev-'))).toBe(true);
    expect(linked.filter((s) => ids.has(s)).length).toBeGreaterThan(linked.length / 2);

    // Moment and card ids carry no full-feed numbering either (it would show where events
    // were withheld), anywhere in the stream: ticks, snapshots, bookmarks, the story.
    const text = JSON.stringify(messages);
    expect(text.match(/MM-[A-Z0-9-]+-\d{5}/g) ?? []).toEqual([]);
    const cards = messages.flatMap((m) => (m.type === 'MATCH_TICK' ? m.data.cards : m.type === 'INITIAL_SNAPSHOT' ? m.data.recent_cards : []));
    expect(cards.length).toBeGreaterThan(10);
    expect(cards.every((c) => /^mo-[0-9a-f]{16}$/.test(c.moment_id) && /^cd-[0-9a-f]{16}$/.test(c.card_id))).toBe(true);
    // The catch-up id still opens the moment, and the answer is in catch-up ids too.
    const card = await server.getMoment(cards[0].moment_id, 'casual', 'en', null);
    expect(card?.moment_id).toBe(cards[0].moment_id);
    expect(JSON.stringify(card)).not.toMatch(/MM-[A-Z0-9-]+-\d{5}/);
    expect(await server.getMoment('mo-0000000000000000', 'casual', 'en', null)).toBeNull();
  });
});
