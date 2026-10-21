import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import type { BetterOptionReplay, UnfoundRunReplay } from '../api/contract';
import { makeFixture, event } from '../test/fixture';
import { Pitch2D, boxAround, decimalsOf } from './Pitch2D';

const teams = makeFixture().teams;

const betterReplay: BetterOptionReplay = {
  shot_event_id: 'T-1-50',
  shooter_id: 'AAA-9',
  teammate_id: 'AAA-10',
  shot_chance_quality: 0.06,
  alt_chance_quality: 0.41,
  pass_success: 0.82,
  alt_value: 0.34,
  times_better: 5.6,
  pass_distance_m: 9.4,
  nearest_marker_m: 4.3,
  shooter_pos: { x: 84, y: 22 },
  teammate_pos: { x: 92, y: 30 },
  defenders: [{ x: 90, y: 24 }, { x: 95, y: 36 }],
  keeper: { x: 103, y: 34 },
};

const runReplay: UnfoundRunReplay = {
  run_event_id: 'T-1-60',
  runner_id: 'AAA-9',
  carrier_id: 'AAA-10',
  found: false,
  pass_on_at_s: 1.2,
  pass_on_clock: '52:14',
  clear_of_line_m: 3.8,
  projected_chance_quality: 0.38,
  one_on_one: true,
  carrier_pos: { x: 60, y: 40 },
  runner_path: [{ x: 72, y: 28 }, { x: 78, y: 27 }, { x: 86, y: 29 }],
  target: { x: 86, y: 29 },
  defenders_at_pass: [{ x: 76, y: 40 }, { x: 75, y: 20 }, { x: 77, y: 30 }],
};

afterEach(cleanup);

describe('Pitch2D', () => {
  it('draws the better-option replay labels and no live event', () => {
    render(
      <I18nProvider lang="en">
        <Pitch2D teams={teams} event={event(1, 10)} replay={betterReplay} showTags />
      </I18nProvider>,
    );
    expect(screen.getByTestId('replay-verdict').textContent).toContain('5.6× better chance');
    expect(screen.getByTestId('replay-shot').textContent).toContain('0.06');
    expect(screen.getByTestId('replay-alt').textContent).toContain('0.41');
    expect(screen.getByTestId('replay-odds').textContent).toContain('82%');
    expect(screen.getByTestId('replay-nearest').textContent).toContain('4.3 m');
    expect(screen.queryByTestId('event-line')).toBeNull();
    expect(screen.queryByTestId('event-tags')).toBeNull();
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('5.6 times better');
  });

  it('draws the unfound-run replay labels', () => {
    render(
      <I18nProvider lang="en">
        <Pitch2D teams={teams} event={null} replay={runReplay} />
      </I18nProvider>,
    );
    expect(screen.getByTestId('replay-pass-on').textContent).toBe('Pass was on at 52:14');
    expect(screen.getByTestId('replay-clear').textContent).toContain('3.8 m clear of the line');
    expect(screen.getByTestId('replay-one-on-one').textContent).toBe('1-on-1');
    expect(screen.getByTestId('replay-projected').textContent).toContain('0.38');
  });

  it('only shows the layers up to the current story step', () => {
    render(
      <I18nProvider lang="en">
        <Pitch2D teams={teams} event={null} replay={betterReplay} replayStep={1} />
      </I18nProvider>,
    );
    expect(screen.getByTestId('replay-shot')).toBeTruthy();
    expect(screen.queryByTestId('replay-odds')).toBeNull();
    expect(screen.queryByTestId('replay-verdict')).toBeNull();
  });

  it('shows speed and distance tags from metrics only', () => {
    const { rerender } = render(
      <I18nProvider lang="en">
        <Pitch2D teams={teams} event={event(1, 10)} showTags />
      </I18nProvider>,
    );
    expect(screen.getByTestId('tag-speed').textContent).toContain('60 km/h');
    expect(screen.getByTestId('tag-distance').textContent).toContain('20.0 m');

    const base = event(2, 12);
    const bare = event(2, 12, {
      metrics: { ...base.metrics, pass_distance_m: null, ball_speed_kmh: null, player_speed_kmh: null },
    });
    rerender(
      <I18nProvider lang="en">
        <Pitch2D teams={teams} event={bare} showTags />
      </I18nProvider>,
    );
    expect(screen.queryByTestId('tag-distance')).toBeNull();
    expect(screen.queryByTestId('tag-speed')).toBeNull();
    expect(screen.queryByText(/\d m$/)).toBeNull();
  });

  it('hides player positions older than 90 seconds', () => {
    const { container } = render(
      <I18nProvider lang="en">
        <Pitch2D
          teams={teams}
          event={event(1, 200, { player_id: 'BBB-9', receiver_id: null })}
          positions={{ 'AAA-9': { x: 10, y: 10, clock_s: 190 }, 'AAA-10': { x: 20, y: 20, clock_s: 50 } }}
        />
      </I18nProvider>,
    );
    const transforms = Array.from(container.querySelectorAll('g[transform]')).map((g) => g.getAttribute('transform'));
    expect(transforms).toContain('translate(10 10)');
    expect(transforms).not.toContain('translate(20 20)');
  });

  it('keeps the pitch left-to-right in Arabic', () => {
    render(
      <I18nProvider lang="ar">
        <Pitch2D teams={teams} event={null} replay={betterReplay} />
      </I18nProvider>,
    );
    const wrapper = screen.getByTestId('pitch-wrapper');
    expect(wrapper.getAttribute('dir')).toBe('ltr');
    const svg = wrapper.querySelector('svg')!;
    expect(svg.getAttribute('transform')).toBeNull();
    expect(svg.getAttribute('style') ?? '').not.toContain('scaleX(-1)');
    expect(screen.getByTestId('replay-verdict').textContent).toContain('فرصة أفضل');
  });

  it('zooms a replay onto the action at the pitch aspect ratio, inside the pitch', () => {
    const box = boxAround([betterReplay.shooter_pos, betterReplay.teammate_pos, { x: 105, y: 34 }]);
    expect(box.w / box.h).toBeCloseTo(105 / 68, 1);
    expect(box.x + box.w).toBeLessThanOrEqual(105.05);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.w).toBeLessThan(60);
    expect(boxAround([])).toEqual({ x: 0, y: 0, w: 105, h: 68 });
  });

  it('shows evidence numbers at the precision of the payload', () => {
    expect(decimalsOf(0.198)).toBe(3);
    expect(decimalsOf(4)).toBe(0);
    expect(decimalsOf(3.75)).toBe(2);
  });
});
