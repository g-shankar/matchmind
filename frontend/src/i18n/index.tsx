import React, { createContext, useContext, useEffect, useMemo } from 'react';
import { UI_LANGUAGES, type UiLanguage, mergedStrings } from './strings';

export { UI_LANGUAGES };
export type { UiLanguage };

export const isRtl = (lang: string) => lang === 'ar';

type Vars = Record<string, string | number>;

export interface I18n {
  lang: UiLanguage;
  dir: 'ltr' | 'rtl';
  t: (key: string, vars?: Vars) => string;
  num: (value: number, digits?: number) => string;
}

// Western digits in every language so on-screen numbers match the fact-checked evidence.
const LOCALES: Record<UiLanguage, string> = { en: 'en-GB', es: 'es-ES', ar: 'ar-u-nu-latn' };

export const toUiLanguage = (lang: string | null | undefined): UiLanguage =>
  (UI_LANGUAGES as readonly string[]).includes(lang ?? '') ? (lang as UiLanguage) : 'en';

export function translate(lang: UiLanguage, key: string, vars?: Vars): string {
  const table = mergedStrings[lang];
  let text = table[key] ?? mergedStrings.en[key] ?? key;
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.split(`{${name}}`).join(String(value));
    }
  }
  return text;
}

export function makeI18n(lang: UiLanguage): I18n {
  const formatters = new Map<number, Intl.NumberFormat>();
  return {
    lang,
    dir: isRtl(lang) ? 'rtl' : 'ltr',
    t: (key, vars) => translate(lang, key, vars),
    num: (value, digits = 0) => {
      let f = formatters.get(digits);
      if (!f) {
        f = new Intl.NumberFormat(LOCALES[lang], {
          minimumFractionDigits: digits,
          maximumFractionDigits: digits,
        });
        formatters.set(digits, f);
      }
      return f.format(value);
    },
  };
}

const I18nContext = createContext<I18n>(makeI18n('en'));

export const I18nProvider: React.FC<{ lang: string; children: React.ReactNode }> = ({ lang, children }) => {
  const uiLang = toUiLanguage(lang);
  const value = useMemo(() => makeI18n(uiLang), [uiLang]);

  useEffect(() => {
    document.documentElement.lang = uiLang;
    document.documentElement.dir = value.dir;
  }, [uiLang, value.dir]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
};

export const useI18n = () => useContext(I18nContext);
