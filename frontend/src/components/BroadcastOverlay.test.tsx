import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import { cardForMoment, DEFAULT_PROFILE } from '../api/mockServer';
import { initialMatchState, matchReducer, type MatchViewState } from '../state/matchStore';
import type { FixtureMoment } from '../api/mockServer';
import type { MatchActions } from '../state/useMatch';
import { makeFixture } from '../test/fixture';
import { BroadcastOverlay } from './BroadcastOverlay';

afterEach(cleanup);

const actions = new Proxy({}, { get: () => vi.fn() }) as unknown as MatchActions;

function matchAt(clock_s: number, over: Partial<MatchViewState> = {}): MatchViewState {
  const fx = makeFixture();
  const card = cardForMoment(fx.moments[0], DEFAULT_PROFILE)!;
  const base = initialMatchState();
  return {
    ...base,
    status: 'demo',
    teams: fx.teams,
    crew: fx.crew,
    cards: [card],
    score: { home: 1, away: 0 },
    clock: '00:21',
    playback: { ...base.playback, clock_s },
    controlChaos: { home_control_pct: 58, away_control_pct: 42, chaos_index: 0, current_tempo: 'Controlled', rolling_momentum_home: 0 },
    ...over,
  };
}

const renderAt = (match: MatchViewState, lang = 'en') =>
  render(
    <I18nProvider lang={lang}>
      <BroadcastOverlay match={match} actions={actions} />
    </I18nProvider>,
  );

describe('BroadcastOverlay', () => {
  it('keeps the pitch backdrop out of the tab order (LC-6, aria-hidden-focus)', () => {
    const { container } = renderAt(matchAt(21, { positions: { 'AAA-9': { x: 10, y: 10, clock_s: 20 } } }));
    const hidden = Array.from(container.querySelectorAll('[aria-hidden="true"]'));
    expect(hidden.length).toBeGreaterThan(0);
    for (const h of hidden) expect(h.querySelector('[tabindex]:not([tabindex="-1"]), button, a[href], input, select')).toBeNull();
  });

  it('shows the lower third for an active card and hides it after its duration', () => {
    const { rerender } = renderAt(matchAt(22));
    expect(screen.getByTestId('lower-third').textContent).toContain('Goal for AAA');
    expect(screen.getByText('AI crew card · fact-checked template')).toBeTruthy();
    // show_at_s 20 + duration_s 8 -> gone at 29s.
    rerender(
      <I18nProvider lang="en">
        <BroadcastOverlay match={matchAt(29)} actions={actions} />
      </I18nProvider>,
    );
    expect(screen.queryByTestId('lower-third')).toBeNull();
  });

  it('scorebug shows short names and score from the payload', () => {
    renderAt(matchAt(22));
    const bug = screen.getByTestId('scorebug');
    expect(bug.textContent).toContain('AAA');
    expect(bug.textContent).toContain('BBB');
    expect(bug.textContent).toContain('1 - 0');
    expect(bug.textContent).toContain('58%');
  });

  it('highlights a favourite-side card in the favourite team colour', () => {
    const fx = makeFixture();
    const card = cardForMoment(fx.moments[0], { ...DEFAULT_PROFILE, favourite_team: 'AAA' })!;
    renderAt(matchAt(22, { cards: [card], profile: { ...DEFAULT_PROFILE, favourite_team: 'AAA' } }));
    expect(screen.getByText('Your team')).toBeTruthy();
  });

  it('producer toggle hides a layer', () => {
    renderAt(matchAt(22));
    const toggle = screen.getByRole('button', { name: 'Show or hide the Lower third layer' });
    expect(toggle.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(toggle);
    expect(screen.queryByTestId('lower-third')).toBeNull();
    expect(toggle.getAttribute('aria-pressed')).toBe('false');
  });

  it('labels the backdrop honestly and renders in Arabic', () => {
    renderAt(matchAt(22), 'ar');
    expect(screen.getByText('بث مباراة اصطناعية')).toBeTruthy();
    expect(screen.getByTestId('scorebug').textContent).toContain('AAA');
    expect(screen.queryByText(/4K/)).toBeNull();
  });

  describe('VAR corrections', () => {
    const correctionMoment = (): FixtureMoment => ({
      ...makeFixture().moments[0],
      moment_id: 'C-1',
      kind: 'correction',
      slot: 'full_screen',
      show_at_s: 30,
      duration_s: 15,
      event_id: 'T-1-3',
      match_clock: '00:30',
      evidence: [{ label: 'ruled_out_clock', value: '00:20', unit: null, source_event_id: 'T-1-2' }],
      texts: { casual: { en: { headline: 'No goal! VAR rules out Nine', body: 'The goal at 00:20 is ruled out.', why: 'Offside.' } } },
      retracts: ['M-1'],
      reason: 'var_offside',
    });

    /** The live path: the goal card is on air, then the tick carrying the correction card arrives. */
    function overturned(): MatchViewState {
      const fx = makeFixture();
      const goal = cardForMoment(fx.moments[0], DEFAULT_PROFILE)!;
      const corr = cardForMoment(correctionMoment(), DEFAULT_PROFILE)!;
      let m = matchAt(22, { cards: [goal] });
      m = matchReducer(m, {
        type: 'message',
        message: {
          type: 'MATCH_TICK',
          data: {
            event: { ...fx.ticks[1].event, clock_s: 24, type: 'var_review', reviewed_event_id: 'T-1-2' },
            clock: '00:24',
            period: 1,
            score: { home: 0, away: 0 },
            state: fx.ticks[1].state,
            control_chaos: fx.ticks[1].control_chaos,
            cards: [{ ...corr, show_at_s: 24 }],
            players_changed: [],
          },
        },
      });
      return m;
    }

    it('takes the goal card off with an exit animation and shows a clear supersede card', () => {
      renderAt(overturned());
      const card = screen.getByTestId('correction-card');
      expect(card.textContent).toContain('Ruled out by VAR');
      expect(card.textContent).toContain('No goal! VAR rules out Nine');
      // The goal is no longer a live lower third; it only appears in the leaving animation.
      expect(screen.queryByTestId('lower-third')?.closest('[data-testid=retracting-card]')).toBeTruthy();
      const leaving = screen.getByTestId('retracting-card');
      expect(leaving.className).toContain('animate-retract-out');
      expect(leaving.getAttribute('aria-hidden')).toBe('true');
    });

    it('reverts the scorebug and marks it as corrected by VAR', () => {
      renderAt(overturned());
      const bug = screen.getByTestId('scorebug');
      expect(bug.textContent).toContain('0 - 0');
      expect(screen.getByTestId('scorebug-var').textContent).toContain('VAR');
    });

    it('shows the reason from the cue sheet in Spanish and Arabic', () => {
      const m = overturned();
      const withCue = matchReducer(m, {
        type: 'message',
        message: {
          type: 'CUES',
          data: {
            sheet_id: 'T-1/casual/en',
            cues: [
              {
                schema_version: '1.0', cue_id: 'C-1@full_screen', seq: 1, op: 'supersede', layer: 'full_screen', moment_id: 'C-1',
                kind: 'correction', retracts: [], supersedes: ['M-1@lower_third'], clears: [], reason: 'var_offside',
                start: { period: 1, clock_s: 24, match_clock: '00:24', t_s: 24 }, duration_s: 15, end: null, priority: 95,
                collision: 'replace', persona: 'casual', language: 'en', rtl: false, text: null, evidence: [], source_event_ids: [],
                team: 'AAA', player_ids: [], produced_by: 'template', scorebug: null, ribbon: null, telestration: null,
              },
            ],
          },
        },
      });
      renderAt(withCue, 'es');
      expect(screen.getByTestId('correction-card').textContent).toContain('Anulado por el VAR');
      expect(screen.getByTestId('correction-card').textContent).toContain('Fuera de juego');
      cleanup();
      renderAt(withCue, 'ar');
      expect(screen.getByTestId('correction-card').textContent).toContain('ألغاه الفار');
      expect(screen.getByTestId('cue-log').textContent).toContain('استبدال');
    });

    it('capture mode renders only the graphics on a transparent stage', () => {
      render(
        <I18nProvider lang="en">
          <BroadcastOverlay match={overturned()} actions={actions} capture />
        </I18nProvider>,
      );
      const stage = screen.getByTestId('overlay-stage');
      expect(stage.className).toContain('bg-transparent');
      expect(document.documentElement.classList.contains('pp-capture')).toBe(true);
      expect(screen.queryByRole('button', { name: /Show or hide/ })).toBeNull();
      expect(screen.queryByTestId('cue-log')).toBeNull();
      expect(screen.queryByText('Synthetic match feed')).toBeNull();
      expect(screen.queryByTestId('phone-qr')).toBeNull();
      cleanup();
      render(
        <I18nProvider lang="en">
          <BroadcastOverlay match={overturned()} actions={actions} />
        </I18nProvider>,
      );
      expect(screen.getByTestId('phone-qr').className).toBe('relative hidden lg:block');
      expect(screen.queryByRole('img', { name: /Scan to open your fan view/ })).toBeNull();
      fireEvent.click(screen.getByRole('button', { name: 'Take it to your phone' }));
      expect(screen.getByRole('img', { name: /Scan to open your fan view/ })).toBeTruthy();
      cleanup();
      expect(document.documentElement.classList.contains('pp-capture')).toBe(false);
    });
  });
});
