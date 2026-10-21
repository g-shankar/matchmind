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
});
