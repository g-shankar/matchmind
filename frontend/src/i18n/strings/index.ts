// UI labels. Each feature keeps its own table in this folder; all tables are
// merged here and every key must exist in every UI language (see i18n.test.ts).
import core from './core';
import pitch from './pitch';
import broadcast from './broadcast';
import studio from './studio';
import fan from './fan';
import world from './world';
import cues from './cues';
import trust from './trust';

export const UI_LANGUAGES = ['en', 'es', 'ar'] as const;
export type UiLanguage = (typeof UI_LANGUAGES)[number];
export type StringTable = Record<UiLanguage, Record<string, string>>;

export const tables: Record<string, StringTable> = { core, pitch, broadcast, studio, fan, world, cues, trust };

export const mergedStrings: Record<UiLanguage, Record<string, string>> = {
  en: {},
  es: {},
  ar: {},
};

for (const table of Object.values(tables)) {
  for (const lang of UI_LANGUAGES) Object.assign(mergedStrings[lang], table[lang]);
}
