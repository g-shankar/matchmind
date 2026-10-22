// The Lab's counting stats in catch-up mode: a team's goals are the score, so the row goes.
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import type { BasicStats, BasicTeamStats } from '../api/contract';
import { StatsTables } from './Lab';

afterEach(cleanup);

const team = (team_id: string, goals: number | null): BasicTeamStats => ({
  team_id, name: team_id, possession_pct: 50, passes_completed: 10, passes_attempted: 12, pass_accuracy_pct: 83.3,
  shots: 4, shots_on_target: 2, goals, tackles_won: 1, tackles_attempted: 2, interceptions: 3, fouls: 1, ppda: 8.1,
  ppda_opponent_passes: 20, ppda_defensive_actions: 3, distance_km: 40.2, top_speed_kmh: 33.1,
});

const stats = (goals: [number | null, number | null]): BasicStats => ({
  match_id: 'T-1', clock: '60:00', period: 2, pass_accuracy_denominator: 'every pass attempt',
  physical_source: 'event_estimate', physical_label: 'Estimated', teams: { AAA: team('AAA', goals[0]), BBB: team('BBB', goals[1]) }, players: [],
});

const renderTables = (s: BasicStats, hideResult?: boolean) =>
  render(
    <I18nProvider lang="en">
      <StatsTables stats={s} hideResult={hideResult} />
    </I18nProvider>,
  );

describe('StatsTables', () => {
  it('shows goals when the result is not hidden', () => {
    renderTables(stats([2, 1]));
    expect(screen.getByRole('rowheader', { name: /goals/i })).toBeTruthy();
  });

  it('has no goals row in catch-up mode, even if a payload still carried goals', () => {
    renderTables(stats([2, 1]), true);
    expect(screen.queryByRole('rowheader', { name: /goals/i })).toBeNull();
    expect(screen.getByRole('rowheader', { name: /shots/i })).toBeTruthy();
  });

  it('drops the row when the server sent goals as null', () => {
    renderTables(stats([null, null]));
    expect(screen.queryByRole('rowheader', { name: /goals/i })).toBeNull();
  });
});

describe('StatsTables tracking label', () => {
  it('says "estimated from synthetic tracking" in the page language', () => {
    render(
      <I18nProvider lang="fr">
        <StatsTables stats={{ ...stats([1, 0]), physical_source: 'synthetic_tracking', physical_label: 'Estimated from synthetic tracking' }} />
      </I18nProvider>,
    );
    expect(screen.getByText('Estimé à partir du suivi synthétique')).toBeTruthy();
    expect(screen.queryByText('Estimated from synthetic tracking')).toBeNull();
  });
});
