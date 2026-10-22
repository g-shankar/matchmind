import { describe, expect, it, vi } from 'vitest';
import type { AskAnswer, ServerMessage } from './contract';
import { MockMatchServer, type DemoAsk, type DemoFixture } from './mockServer';
import { catchUpIds, isSpoilerCard, scrubEvent, spoilerFreeBookmarks, spoilerFreeTick, withCatchUpIds } from './spoilers';
import { event, makeFixture } from '../test/fixture';

const flush = () => new Promise((r) => setTimeout(r, 0));

// The test match with a real score: 1-0 from the goal at tick 2, and a big chance at tick 1.
function scoredFixture(): DemoFixture {
  const f = makeFixture();
  for (const t of f.ticks.slice(2)) {
    t.score = { home: 1, away: 0 };
    t.state = { ...t.state, score_home: 1, score_away: 0 };
  }
  f.ticks[2].event.details = { score_home: 1, score_away: 0 };
  f.ticks[2].players_changed = [{ ...f.ticks[2].players_changed[0], goals: 1 }];
  f.moments.push({
    ...f.moments[0],
    moment_id: 'M-0',
    kind: 'big_chance',
    event_id: 'T-1-1',
    show_at_s: 10,
    match_clock: '00:10',
    texts: { casual: { en: { headline: 'Big chance for AAA', body: '', why: '' } } },
  });
  return f;
}

const answer = (clock: string, text: string): AskAnswer => ({
  status: 'answered',
  reason: null,
  intent: { kind: 'top_player', team: null, player_id: null, metric: 'xg' },
  understood_by: 'chip',
  answer: text,
  language: 'en',
  text_language: 'en',
  rtl: false,
  as_of: { clock, period: 1, clock_s: 0, ended: false },
  spoilers: true,
  evidence: [],
  moment_ids: [],
  metric: null,
  produced_by: 'template',
  fact_check: { ok: true, reasons: [] },
});

const askData: DemoAsk = {
  match_id: 'T-1',
  checkpoint_s: 300,
  chips: ['score', 'top_xg'],
  hidden: { en: 'The score is hidden in catch-up mode. Tap reveal to see it.' },
  checkpoints: [
    {
      tick_index: 0,
      clock: '00:00',
      period: 1,
      clock_s: 0,
      answers: { en: { score: answer('00:00', 'AAA 0-0 BBB at 00:00.'), top_xg: answer('00:00', 'Nobody yet.') } },
      stories: { en: { title: 'So far', headline: 'Catch up', summary_paragraphs: ['At 00:00: xG 0 to 0.'], stats: {}, fact_check: { ok: true, reasons: [] }, key_moment_ids: ['M-0', 'M-1'] } },
    },
    {
      tick_index: 3,
      clock: '46:40',
      period: 2,
      clock_s: 2800,
      answers: { en: { score: answer('46:40', 'AAA 1-0 BBB at 46:40.'), top_xg: answer('46:40', 'AAA Striker leads.') } },
      stories: {},
    },
  ],
};

async function start(spoilers: boolean) {
  vi.useFakeTimers({ toFake: ['setInterval'] });
  const messages: ServerMessage[] = [];
  const server = new MockMatchServer(scoredFixture(), (m) => messages.push(m), {
    profile: { spoilers },
    speed: 10,
    autoplay: true,
    askData,
  });
  await flush();
  return { server, messages };
}

const leaks = (payload: unknown) => {
  const text = JSON.stringify(payload);
  return /"(home_score|away_score|score_home|score_away|goals|assists)":\d/.test(text) || /"kind":"(goal|correction)"/.test(text) || /"outcome":"goal"/.test(text);
};

describe('catch-up mode in the offline demo', () => {
  it('never sends the score, a goal card, a shot outcome or the cue sheet', async () => {
    const { server, messages } = await start(false);
    server.step(1); // the whole test match
    expect(messages.some((m) => m.type === 'CUES')).toBe(false);
    const ticks = messages.filter((m) => m.type === 'MATCH_TICK');
    expect(ticks).toHaveLength(4);
    for (const m of messages) if (m.type !== 'MATCH_END') expect(leaks(m), JSON.stringify(m).slice(0, 200)).toBe(false);
    const snap = messages[0];
    expect(snap.type === 'INITIAL_SNAPSHOT' && snap.data.cue_sheet).toBeNull();
    server.close();
  });

  it('reveal sends one fresh snapshot with the real score; hiding again takes it away', async () => {
    const { server, messages } = await start(false);
    server.step(1);
    messages.length = 0;
    server.send({ action: 'set_view', spoilers: true });
    expect(messages.map((m) => m.type)).toEqual(['PROFILE_CHANGED', 'PERSONA_CHANGED', 'INITIAL_SNAPSHOT']);
    const snap = messages[2];
    if (snap.type !== 'INITIAL_SNAPSHOT') throw new Error('no snapshot');
    expect([snap.data.home_score, snap.data.away_score]).toEqual([1, 0]);
    expect(snap.data.recent_cards.some((c) => c.kind === 'goal')).toBe(true);
    messages.length = 0;
    server.send({ action: 'set_view', spoilers: false });
    const again = messages[2];
    expect(again.type === 'INITIAL_SNAPSHOT' && again.data.home_score).toBeNull();
    // A change that does not touch spoilers sends no snapshot.
    messages.length = 0;
    server.send({ action: 'set_view', language: 'es' });
    expect(messages.map((m) => m.type)).toEqual(['PROFILE_CHANGED', 'PERSONA_CHANGED']);
    server.close();
  });

  it('refuses a spoilers value that is not true or false', async () => {
    const { server, messages } = await start(true);
    messages.length = 0;
    server.send({ action: 'set_view', spoilers: 'no' as unknown as boolean });
    expect(messages.map((m) => m.type)).toEqual(['ERROR']);
    server.close();
  });

  it('the story so far is spoiler-free and leaves goals out of its key moments', async () => {
    const { server } = await start(false);
    const story = await server.getRecap('casual', 'en', false);
    expect(story).toMatchObject({ spoiler_free: true, player_of_the_match: null, generated_at_clock: '00:00' });
    expect(story?.key_moments.map((k) => k.moment_id)).toEqual(['M-0']);
    server.close();
  });
});

describe('Ask the studio in the offline demo', () => {
  it('answers chips from the latest checkpoint already played, never a later one', async () => {
    const { server } = await start(true);
    const early = await server.ask({ chip: 'top_xg', lang: 'en', spoilers: true });
    expect(early.ok && early.answer.answer).toBe('Nobody yet.');
    server.step(1);
    const late = await server.ask({ chip: 'top_xg', lang: 'en', spoilers: true });
    expect(late.ok && late.answer.as_of.clock).toBe('46:40');
    server.close();
  });

  it('typed questions need the live server', async () => {
    const { server } = await start(true);
    expect(await server.ask({ question: 'who is fastest', lang: 'en', spoilers: true })).toEqual({ ok: false, failure: 'needs_live' });
    server.close();
  });

  it('hides the score chip in catch-up mode and answers other languages in English', async () => {
    const { server } = await start(false);
    server.step(1);
    const res = await server.ask({ chip: 'score', lang: 'en', spoilers: false });
    expect(res.ok && res.answer.status).toBe('hidden');
    expect(res.ok && res.answer.answer).not.toMatch(/\d-\d/);
    const fr = await server.ask({ chip: 'top_xg', lang: 'fr', spoilers: true });
    expect(fr.ok && fr.answer).toMatchObject({ language: 'fr', text_language: 'en' });
    server.close();
  });
});

describe('spoiler scrub helpers', () => {
  it('drop outcomes and score details from shots and VAR reviews', () => {
    const shot = scrubEvent(event(1, 10, { type: 'shot', outcome: 'goal', details: { score_home: 1, score_away: 0, body_part: 'foot' } }));
    expect(shot.outcome).toBeNull();
    expect(shot.details).toEqual({ body_part: 'foot' });
    const pass = scrubEvent(event(2, 11));
    expect(pass.outcome).toBe('complete');
  });

  it('hide outcome geometry and feed numbering: shot end points, blockers and seq', () => {
    // Every goal ends inside the goal mouth, so the end point alone would give it away.
    const goal = scrubEvent(event(1, 10, { type: 'shot', outcome: 'goal', start: { x: 93, y: 35 }, end: { x: 105, y: 34.4 } }));
    expect(goal.end).toBeNull();
    expect(goal.start).toEqual({ x: 93, y: 35 });
    expect(goal.seq).toBeNull();
    const blocked = scrubEvent(event(1, 11, { type: 'shot', outcome: 'blocked', end: { x: 96, y: 30 }, details: { blocked_by: 'BBB-4' } }));
    expect(blocked.end).toBeNull();
    expect(blocked.details).toEqual({});
  });

  it('withhold kick-offs: every restart after the first whistle follows a goal', () => {
    const f = makeFixture();
    const tick = { ...f.ticks[1], cards: [] };
    const kickoff = { ...tick, event: { ...tick.event, type: 'pass' as const, start: { x: 52.5, y: 34 }, details: { pass_type: 'kickoff' } } };
    expect(spoilerFreeTick(kickoff)).toBeNull();
    expect(spoilerFreeTick({ ...kickoff, event: { ...kickoff.event, details: { pass_type: 'ground' } } })).not.toBeNull();
  });

  it('catch-up ids are stable, unique and unordered, and replace every event id in a payload', () => {
    const idFor = catchUpIds();
    const ids = Array.from({ length: 50 }, (_, i) => idFor(`T-1-${String(i).padStart(5, '0')}`));
    expect(new Set(ids).size).toBe(50);
    expect(ids.every((id) => /^ev-[0-9a-f]{16}$/.test(id))).toBe(true);
    expect(idFor('T-1-00003')).toBe(ids[3]);
    const card = { evidence: [{ source_event_id: 'T-1-00003' }, { source_event_id: null }], claims: [{ source_event_ids: ['T-1-00003'] }], replay: { shot_event_id: 'T-1-00004' } };
    expect(withCatchUpIds(card, idFor)).toEqual({ evidence: [{ source_event_id: ids[3] }, { source_event_id: null }], claims: [{ source_event_ids: [ids[3]] }], replay: { shot_event_id: ids[4] } });
  });

  it('withhold VAR review ticks altogether', () => {
    const f = makeFixture();
    const tick = { ...f.ticks[1], cards: [] };
    const review = { ...tick, event: { ...tick.event, type: 'var_review' as const, outcome: 'overturned', reviewed_event_id: 'x', review_reason: 'offside' as const } };
    expect(spoilerFreeTick(review)).toBeNull();
    expect(spoilerFreeTick(tick)).not.toBeNull();
  });

  it('spot spoiler cards by kind, retraction or result evidence', () => {
    const base = { kind: 'big_chance' as const, retracts: [], evidence: [] };
    expect(isSpoilerCard(base)).toBe(false);
    expect(isSpoilerCard({ ...base, kind: 'goal' })).toBe(true);
    expect(isSpoilerCard({ ...base, retracts: ['M-1'] })).toBe(true);
    expect(isSpoilerCard({ ...base, evidence: [{ label: 'Home', label_key: 'score_home', value: 1, unit: null, source_event_id: null }] })).toBe(true);
    expect(
      spoilerFreeBookmarks([
        { moment_id: 'a', kind: 'goal', match_clock: '1', clock_s: 1, period: 1, title: 'g' },
        { moment_id: 'b', kind: 'big_chance', match_clock: '2', clock_s: 2, period: 1, title: 'c', ruled_out: true },
      ]),
    ).toEqual([{ moment_id: 'b', kind: 'big_chance', match_clock: '2', clock_s: 2, period: 1, title: 'c', ruled_out: false }]);
  });
});
