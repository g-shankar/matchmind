// Read-aloud switch and the card reader behind it (lib/speech.ts). Off by default,
// nothing at all in capture mode, and a plain notice when the browser has no
// voice for the viewer's language (Arabic voices are often missing).
import React, { useEffect, useRef } from 'react';
import { Volume2, VolumeX } from 'lucide-react';
import type { OverlayCard } from '../api/contract';
import { useI18n } from '../i18n';
import { textLanguage } from '../lib/languages';
import { useReadAloud } from '../lib/speech';
import { activeCards, type MatchViewState } from '../state/matchStore';
import { cx } from './ui';

const SPOKEN_SLOTS: OverlayCard['slot'][] = ['lower_third', 'side_panel', 'full_screen'];
const MIN_GAP_MS = 6000; // at high playback speed, skip cards rather than queue a backlog

export function languageName(code: string, uiLang: string): string {
  try {
    return new Intl.DisplayNames([uiLang], { type: 'language' }).of(code) ?? code;
  } catch {
    return code;
  }
}

export const ReadAloudToggle: React.FC<{ match: MatchViewState }> = ({ match }) => {
  const { t, lang } = useI18n();
  const speech = useReadAloud();
  if (!speech.supported) return null;
  const language = match.profile.language;
  const missing = speech.enabled && !speech.hasVoice(language);
  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        aria-pressed={speech.enabled}
        onClick={() => speech.setEnabled(!speech.enabled)}
        title={t('speech.toggle')}
        className={cx(
          'flex min-h-[36px] items-center gap-1.5 border px-2.5 font-display text-xs font-bold uppercase tracking-broadcast',
          speech.enabled ? 'border-pp-signal bg-pp-signal/15 text-pp-signal' : 'border-pp-line bg-pp-deep text-pp-mute hover:text-pp-chalk',
        )}
      >
        {speech.enabled ? <Volume2 className="h-4 w-4" aria-hidden /> : <VolumeX className="h-4 w-4" aria-hidden />}
        <span>{t(speech.enabled ? 'speech.on' : 'speech.off')}</span>
      </button>
      {missing && (
        <p role="status" className="max-w-[260px] text-[11px] leading-tight text-pp-gold">
          {t('speech.noVoice', { language: languageName(language, lang) })}
        </p>
      )}
    </div>
  );
};

/** Speaks the headline of each new on-air card while read-aloud is on. Renders nothing. */
export const ReadAloudCards: React.FC<{ match: MatchViewState }> = ({ match }) => {
  const speech = useReadAloud();
  const spoken = useRef(new Set<string>());
  const lastAt = useRef(0);
  const clockS = match.playback.clock_s;
  const newest = speech.enabled
    ? SPOKEN_SLOTS.flatMap((slot) => activeCards(match.cards, clockS, slot, match.cue.ruledOut))
        .filter((c) => !spoken.current.has(c.card_id))
        .sort((a, b) => b.priority - a.priority)[0]
    : undefined;

  // Cards already on screen when it is switched on are not read out as a backlog.
  useEffect(() => {
    if (speech.enabled) for (const c of match.cards) spoken.current.add(c.card_id);
  }, [speech.enabled]);

  useEffect(() => {
    // The switch-on effect above runs first, so a card already on screen is skipped here.
    if (!newest || spoken.current.has(newest.card_id)) return;
    spoken.current.add(newest.card_id);
    const now = Date.now();
    if (now - lastAt.current < MIN_GAP_MS) return;
    if (speech.speak(newest.headline, textLanguage(newest))) lastAt.current = now;
  }, [newest, speech]);

  return null;
};
