import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { DEFAULT_PROFILE } from '../api/mockServer';
import { initialMatchState, type MatchViewState } from '../state/matchStore';
import type { MatchActions } from '../state/useMatch';
import { makeFixture } from '../test/fixture';
import { Shell } from '../App';
import { STUDIO_LANGUAGES } from '../lib/languages';
import { I18nProvider, makeI18n, toUiLanguage, translate, UI_LANGUAGES, type UiLanguage } from '.';
import { mergedStrings } from './strings';

// Every studio language (the ones the crew writes cards in) also has a full interface, so
// picking one never shows its cards inside chrome in another language.

const fixture = makeFixture();

const actions = (): MatchActions => ({
  togglePause: vi.fn(),
  setSpeed: vi.fn(),
  reset: vi.fn(),
  seek: vi.fn(),
  setView: vi.fn(),
  clearError: vi.fn(),
  retryNow: vi.fn(),
  getMoment: vi.fn().mockResolvedValue(null),
  loadRecap: vi.fn().mockResolvedValue(null),
  setSpoilers: vi.fn(),
  ask: vi.fn().mockResolvedValue({ ok: false, failure: 'unavailable' }),
});

const studioIn = (lang: UiLanguage) => {
  const match: MatchViewState = {
    ...initialMatchState({ ...DEFAULT_PROFILE, language: lang }),
    status: 'live',
    teams: fixture.teams,
  };
  return render(
    <I18nProvider lang={lang}>
      <Shell match={match} actions={actions()} />
    </I18nProvider>,
  );
};

// Chrome a first-time viewer sees on the Studio: header, view tabs, audience picker, Ask panel.
const CHROME_KEYS = [
  'ask.title',
  'ask.subtitle',
  'ask.chip.score',
  'visit.audience',
  'persona.casual',
  'persona.tactical',
  'view.studio',
  'view.overlay',
  'view.split',
  'view.follow',
  'view.fan',
  'view.lab',
  'play.recap',
  'visit.source.replay',
  'visit.about.title',
  'visit.about.synthetic',
  'studio.feed.title',
  'studio.moments.title',
];

beforeEach(() => {
  window.history.replaceState(null, '', '/');
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ source: 'file' }) }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('interface languages', () => {
  it('cover every studio language', () => {
    expect([...UI_LANGUAGES].sort()).toEqual([...STUDIO_LANGUAGES].sort());
    for (const lang of STUDIO_LANGUAGES) expect(toUiLanguage(lang)).toBe(lang);
  });

  it('French and Japanese have their own text for every label that is not a shared term', () => {
    // Labels that read the same as English on purpose: names of languages and services, units,
    // xG/xA/VAR/PPDA, and words French shares with English. Anything else left in English fails.
    const both = [
      'lang.en', 'lang.es', 'lang.fr', 'unit.kmh', 'unit.km', 'pitch.xg', 'studio.chip.xg', 'studio.gauge.xg',
      'fan.stat.xg', 'fan.stat.xa', 'fan.my.xg', 'cue.var', 'audit.status.ok', 'health.provider.azure_openai',
      'health.provider.foundry_agents', 'health.orchestrator.agent_framework', 'lab.stats.ppda',
    ];
    const sameOnPurpose: Record<'fr' | 'ja', Set<string>> = {
      fr: new Set([
        ...both, 'view.studio', 'play.pause', 'common.minute', 'event.dribble', 'event.interception',
        'studio.gauge.chaos', 'studio.gauge.tempo', 'fan.follow.zoom', 'fan.stat.passes', 'fan.stat.interceptions',
        'fan.stat.sprints', 'fan.stat.band.sprint', 'fan.mx.sprint', 'fan.my.possession', 'health.agent', 'lab.jump',
        'lab.stats.possession', 'lab.stats.passes', 'lab.stats.interceptions', 'lab.stats.distance', 'lab.bench.kind',
        'lab.bench.f1Pixels', 'lab.kind.interception', 'lab.data.match', 'tag.discipline', 'tag.pressing',
        'pitch.minute',
      ]),
      // "AI", "GK" and "vs" are what Japanese broadcasts print.
      ja: new Set([...both, 'common.vs', 'produced.ai', 'pitch.keeper']),
    };
    for (const lang of ['fr', 'ja'] as const) {
      const same = Object.entries(mergedStrings.en)
        .filter(([k, en]) => mergedStrings[lang][k] === en && /[A-Za-z]{2,}/.test(en.replace(/\{\w+\}/g, '')))
        .filter(([k]) => !sameOnPurpose[lang].has(k))
        .map(([k]) => k);
      expect(same, `${lang} labels still in English: ${same.join(', ')}`).toEqual([]);
    }
  });

  it('format numbers with Western digits (decimal comma in French, as the cards print them)', () => {
    expect(makeI18n('fr').num(3.14159, 2)).toBe('3,14');
    expect(makeI18n('ja').num(3.14159, 2)).toBe('3.14');
    expect(makeI18n('ja').dir).toBe('ltr');
    expect(makeI18n('fr').dir).toBe('ltr');
  });

  for (const lang of ['fr', 'ja'] as const) {
    it(`render the Studio chrome in ${lang} with no English fallback`, async () => {
      studioIn(lang);
      expect(document.documentElement.lang).toBe(lang);
      expect(screen.getByRole('radiogroup', { name: translate(lang, 'visit.audience') })).toBeTruthy();
      expect(screen.getByRole('navigation', { name: translate(lang, 'visit.views') })).toBeTruthy();
      expect(await screen.findByText(translate(lang, 'ask.title'))).toBeTruthy();

      const text = document.body.textContent ?? '';
      for (const key of CHROME_KEYS) {
        const local = translate(lang, key);
        const en = translate('en', key);
        expect(text, `${lang}.${key}`).toContain(local);
        if (local !== en) {
          const word = new RegExp(`(^|[^\\p{L}])${en.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}($|[^\\p{L}])`, 'u');
          expect(text, `English "${en}" (${key}) on the ${lang} page`).not.toMatch(word);
        }
      }
    });
  }
});
