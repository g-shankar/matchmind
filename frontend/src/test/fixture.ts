import type { MatchEvent, MatchState, PlayerStats, TeamInfo } from '../api/contract';
import type { DemoFixture, FixtureTick } from '../api/mockServer';

const team = (id: string, color: string): TeamInfo => ({
  team_id: id,
  name: `${id} Town`,
  short_name: id,
  primary_color: color,
  secondary_color: '#000000',
  formation: '4-3-3',
  style: '',
  players: [
    { player_id: `${id}-9`, name: `${id} Striker`, number: 9, position: 'ST', line: 'FWD' },
    { player_id: `${id}-10`, name: `${id} Playmaker`, number: 10, position: 'CAM', line: 'MID' },
  ],
});

const window5 = { possession_pct: 50, field_tilt_pct: 50, pressure_index: 20, shots: 0, xg: 0, final_third_passes: 0, box_entries: 0 };

export const state = (clock_s: number, over: Partial<MatchState> = {}): MatchState => ({
  match_id: 'T-1', clock_s, match_clock: '00:00', period: clock_s >= 2700 ? 2 : 1, home_id: 'AAA', away_id: 'BBB',
  score_home: 0, score_away: 0, home: { ...window5 }, away: { ...window5 }, momentum: 0, control_chaos: 0,
  tempo: 'Controlled', events_per_min: 10, turnovers_per_min: 1, avg_chain_passes: 4, xg_home: 0, xg_away: 0,
  shots_home: 0, shots_away: 0, ...over,
});

export const event = (seq: number, clock_s: number, over: Partial<MatchEvent> = {}): MatchEvent => ({
  event_id: `T-1-${seq}`, seq, match_clock: '00:00', clock_s, period: clock_s >= 2700 ? 2 : 1, type: 'pass',
  team: 'AAA', player_id: 'AAA-10', receiver_id: 'AAA-9', start: { x: 50, y: 30 }, end: { x: 70, y: 32 },
  outcome: 'complete', under_pressure: false, details: {},
  metrics: { pass_distance_m: 20, pass_difficulty: 30, progressive: true, ball_speed_kmh: 60, player_speed_kmh: null, sprint: false, fast_shot: false, chance_quality: null, distance_to_goal_m: null, pitch_zone: 'Middle Third', xt_delta: null },
  ...over,
});

const stats = (id: string, touches: number): PlayerStats => ({
  player_id: id, team: id.slice(0, 3), touches, passes: touches, passes_completed: touches, pass_accuracy: 100,
  key_passes: 0, shots: 0, goals: 0, assists: 0, xg: 0, xa: 0, tackles_won: 0, interceptions: 0,
  top_speed_kmh: 30, sprints: 0, distance_km: 0.1, carry_distance_m: 0,
});

const tick = (seq: number, clock_s: number, over: Partial<MatchEvent> = {}, s: Partial<MatchState> = {}): FixtureTick => ({
  event: event(seq, clock_s, over), clock: '00:00', period: clock_s >= 2700 ? 2 : 1, score: { home: 0, away: 0 },
  state: state(clock_s, s),
  control_chaos: { home_control_pct: 50, away_control_pct: 50, chaos_index: 0, current_tempo: 'Controlled', rolling_momentum_home: 0 },
  players_changed: [stats('AAA-10', seq)],
});

export function makeFixture(): DemoFixture {
  return {
    fixture_version: 1, match_id: 'T-1', source: 'test',
    teams: { home: team('AAA', '#2f6fde'), away: team('BBB', '#f08a24') },
    crew: { mode: 'template', model: null, breakers_open: [], moments: 1, fallbacks: 0, rejections: 0 },
    ticks: [
      tick(0, 0, { type: 'match_start' }),
      tick(1, 10),
      tick(2, 20, { type: 'shot', outcome: 'goal', player_id: 'AAA-9' }, { home: { ...window5, pressure_index: 75 } }),
      tick(3, 2800, {}, {}),
    ],
    moments: [
      {
        moment_id: 'M-1', kind: 'goal', slot: 'lower_third', priority: 95, show_at_s: 20, duration_s: 8,
        event_id: 'T-1-2', match_clock: '00:20', team: 'AAA', player_ids: ['AAA-9'],
        evidence: [{ label: 'chance_quality', value: 0.31, unit: null, source_event_id: 'T-1-2' }],
        tactical_tag: 'finish', replay: null,
        texts: {
          casual: { en: { headline: 'Goal for AAA', body: 'A 0.31 chance taken.', why: 'Lead.' }, es: { headline: 'Gol de AAA', body: 'Ocasión de 0.31.', why: 'Ventaja.' } },
          tactical: { en: { headline: 'Finish from 0.31 xG', body: 'Clinical.', why: 'Lead.' } },
        },
      },
    ],
    recaps: {},
  };
}
