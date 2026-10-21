import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import type { OverlayCard } from '../api/contract';
import { makeFixture } from '../test/fixture';
import { ReplayCard } from './ReplayCard';

const teams = makeFixture().teams;

const card: OverlayCard = {
  card_id: 'C-1', moment_id: 'M-9', kind: 'better_option', slot: 'full_screen', priority: 90, show_at_s: 2041,
  duration_s: 12, persona: 'casual', language: 'en', rtl: false,
  headline: 'Should Striker have squared it?', body: 'He shot from a 0.06 chance.', why: 'The pass was 5.6 times better.',
  tactical_tag: 'decision',
  evidence: [
    { label: 'shot_chance_quality', value: 0.06, unit: null, source_event_id: 'T-1-50' },
    { label: 'nearest_marker_m', value: 4.3, unit: 'm', source_event_id: 'T-1-50' },
    { label: 'times_better', value: 5.6, unit: null, source_event_id: null },
  ],
  player_ids: ['AAA-9', 'AAA-10'], team: 'AAA', favourite_side: null,
  produced_by: 'template', fallback_reason: 'AI switched off',
  replay: {
    shot_event_id: 'T-1-50', shooter_id: 'AAA-9', teammate_id: 'AAA-10', shot_chance_quality: 0.06,
    alt_chance_quality: 0.41, pass_success: 0.82, alt_value: 0.34, times_better: 5.6, pass_distance_m: 9.4,
    nearest_marker_m: 4.3, shooter_pos: { x: 84, y: 22 }, teammate_pos: { x: 92, y: 30 },
    defenders: [{ x: 90, y: 24 }], keeper: { x: 103, y: 34 },
  },
};

afterEach(cleanup);

describe('ReplayCard', () => {
  it('shows headline, evidence values, the template badge and the fallback reason', () => {
    const onClose = vi.fn();
    render(
      <I18nProvider lang="en">
        <ReplayCard card={card} teams={teams} onClose={onClose} />
      </I18nProvider>,
    );
    expect(screen.getByText('Should Striker have squared it?')).toBeTruthy();
    expect(screen.getByText('Should he have passed?')).toBeTruthy();
    const values = screen.getAllByTestId('evidence-value').map((n) => n.textContent);
    expect(values).toEqual(['0.06', '4.3m', '5.6']);
    expect(screen.getAllByText('Source event T-1-50')).toHaveLength(2);
    expect(screen.getByText('Template')).toBeTruthy();
    expect(screen.getByText(/Fact-checked/)).toBeTruthy();
    expect(screen.getByTestId('replay-fallback').textContent).toContain('AI switched off');
    fireEvent.click(screen.getByLabelText('Close'));
    expect(onClose).toHaveBeenCalled();
  });

  it('auto-advances the story and can be clicked', () => {
    vi.useFakeTimers();
    try {
      render(
        <I18nProvider lang="en">
          <ReplayCard card={card} teams={teams} />
        </I18nProvider>,
      );
      const current = () => document.querySelector('[aria-current="step"]')?.getAttribute('aria-label');
      expect(current()).toContain('Step 1');
      expect(screen.queryByTestId('replay-verdict')).toBeNull();
      act(() => {
        vi.advanceTimersByTime(2600);
      });
      expect(current()).toContain('Step 2');
      fireEvent.click(screen.getByLabelText('Step 3: The verdict'));
      expect(current()).toContain('Step 3');
      expect(screen.getByTestId('replay-verdict').textContent).toContain('5.6×');
    } finally {
      vi.useRealTimers();
    }
  });

  it('compact layout keeps pitch, headline and verdict only', () => {
    render(
      <I18nProvider lang="ar">
        <ReplayCard card={card} teams={teams} compact />
      </I18nProvider>,
    );
    expect(screen.getByTestId('replay-compact-verdict').textContent).toContain('5.6');
    expect(screen.queryAllByTestId('evidence-value')).toHaveLength(0);
    expect(screen.getByTestId('pitch-wrapper').getAttribute('dir')).toBe('ltr');
  });
});
