import { describe, expect, it } from 'vitest';
import { mergedStrings, tables, UI_LANGUAGES } from './strings';
import { makeI18n, translate } from '.';

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe('UI strings', () => {
  for (const [name, table] of Object.entries(tables)) {
    it(`${name}: every key exists in every language with the same placeholders`, () => {
      const keys = Object.keys(table.en);
      for (const lang of UI_LANGUAGES) {
        expect(Object.keys(table[lang]).sort()).toEqual([...keys].sort());
        for (const k of keys) {
          expect(table[lang][k].trim(), `${lang}.${k}`).not.toBe('');
          expect(placeholders(table[lang][k]), `${lang}.${k}`).toEqual(placeholders(table.en[k]));
        }
      }
    });
  }

  it('no two tables define the same key', () => {
    const seen = new Map<string, string>();
    for (const [name, table] of Object.entries(tables)) {
      for (const k of Object.keys(table.en)) {
        expect(seen.get(k), `${k} in ${name}`).toBeUndefined();
        seen.set(k, name);
      }
    }
  });

  it('Arabic is right-to-left and keeps Western digits', () => {
    const ar = makeI18n('ar');
    expect(ar.dir).toBe('rtl');
    expect(ar.num(3.14159, 2)).toBe('3.14');
    expect(makeI18n('es').dir).toBe('ltr');
  });

  it('fills placeholders and falls back to the key', () => {
    expect(translate('en', 'evidence.source', { id: 'E-1' })).toBe('Source event E-1');
    expect(translate('ar', 'no.such.key')).toBe('no.such.key');
    expect(Object.keys(mergedStrings.ar).length).toBe(Object.keys(mergedStrings.en).length);
  });
});
