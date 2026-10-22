import type React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import type { Recap } from '../api/contract';
import { makeFixture } from '../test/fixture';
import { RecapModal } from './RecapModal';

afterEach(cleanup);

const recap = (over: Partial<Recap> = {}): Recap => ({
  match_id: 'T-1',
  persona: 'casual',
  language: 'en',
  rtl: false,
  title: 'AAA v BBB recap',
  headline: 'AAA edge it',
  summary_paragraphs: ['AAA scored from a 0.31 chance.'],
  key_moments: [{ match_clock: '00:20', kind: 'goal', headline: 'Goal for AAA', moment_id: 'M-1' }],
  player_of_the_match_id: 'AAA-9',
  player_of_the_match: 'AAA Striker',
  stats: { xg_home: 0.31, mystery_key: 7 },
  generated_at_clock: '90:00',
  produced_by: 'template',
  fact_check: { ok: true, reasons: [] },
  ...over,
});

const renderModal = (props: Partial<React.ComponentProps<typeof RecapModal>> = {}, lang = 'en') => {
  const onClose = vi.fn();
  render(
    <I18nProvider lang={lang}>
      <RecapModal open onClose={onClose} recap={recap()} loading={false} teams={makeFixture().teams} {...props} />
    </I18nProvider>,
  );
  return onClose;
};

describe('RecapModal', () => {
  it('renders the recap with the fact-check line and closes on Escape', () => {
    const onClose = renderModal();
    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(screen.getByText('Every number checked against the stats engine')).toBeTruthy();
    expect(screen.getByText('AAA Striker')).toBeTruthy();
    expect(screen.getByText(`${makeFixture().teams.home.name} chance quality (xG)`)).toBeTruthy();
    expect(document.activeElement?.getAttribute('aria-label')).toBe('Close recap');
    fireEvent.keyDown(document.activeElement!, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('shows match numbers with human labels and hides internal fields', () => {
    renderModal({
      recap: recap({
        stats: { home: 'AAA', generated_at: '90:00', n_big_chances: 4, score_w: 2, score_l: 1, potm_short: 'Striker', potm_tackles: 3, mystery_key: 7 },
      }),
    });
    const table = screen.getByRole('table');
    expect(table.textContent).toContain('Big chances');
    expect(table.textContent).toContain('Player of the match tackles won');
    for (const raw of ['generated at', 'n big chances', 'score w', 'score l', 'potm short', 'potm tackles', 'mystery key', 'home']) {
      expect(table.textContent?.toLowerCase()).not.toContain(raw);
    }
  });

  it('keeps Tab inside the dialog and gives focus back to what opened it', () => {
    const opener = document.createElement('button');
    opener.textContent = 'Recap';
    document.body.appendChild(opener);
    opener.focus();
    const onClose = vi.fn();
    const { rerender } = render(
      <I18nProvider lang="en">
        <RecapModal open onClose={onClose} recap={recap()} loading={false} teams={null} />
      </I18nProvider>,
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-labelledby')).toBe('recap-title');
    const buttons = dialog.querySelectorAll('button');
    const last = buttons[buttons.length - 1] as HTMLElement;
    last.focus();
    fireEvent.keyDown(last, { key: 'Tab' });
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(document.activeElement).toBe(buttons[0]);
    fireEvent.keyDown(buttons[0], { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(last);
    rerender(
      <I18nProvider lang="en">
        <RecapModal open={false} onClose={onClose} recap={recap()} loading={false} teams={null} />
      </I18nProvider>,
    );
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });

  it('lists fact-check reasons when the check failed', () => {
    renderModal({ recap: recap({ fact_check: { ok: false, reasons: ['0.5 not in facts'] } }) });
    expect(screen.getByText('0.5 not in facts')).toBeTruthy();
    expect(screen.queryByText('Every number checked against the stats engine')).toBeNull();
  });

  it('shows the empty state when there is no recap', () => {
    renderModal({ recap: null });
    expect(screen.getByText('Recap is not available yet')).toBeTruthy();
  });

  it('shows a loading state, and nothing when closed', () => {
    renderModal({ loading: true });
    expect(screen.getByRole('status')).toBeTruthy();
    cleanup();
    renderModal({ open: false });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('follows the page direction in Arabic', () => {
    renderModal({ recap: null }, 'ar');
    expect(screen.getByText('الملخص غير متاح بعد')).toBeTruthy();
    expect(screen.getByRole('dialog').closest('[dir]')?.getAttribute('dir')).toBe('rtl');
  });
});

describe('RecapModal in catch-up mode', () => {
  it('shows the player of the match as hidden in the story so far', () => {
    const story = {
      match_id: 'T-1', persona: 'casual' as const, language: 'en' as const, rtl: false,
      title: 'The story so far', headline: 'Catch up without the score', summary_paragraphs: ['At 30:00: xG 1.2 to 0.4.'],
      key_moments: [], player_of_the_match_id: null, player_of_the_match: null, stats: {},
      generated_at_clock: '30:00', produced_by: 'template' as const, fact_check: { ok: true, reasons: [] }, spoiler_free: true,
    };
    render(<I18nProvider lang="en"><RecapModal open onClose={() => {}} recap={story} loading={false} teams={null} /></I18nProvider>);
    expect(screen.getByText('Hidden')).toBeTruthy();
  });
});
