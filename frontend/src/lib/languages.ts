// The languages a viewer can pick. The server sends the live list (with
// availability) in INITIAL_SNAPSHOT.languages; this copy is the shape before
// the first snapshot arrives, with world languages off until the server says otherwise.
import type { Language, LanguageInfo, OverlayCard, Recap } from '../api/contract';

const STUDIO: [Language, string, string][] = [
  ['en', 'English', 'English'],
  ['es', 'Español', 'Spanish'],
  ['fr', 'Français', 'French'],
  ['ar', 'العربية', 'Arabic'],
  ['ja', '日本語', 'Japanese'],
];

const WORLD: [Language, string, string][] = [
  ['pt', 'Português', 'Portuguese'],
  ['de', 'Deutsch', 'German'],
  ['hi', 'हिन्दी', 'Hindi'],
  ['zh-Hans', '简体中文', 'Chinese (Simplified)'],
  ['sw', 'Kiswahili', 'Swahili'],
  ['id', 'Bahasa Indonesia', 'Indonesian'],
  ['tr', 'Türkçe', 'Turkish'],
  ['ko', '한국어', 'Korean'],
];

export const STUDIO_LANGUAGES: Language[] = STUDIO.map(([c]) => c);
export const WORLD_LANGUAGES: Language[] = WORLD.map(([c]) => c);
export const ALL_LANGUAGES: Language[] = [...STUDIO_LANGUAGES, ...WORLD_LANGUAGES];

export const isWorldLanguage = (lang: string): boolean => (WORLD_LANGUAGES as string[]).includes(lang);

export function defaultLanguages(translatorAvailable = false): LanguageInfo[] {
  return [
    ...STUDIO.map(([code, name, english_name]) => ({
      code,
      name,
      english_name,
      source: 'studio' as const,
      available: true,
      rtl: code === 'ar',
      reason: null,
    })),
    ...WORLD.map(([code, name, english_name]) => ({
      code,
      name,
      english_name,
      source: 'translator' as const,
      available: translatorAvailable,
      rtl: false,
      reason: translatorAvailable ? null : ('translator_off' as const),
    })),
  ];
}

// Fallback reasons that are about translation, shown by the translation tag rather than as a raw reason.
const TRANSLATION_REASONS = new Set([
  'translator_off',
  'translation_rejected',
  'translator_budget',
  'translator_circuit_open',
  'translator_timeout',
  'translator_error',
  'translator_too_long',
  'translator_unsupported',
  'not_in_demo',
]);

export const isTranslationReason = (reason: string | null | undefined): boolean =>
  !!reason && TRANSLATION_REASONS.has(reason);

/** The language the text is really in (older payloads have no text_language: same as language). */
export const textLanguage = (item: Pick<OverlayCard | Recap, 'language' | 'text_language'>): Language =>
  item.text_language ?? item.language;
