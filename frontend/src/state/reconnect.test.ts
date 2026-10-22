// Launch checks LC-2: a viewer who was watching the live server must get back to it after
// the server restarts, without a refresh (CLAUDE.md section 3.3).
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/mockServer', () => ({
  // The offline demo lives on the same server as the app, so while it is down it cannot load.
  loadDemoFixture: vi.fn(() => Promise.reject(new Error('server down'))),
  MockMatchServer: vi.fn(),
}));

class FakeSocket {
  static all: FakeSocket[] = [];
  static readonly OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    FakeSocket.all.push(this);
  }
  send() {}
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
}

describe('reconnecting after the live server restarts (LC-2)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeSocket.all = [];
    vi.stubGlobal('WebSocket', FakeSocket);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('keeps trying the live server instead of switching to the demo, and comes back without a refresh', async () => {
    const { useMatch } = await import('./useMatch');
    const { result } = renderHook(() => useMatch());
    act(() => FakeSocket.all[0].open());
    expect(result.current.state.status).toBe('live');

    // The server goes away for about 30 s: every attempt in that time fails to open.
    act(() => FakeSocket.all[0].close());
    for (let s = 0; s < 30; s += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      const last = FakeSocket.all[FakeSocket.all.length - 1];
      if (last.readyState === 0) act(() => last.close());
      expect(result.current.state.status).not.toBe('demo');
    }
    const attempts = FakeSocket.all.length;
    expect(attempts).toBeGreaterThan(3);

    // Back up: the next attempt opens and the viewer is live again.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15000);
    });
    expect(FakeSocket.all.length).toBeGreaterThan(attempts);
    act(() => FakeSocket.all[FakeSocket.all.length - 1].open());
    expect(result.current.state.status).toBe('live');
  });

  it('still falls back to the offline demo when no live server ever answered', async () => {
    const { loadDemoFixture } = await import('../api/mockServer');
    const { useMatch } = await import('./useMatch');
    renderHook(() => useMatch());
    act(() => FakeSocket.all[0].close());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(loadDemoFixture).toHaveBeenCalled();
  });
});
