import { describe, expect, it } from 'vitest';
import { sanitizeProfile } from './useMatch';

describe('sanitizeProfile', () => {
  it('keeps only known fields with allowed values', () => {
    const p = sanitizeProfile({ x: 1, persona: 'bogus', language: 'ar', favourite_team: 'NBR', focus_player_id: '<b>', focus_metric: 'xg' });
    expect(p).toEqual({ persona: 'casual', language: 'ar', favourite_team: 'NBR', focus_player_id: null, focus_metric: 'xg' });
  });

  it('falls back to defaults for junk', () => {
    expect(sanitizeProfile('nope').language).toBe('en');
  });

  it('keeps world languages and drops unknown ones', () => {
    expect(sanitizeProfile({ language: 'zh-Hans' }).language).toBe('zh-Hans');
    expect(sanitizeProfile({ language: 'sw' }).language).toBe('sw');
    expect(sanitizeProfile({ language: 'zh' }).language).toBe('en');
  });
});

describe('urlProfile', () => {
  it('pins persona, language and club from the link and ignores unknown values', async () => {
    const { urlProfile } = await import('./useMatch');
    const { DEFAULT_PROFILE } = await import('../api/mockServer');
    expect(urlProfile(DEFAULT_PROFILE, '?persona=tactical&lang=es&club=NBR')).toMatchObject({ persona: 'tactical', language: 'es', favourite_team: 'NBR' });
    const base = { ...DEFAULT_PROFILE, persona: 'fantasy' as const, language: 'ar' as const };
    expect(urlProfile(base, '?persona=boss&lang=xx&club=<script>')).toMatchObject({ persona: 'fantasy', language: 'ar', favourite_team: null });
    expect(urlProfile(base, '')).toEqual(base);
  });
});
