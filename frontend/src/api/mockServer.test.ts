import { describe, expect, it, vi } from 'vitest';
import type { ServerMessage } from './contract';
import { MockMatchServer, cardForMoment, DEFAULT_PROFILE, seekIndex } from './mockServer';
import { makeFixture } from '../test/fixture';

const flush = () => new Promise((r) => setTimeout(r, 0));

async function start(profile = {}) {
  vi.useFakeTimers({ toFake: ['setInterval'] });
  const messages: ServerMessage[] = [];
  const server = new MockMatchServer(makeFixture(), (m) => messages.push(m), { profile, speed: 10, autoplay: true });
  await flush();
  return { server, messages };
}

describe('MockMatchServer', () => {
  it('opens with a snapshot carrying teams from the recording', async () => {
    const { server, messages } = await start();
    expect(messages[0].type).toBe('INITIAL_SNAPSHOT');
    if (messages[0].type === 'INITIAL_SNAPSHOT') expect(messages[0].data.teams.home.short_name).toBe('AAA');
    server.close();
  });

  it('lists languages honestly: recorded studio text on, the rest off with a reason', async () => {
    const { server, messages } = await start();
    const snap = messages[0];
    if (snap.type !== 'INITIAL_SNAPSHOT') throw new Error('no snapshot');
    const by = Object.fromEntries((snap.data.languages ?? []).map((l) => [l.code, l]));
    expect(Object.keys(by)).toHaveLength(13);
    expect(['en', 'es', 'ar'].every((c) => by[c].available)).toBe(true);
    expect(by.fr).toMatchObject({ source: 'studio', available: false, reason: 'not_in_demo' });
    expect(by['zh-Hans']).toMatchObject({ source: 'translator', available: false, reason: 'translator_off' });
    server.close();
  });

  it('plays ticks on the match clock and attaches the goal card', async () => {
    const { server, messages } = await start();
    server.step(0.15); // 15 s of match clock at 10x
    expect(messages.filter((m) => m.type === 'MATCH_TICK')).toHaveLength(2);
    server.step(0.06);
    const goal = messages.find((m) => m.type === 'MATCH_TICK' && m.data.event.seq === 2);
    expect(goal?.type === 'MATCH_TICK' && goal.data.cards[0].kind).toBe('goal');
    server.close();
  });

  it('does not wait out the half-time clock jump', async () => {
    const { server, messages } = await start();
    server.step(1); // 100 s of virtual time is enough because period 2 restarts at 2700
    expect(messages.filter((m) => m.type === 'MATCH_TICK')).toHaveLength(4);
    expect(messages.some((m) => m.type === 'PLAYBACK_CONTROL' && m.data.ended)).toBe(true);
    server.close();
  });

  it('pauses, rejects bad speeds and keeps viewer choices per connection', async () => {
    const { server, messages } = await start();
    server.send({ action: 'toggle_pause' });
    server.step(0.5);
    expect(messages.filter((m) => m.type === 'MATCH_TICK')).toHaveLength(0);
    server.send({ action: 'set_speed', speed_multiplier: 7 as never });
    expect(messages.at(-1)?.type).toBe('ERROR');
    server.send({ action: 'set_view', language: 'es', favourite_team: 'AAA' });
    const changed = messages.find((m) => m.type === 'PROFILE_CHANGED');
    expect(changed?.type === 'PROFILE_CHANGED' && changed.data.language).toBe('es');
    server.close();
  });

  it('seeks and rebuilds player stats up to the target', async () => {
    const { server, messages } = await start();
    server.send({ action: 'seek', clock_s: 15 });
    const snap = messages.at(-1);
    expect(snap?.type).toBe('INITIAL_SNAPSHOT');
    if (snap?.type === 'INITIAL_SNAPSHOT') {
      expect(snap.data.players.find((p) => p.player_id === 'AAA-10')?.touches).toBe(1);
    }
    server.close();
  });

  it('refuses a seek past full time or to a bad time, like the live server (EC-8)', async () => {
    const { server, messages } = await start();
    for (const action of [
      { action: 'seek' as const, clock_s: 99_999 },
      { action: 'seek' as const, clock_s: Number.NaN },
      { action: 'seek' as const, clock_s: -5 },
      { action: 'seek' as const, clock_s: 10, period: 3 },
    ]) {
      const before = messages.length;
      server.send(action);
      expect(messages.slice(before).map((m) => m.type)).toEqual(['ERROR']);
    }
    server.close();
  });

  it('sends a metric alert only for the focus metric', async () => {
    const { server, messages } = await start({ focus_metric: 'pressure' });
    server.step(0.25);
    const cards = messages.flatMap((m) => (m.type === 'MATCH_TICK' ? m.data.cards : []));
    const alert = cards.find((c) => c.slot === 'metric_alert');
    expect(alert?.evidence[0].value).toBe(75);
    expect(alert?.body).toContain('75');
    server.close();
  });
});

describe('cardForMoment', () => {
  const m = makeFixture().moments[0];

  it('falls back to English when a language is missing, and says so', () => {
    const card = cardForMoment(m, { ...DEFAULT_PROFILE, persona: 'tactical', language: 'ar' });
    expect(card?.language).toBe('ar');
    expect(card?.text_language).toBe('en');
    expect(card?.rtl).toBe(false);
    expect(card?.fallback_reason).toBe('not_in_demo');
    expect(card?.headline).toBe('Finish from 0.31 xG');
  });

  it('carries player identities from the recording onto the card', () => {
    const who = { player_id: m.player_ids[0] ?? 'AAA-10', name: 'Test Player', number: 10, team: 'AAA', position: 'ST' };
    expect(cardForMoment({ ...m, players: [who] }, DEFAULT_PROFILE)?.players).toEqual([who]);
    expect(cardForMoment(m, DEFAULT_PROFILE)?.players).toBeUndefined();
  });

  it('never pretends to translate: world languages are English with translator_off', () => {
    const card = cardForMoment(m, { ...DEFAULT_PROFILE, language: 'pt' });
    expect(card?.language).toBe('pt');
    expect(card?.text_language).toBe('en');
    expect(card?.translated_by).toBeNull();
    expect(card?.fallback_reason).toBe('translator_off');
    expect(card?.headline).toBe('Goal for AAA');
  });

  it('studio text in the recording keeps its own language and no fallback', () => {
    const card = cardForMoment(m, { ...DEFAULT_PROFILE, language: 'es' });
    expect(card?.text_language).toBe('es');
    expect(card?.fallback_reason).toBeNull();
  });

  it('marks and boosts the favourite side', () => {
    const card = cardForMoment(m, { ...DEFAULT_PROFILE, language: 'es', favourite_team: 'AAA' });
    expect(card?.favourite_side).toBe(true);
    expect(card?.priority).toBe(100);
    expect(card?.headline).toBe('Gol de AAA');
  });

  it('player cam keeps goals but drops other players moments', () => {
    const other = { ...m, kind: 'big_chance' as const };
    expect(cardForMoment(other, { ...DEFAULT_PROFILE, persona: 'player_spotlight', focus_player_id: 'BBB-9' })).toBeNull();
    expect(cardForMoment(m, { ...DEFAULT_PROFILE, persona: 'player_spotlight', focus_player_id: 'BBB-9' })).not.toBeNull();
  });
});

describe('seekIndex', () => {
  it('prefers second-half ticks from 2700 s', () => {
    expect(seekIndex(makeFixture().ticks, 2750)).toBe(3);
    expect(seekIndex(makeFixture().ticks, 5)).toBe(1);
  });
});
