import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import type { DecisionOption, OverlayCard } from '../api/contract';
import { makeFixture } from '../test/fixture';
import { ReplayCard } from './ReplayCard';

const teams = makeFixture().teams;

const opt = (o: Partial<DecisionOption> & Pick<DecisionOption, 'rank' | 'kind' | 'player_id' | 'score'>): DecisionOption => ({
  taken: o.kind === 'shot', chance_quality: o.score, pass_success: null, pass_distance_m: null, nearest_marker_m: null,
  onside: true, open: true, eligible: true, pos: { x: 90, y: 30 }, ...o,
});

const card: OverlayCard = {
  card_id: 'C-2', moment_id: 'M-9', kind: 'better_option', slot: 'full_screen', priority: 90, show_at_s: 2041,
  duration_s: 12, persona: 'casual', language: 'en', rtl: false,
  headline: 'Should Striker have squared it?', body: '', why: '', tactical_tag: 'decision', evidence: [],
  player_ids: ['AAA-9', 'AAA-10'], team: 'AAA', favourite_side: null, produced_by: 'template', fallback_reason: null,
  replay: {
    shot_event_id: 'T-1-50', shooter_id: 'AAA-9', teammate_id: 'AAA-10', shot_chance_quality: 0.06,
    alt_chance_quality: 0.41, pass_success: 0.82, alt_value: 0.34, times_better: 5.6, pass_distance_m: 9.4,
    nearest_marker_m: 4.3, shooter_pos: { x: 84, y: 22 }, teammate_pos: { x: 92, y: 30 },
    defenders: [{ x: 90, y: 24 }], keeper: { x: 103, y: 34 }, method: 'pass_value', method_version: 1,
    options: [
      opt({ rank: 1, kind: 'pass', player_id: 'AAA-10', score: 0.34, pos: { x: 92, y: 30 } }),
      opt({ rank: 2, kind: 'shot', player_id: 'AAA-9', score: 0.06, pos: { x: 84, y: 22 } }),
      opt({ rank: 3, kind: 'pass', player_id: 'AAA-7', score: 0.12, onside: false, eligible: false, pos: { x: 99, y: 40 } }),
    ],
  },
};

afterEach(cleanup);

const renderIn = (lang: 'en' | 'ar') =>
  render(
    <I18nProvider lang={lang}>
      <ReplayCard card={card} teams={teams} />
    </I18nProvider>,
  );

const current = () => document.querySelector('[data-testid="option-row"][aria-current="true"]')?.getAttribute('aria-label') ?? '';
const drawn = () => document.querySelector('[data-testid="replay-option-line"]')?.getAttribute('data-option');

describe('DecisionOptions', () => {
  it('lists every option with engine scores, marks the taken action and shows the method and caveat', () => {
    renderIn('en');
    expect(screen.getByText('Every option, ranked by the engine')).toBeTruthy();
    const rows = screen.getAllByTestId('option-row');
    expect(rows).toHaveLength(3);
    expect(rows.map((r) => r.textContent)).toEqual([expect.stringContaining('0.340'), expect.stringContaining('0.060'), expect.stringContaining('0.120')]);
    expect(screen.getAllByTestId('option-taken')).toHaveLength(1);
    expect(rows[1].getAttribute('aria-label')).toContain('Taken');
    expect(rows[2].getAttribute('aria-label')).toContain('Offside');
    expect(screen.getByTestId('option-method').textContent).toBe('Pass value model v1');
    expect(screen.getByTestId('option-caveat').textContent).toBe('A higher score is not proof it was the right decision.');
    expect(current()).toMatch(/^1\./);
    expect(drawn()).toBe('AAA-10');
  });

  it('steps with the buttons and arrow keys and redraws the chosen line', () => {
    renderIn('en');
    fireEvent.click(screen.getByTestId('option-next'));
    expect(current()).toMatch(/^2\./);
    expect(drawn()).toBe('AAA-9');
    const box = screen.getByTestId('decision-options');
    fireEvent.keyDown(box, { key: 'ArrowRight' });
    expect(drawn()).toBe('AAA-7');
    fireEvent.keyDown(box, { key: 'ArrowRight' });
    expect(drawn()).toBe('AAA-10'); // wraps
    fireEvent.click(screen.getByTestId('option-prev'));
    expect(drawn()).toBe('AAA-7');
    fireEvent.click(screen.getAllByTestId('option-row')[1]);
    expect(drawn()).toBe('AAA-9');
    expect(screen.getByTestId('option-live').textContent).toContain('Option 2 of 3');
  });

  it('shows the top three plus the action taken until expanded', () => {
    const many = { ...card, replay: { ...card.replay!, options: [
      opt({ rank: 1, kind: 'pass', player_id: 'AAA-10', score: 0.34 }),
      opt({ rank: 2, kind: 'pass', player_id: 'AAA-7', score: 0.2 }),
      opt({ rank: 3, kind: 'pass', player_id: 'AAA-8', score: 0.1 }),
      opt({ rank: 4, kind: 'pass', player_id: 'AAA-6', score: 0.08 }),
      opt({ rank: 5, kind: 'shot', player_id: 'AAA-9', score: 0.06 }),
    ] } } as OverlayCard;
    render(<I18nProvider lang="en"><ReplayCard card={many} teams={teams} /></I18nProvider>);
    expect(screen.getAllByTestId('option-row')).toHaveLength(4);
    expect(screen.getAllByTestId('option-taken')).toHaveLength(1);
    fireEvent.click(screen.getByText('All 5 options'));
    expect(screen.getAllByTestId('option-row')).toHaveLength(5);
    fireEvent.click(screen.getByText('Fewer options'));
    expect(screen.getAllByTestId('option-row')).toHaveLength(4);
  });

  it('flips the arrow keys for right-to-left Arabic', () => {
    renderIn('ar');
    const box = screen.getByTestId('decision-options');
    fireEvent.keyDown(box, { key: 'ArrowLeft' });
    expect(drawn()).toBe('AAA-9');
    expect(screen.getByTestId('option-caveat').textContent).not.toContain('higher score');
  });
});
