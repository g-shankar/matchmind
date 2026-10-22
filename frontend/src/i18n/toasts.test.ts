import { describe, expect, it } from 'vitest';
import { CONNECTION_LOST, TOAST_CODES, TOAST_LANGUAGES, TOASTS, connectionLostText, toastText } from './toasts';

describe('error toasts', () => {
  it('every toast code has a non-empty text in every one of the five languages', () => {
    for (const lang of TOAST_LANGUAGES) {
      expect(Object.keys(TOASTS[lang]).sort(), lang).toEqual([...TOAST_CODES].sort());
      for (const code of TOAST_CODES) expect(TOASTS[lang][code].trim(), `${lang}.${code}`).not.toBe('');
    }
  });

  it('every non-English toast is actually translated', () => {
    for (const lang of TOAST_LANGUAGES.filter((l) => l !== 'en')) {
      for (const code of TOAST_CODES) expect(TOASTS[lang][code], `${lang}.${code}`).not.toBe(TOASTS.en[code]);
    }
  });

  it('shows the rate-limit refusals in the viewer language, never server English', () => {
    expect(toastText('Changing the view too fast. Wait a moment and try again.', 'view_too_fast', 'ar')).toBe(TOASTS.ar.view_too_fast);
    expect(toastText('Jumping around too fast. Wait a moment and try again.', 'jump_too_fast', 'ja')).toBe(TOASTS.ja.jump_too_fast);
  });

  it('recognises the English text when a frame has no code (older server, offline demo)', () => {
    expect(toastText('Jumping around too fast. Wait a moment and try again.', undefined, 'es')).toBe(TOASTS.es.jump_too_fast);
    expect(toastText('Speed must be 1, 10 or 60.', null, 'fr')).toBe(TOASTS.fr.bad_speed);
  });

  it('an unknown message stays as sent in English and becomes a general message elsewhere', () => {
    expect(toastText('Some new refusal.', 'other', 'en')).toBe('Some new refusal.');
    expect(toastText('Some new refusal.', 'other', 'ar')).toBe(TOASTS.ar.other);
    expect(toastText('Some new refusal.', null, 'de')).toBe('Some new refusal.');
  });
});

describe('the lost-connection notice (LC-15)', () => {
  it('has one sentence and a retry label in all five languages, translated', () => {
    expect(CONNECTION_LOST.en.message).toBe('Lost the connection to the match server. Trying again…');
    for (const lang of TOAST_LANGUAGES) {
      expect(CONNECTION_LOST[lang].message.trim(), lang).not.toBe('');
      expect(CONNECTION_LOST[lang].retry.trim(), lang).not.toBe('');
      if (lang !== 'en') {
        expect(CONNECTION_LOST[lang].message, lang).not.toBe(CONNECTION_LOST.en.message);
        expect(CONNECTION_LOST[lang].retry, lang).not.toBe(CONNECTION_LOST.en.retry);
      }
    }
  });

  it('falls back to English for a language without a table', () => {
    expect(connectionLostText('de')).toEqual({ lang: 'en', ...CONNECTION_LOST.en });
    expect(connectionLostText('ja').lang).toBe('ja');
  });
});
