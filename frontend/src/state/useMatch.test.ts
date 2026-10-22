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

describe('link-pinned profile', () => {
  it('ignores an invalid club instead of clearing the saved one', async () => {
    const { urlProfile } = await import('./useMatch');
    const { DEFAULT_PROFILE } = await import('../api/mockServer');
    const base = { ...DEFAULT_PROFILE, favourite_team: 'HCY' };
    expect(urlProfile(base, '?club=<script>').favourite_team).toBe('HCY');
    expect(urlProfile(base, '?club=').favourite_team).toBe('HCY');
    expect(urlProfile(base, '?club=NBR').favourite_team).toBe('NBR');
    expect(urlProfile(base, '?persona=boss&lang=xx')).toEqual(base);
  });

  it('saves only the viewer\'s own changes, never the values a link pinned', async () => {
    const { saveProfileChanges } = await import('./useMatch');
    localStorage.setItem('pitchpulse.profile', JSON.stringify({ persona: 'casual', language: 'en', favourite_team: 'HCY' }));
    window.history.replaceState(null, '', '/?persona=tactical&lang=es&club=NBR#overlay');
    try {
      saveProfileChanges({ focus_metric: 'xg' });
      const saved = JSON.parse(localStorage.getItem('pitchpulse.profile') ?? '{}');
      expect(saved).toMatchObject({ persona: 'casual', language: 'en', favourite_team: 'HCY', focus_metric: 'xg' });
      saveProfileChanges({ language: 'ar' });
      expect(JSON.parse(localStorage.getItem('pitchpulse.profile') ?? '{}').language).toBe('ar');
    } finally {
      window.history.replaceState(null, '', '/');
      localStorage.clear();
    }
  });
});
