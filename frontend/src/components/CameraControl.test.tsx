import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { I18nProvider } from '../i18n';
import { CAMERA_STORAGE_KEY, initialCamera, saveCamera } from '../lib/camera';
import { CameraControl, useCameraPreset } from './CameraControl';
import { Pitch2D, TACTICAL_TRANSFORM } from './Pitch2D';
import { makeFixture } from '../test/fixture';
import type { MatchEvent } from '../api/contract';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
beforeEach(() => {
  try {
    window.localStorage.clear();
  } catch {
    /* ignore */
  }
});

const Harness: React.FC = () => {
  const [cam, setCam] = useCameraPreset();
  return (
    <>
      <CameraControl value={cam} onChange={setCam} />
      <span data-testid="cam">{cam}</span>
    </>
  );
};

describe('camera presets', () => {
  it('deep link wins over the saved choice, unknown values fall back', () => {
    saveCamera('tactical');
    expect(initialCamera('?cam=follow')).toBe('follow');
    expect(initialCamera('?cam=drone')).toBe('tactical');
    window.localStorage.setItem(CAMERA_STORAGE_KEY, 'bogus');
    expect(initialCamera('')).toBe('wide');
  });

  it('survives blocked storage', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(initialCamera('')).toBe('wide');
    expect(() => saveCamera('follow')).not.toThrow();
  });

  it('is a labelled radio group, keyboard operable and remembered', () => {
    render(
      <I18nProvider lang="en">
        <Harness />
      </I18nProvider>,
    );
    const group = screen.getByRole('radiogroup', { name: 'Camera' });
    expect(group).toBeTruthy();
    const wide = screen.getByRole('radio', { name: /Wide camera/ });
    expect(wide.getAttribute('aria-checked')).toBe('true');
    act(() => {
      fireEvent.keyDown(wide, { key: 'ArrowRight' });
    });
    expect(screen.getByTestId('cam').textContent).toBe('tactical');
    expect(document.activeElement).toBe(screen.getByRole('radio', { name: /Tactical camera/ }));
    act(() => {
      fireEvent.keyDown(document.activeElement!, { key: 'End' });
    });
    expect(screen.getByTestId('cam').textContent).toBe('follow');
    expect(window.localStorage.getItem(CAMERA_STORAGE_KEY)).toBe('follow');
    fireEvent.click(screen.getByRole('radio', { name: /Wide camera/ }));
    expect(window.localStorage.getItem(CAMERA_STORAGE_KEY)).toBe('wide');
  });
});

describe('Pitch2D camera', () => {
  const fx = makeFixture();
  const ev = {
    event_id: 'e1',
    type: 'pass',
    player_id: null,
    receiver_id: null,
    start: { x: 80, y: 20 },
    end: { x: 90, y: 30 },
    outcome: 'complete',
    match_clock: '10:00',
    clock_s: 600,
    metrics: {},
  } as unknown as MatchEvent;

  const viewBox = () => document.querySelector('svg[role="figure"]')!.getAttribute('viewBox');

  it('wide shows the whole pitch, flat', () => {
    render(
      <I18nProvider lang="en">
        <Pitch2D teams={fx.teams} event={ev} camera="wide" />
      </I18nProvider>,
    );
    expect(viewBox()).toBe('0 0 105 68');
    expect(screen.getByTestId('pitch-wrapper').style.transform).toBe('none');
  });

  it('tactical tilts the pitch with a CSS 3D transform', () => {
    render(
      <I18nProvider lang="en">
        <Pitch2D teams={fx.teams} event={ev} camera="tactical" />
      </I18nProvider>,
    );
    expect(screen.getByTestId('pitch-wrapper').style.transform).toBe(TACTICAL_TRANSFORM);
    expect(viewBox()).toBe('0 0 105 68');
  });

  it('follow zooms on the ball (instantly under reduced motion), kept inside the pitch', () => {
    vi.spyOn(window, 'matchMedia').mockImplementation(
      (q: string) => ({ matches: q.includes('reduce'), media: q, addEventListener() {}, removeEventListener() {} }) as unknown as MediaQueryList,
    );
    render(
      <I18nProvider lang="en">
        <Pitch2D teams={fx.teams} event={ev} camera="follow" />
      </I18nProvider>,
    );
    const [x, y, w, h] = viewBox()!.split(' ').map(Number);
    expect(w).toBe(50);
    expect(x + w).toBeLessThanOrEqual(105);
    expect(y + h).toBeLessThanOrEqual(68.01);
    // Ball (pass end 90,30) is in view.
    expect(90).toBeGreaterThanOrEqual(x);
    expect(30).toBeGreaterThanOrEqual(y);
    expect(30).toBeLessThanOrEqual(y + h);
  });
});
