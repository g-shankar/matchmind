import type React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import type { OverlayCard } from '../api/contract';
import { DEFAULT_PROFILE, cardForMoment, demoLanguages } from '../api/mockServer';
import { I18nProvider } from '../i18n';
import { defaultLanguages } from '../lib/languages';
import { initialMatchState } from '../state/matchStore';
import { makeFixture } from '../test/fixture';
import { LanguagePicker, TranslationTag } from './LanguagePicker';
import { NarrativeFeed } from './NarrativeFeed';
import { BroadcastOverlay } from './BroadcastOverlay';

afterEach(cleanup);

const ui = (node: React.ReactNode, lang = 'en') => render(<I18nProvider lang={lang}>{node}</I18nProvider>);
const option = (name: RegExp) => screen.getByRole('option', { name }) as HTMLOptionElement;

describe('LanguagePicker', () => {
  it('greys out world languages while Azure AI Translator is off', () => {
    ui(<LanguagePicker value="en" languages={defaultLanguages(false)} onChange={vi.fn()} />);
    const pt = option(/Português/);
    expect(pt.disabled).toBe(true);
    expect(pt.textContent).toContain('Off: needs Azure AI Translator');
    expect(pt.lang).toBe('pt');
    expect(option(/Español/).disabled).toBe(false);
    expect(screen.getByTestId('world-status').textContent).toContain('World languages: off');
    const groups = screen.getAllByRole('group');
    expect(groups.map((g) => g.getAttribute('label'))).toEqual(['Studio languages', 'World languages · Azure AI Translator']);
    expect(within(groups[1]).getAllByRole('option')).toHaveLength(8);
  });

  it('lets the viewer pick a world language once the translator is live', () => {
    const onChange = vi.fn();
    ui(<LanguagePicker value="en" languages={defaultLanguages(true)} onChange={onChange} />);
    expect(option(/한국어/).disabled).toBe(false);
    expect(screen.getByTestId('world-status').textContent).toContain('World languages: live');
    fireEvent.change(screen.getByTestId('language-picker'), { target: { value: 'ko' } });
    expect(onChange).toHaveBeenCalledWith('ko');
  });

  it('marks studio languages missing from the offline demo', () => {
    ui(<LanguagePicker value="en" languages={demoLanguages()} onChange={vi.fn()} />);
    const fr = option(/Français/);
    expect(fr.disabled).toBe(true);
    expect(fr.textContent).toContain('Not in the offline demo');
  });

  it('keeps a stored choice selectable so the picker never shows a wrong value', () => {
    ui(<LanguagePicker value="de" languages={defaultLanguages(false)} onChange={vi.fn()} />);
    expect(option(/Deutsch/).disabled).toBe(false);
    expect((screen.getByTestId('language-picker') as HTMLSelectElement).value).toBe('de');
  });
});

describe('translation tags on cards', () => {
  const fixture = makeFixture();
  const english = cardForMoment(fixture.moments[0], DEFAULT_PROFILE)!;
  const translated: OverlayCard = {
    ...english,
    card_id: 'M-1:casual:de',
    language: 'de',
    text_language: 'de',
    translated_by: 'azure_ai_translator',
    headline: 'Tor für AAA',
  };
  const offCard = cardForMoment(fixture.moments[0], { ...DEFAULT_PROFILE, language: 'pt' })!;

  it('says "Translated by Azure AI Translator" and marks the text language', () => {
    const match = { ...initialMatchState(DEFAULT_PROFILE), teams: fixture.teams, cards: [translated] };
    const { container } = ui(<NarrativeFeed match={match} actions={{} as never} onOpenReplay={vi.fn()} />);
    expect(screen.getByTestId('translation-tag').textContent).toContain('Translated by Azure AI Translator');
    expect(container.querySelector('article')?.getAttribute('lang')).toBe('de');
    expect(screen.queryByText(/translator_off/)).toBeNull();
  });

  it('says a world language is shown in English, in plain words, when the translator is off', () => {
    const match = { ...initialMatchState(DEFAULT_PROFILE), teams: fixture.teams, cards: [offCard] };
    const { container } = ui(<NarrativeFeed match={match} actions={{} as never} onOpenReplay={vi.fn()} />);
    expect(screen.getByTestId('translation-fallback').textContent).toBe('Shown in English: Azure AI Translator is off');
    expect(container.querySelector('article')?.getAttribute('lang')).toBe('en');
    expect(screen.queryByText(/translator_off/)).toBeNull(); // never the raw reason code
  });

  it('shows nothing extra on studio cards', () => {
    ui(<TranslationTag item={english} />);
    expect(screen.queryByTestId('translation-tag')).toBeNull();
    expect(screen.queryByTestId('translation-fallback')).toBeNull();
  });

  it('tags translated lower thirds on the broadcast view', () => {
    const match = {
      ...initialMatchState({ ...DEFAULT_PROFILE, language: 'de' }),
      teams: fixture.teams,
      cards: [{ ...translated, slot: 'lower_third' as const }],
      playback: { ...initialMatchState().playback, clock_s: translated.show_at_s + 1 },
    };
    ui(<BroadcastOverlay match={match} actions={{} as never} />);
    const third = screen.getByTestId('lower-third');
    expect(third.getAttribute('lang')).toBe('de');
    expect(within(third).getByTestId('translation-tag').textContent).toContain('Translated by Azure AI Translator');
  });
});
