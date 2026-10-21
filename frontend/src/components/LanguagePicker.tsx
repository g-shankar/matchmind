import type React from 'react';
import { ChevronDown, Globe, Languages } from 'lucide-react';
import type { Language, LanguageInfo, OverlayCard, Recap } from '../api/contract';
import { useI18n } from '../i18n';
import { textLanguage } from '../lib/languages';
import { cx } from './ui';

const reasonLabel = (info: LanguageInfo, t: (k: string) => string) =>
  info.reason === 'not_in_demo' ? t('world.notInDemo') : t('world.off');

// Native select so it works with a screen reader and a phone's own picker; styled as a broadcast chip.
export const LanguagePicker: React.FC<{
  value: Language;
  languages: LanguageInfo[];
  onChange: (language: Language) => void;
}> = ({ value, languages, onChange }) => {
  const { t } = useI18n();
  const studio = languages.filter((l) => l.source === 'studio');
  const world = languages.filter((l) => l.source === 'translator');
  const worldLive = world.some((l) => l.available);
  const option = (l: LanguageInfo) => (
    <option key={l.code} value={l.code} lang={l.code} disabled={!l.available && l.code !== value}>
      {l.available ? l.name : `${l.name} · ${reasonLabel(l, t)}`}
    </option>
  );
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="relative flex items-stretch border border-pp-line bg-pp-deep focus-within:border-pp-pulse">
        <span className="sr-only">{t('lang.label')}</span>
        <Globe aria-hidden className="pointer-events-none absolute start-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-pp-mute" />
        <select
          data-testid="language-picker"
          value={value}
          title={t('world.hint')}
          onChange={(e) => onChange(e.target.value as Language)}
          className="min-h-[36px] cursor-pointer appearance-none bg-transparent pe-7 ps-7 font-display text-[13px] font-bold uppercase tracking-broadcast text-pp-chalk outline-none"
        >
          <optgroup label={t('world.studioGroup')}>{studio.map(option)}</optgroup>
          {world.length > 0 && <optgroup label={t('world.worldGroup')}>{world.map(option)}</optgroup>}
        </select>
        <ChevronDown aria-hidden className="pointer-events-none absolute end-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-pp-mute" />
      </label>
      {world.length > 0 && (
        <span
          data-testid="world-status"
          title={worldLive ? t('world.hint') : t('world.off')}
          className={cx(
            'inline-flex items-center gap-1 px-1.5 py-0.5 font-display text-[11px] font-bold uppercase tracking-broadcast',
            worldLive ? 'bg-pp-signal text-pp-night' : 'border border-dashed border-pp-line text-pp-mute',
          )}
        >
          <Languages aria-hidden className="h-3 w-3" />
          {worldLive ? t('world.statusLive') : t('world.statusOff')}
        </span>
      )}
    </div>
  );
};

/** Plain words for why a world language is shown in English. */
export function translationReasonText(t: (k: string) => string, reason: string | null | undefined): string {
  const key = `world.reason.${reason ?? 'other'}`;
  const text = t(key);
  return text === key ? t('world.reason.other') : text;
}

type Translatable =Pick<OverlayCard | Recap, 'language' | 'text_language' | 'translated_by' | 'fallback_reason'>;

// "Translated by Azure AI Translator", or why a world language is shown in English. Nothing for studio text.
export const TranslationTag: React.FC<{ item: Translatable; className?: string }> = ({ item, className }) => {
  const { t } = useI18n();
  if (item.translated_by === 'azure_ai_translator') {
    return (
      <span
        data-testid="translation-tag"
        title={t('world.translatedHint')}
        className={cx(
          'inline-flex items-center gap-1 border border-pp-signal/60 px-1.5 py-0.5 font-display text-[10px] font-bold uppercase tracking-broadcast text-pp-signal',
          className,
        )}
      >
        <Languages aria-hidden className="h-3 w-3" />
        {t('world.translated')}
      </span>
    );
  }
  if (textLanguage(item) === item.language) return null;
  const reason = translationReasonText(t, item.fallback_reason);
  return (
    <span
      data-testid="translation-fallback"
      className={cx(
        'inline-flex items-center gap-1 border border-dashed border-pp-gold/60 px-1.5 py-0.5 text-[10px] font-semibold text-pp-gold',
        className,
      )}
    >
      <Languages aria-hidden className="h-3 w-3" />
      {t('world.inEnglishWhy', { reason })}
    </span>
  );
};
