import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { InsightMode, InsightResult } from '../api/insights';

const ModeContext = createContext<InsightMode>('live');

/** Tells the trust panels whether to read the match server or the offline recording. */
export const InsightModeProvider: React.FC<{ mode: InsightMode; children: React.ReactNode }> = ({ mode, children }) => (
  <ModeContext.Provider value={mode}>{children}</ModeContext.Provider>
);

export const useInsightMode = () => useContext(ModeContext);

export type InsightState<T> = InsightResult<T> | { status: 'loading' };

/**
 * Loads one insight in the background. `key` changes start a fresh load; with
 * `pollMs` the data refreshes in place (the last good answer stays on screen
 * while a refresh runs, and polling pauses while the tab is hidden).
 */
export function useInsight<T>(
  load: () => Promise<InsightResult<T>>,
  key: string,
  options: { pollMs?: number; enabled?: boolean } = {},
): { state: InsightState<T>; reload: () => void; refreshing: boolean } {
  const { pollMs, enabled = true } = options;
  const [state, setState] = useState<InsightState<T>>({ status: 'loading' });
  const [refreshing, setRefreshing] = useState(false);
  const [nonce, setNonce] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;
  const last = useRef<InsightState<T>>(state);
  last.current = state;

  useEffect(() => {
    if (!enabled) return;
    let live = true;
    setState({ status: 'loading' });
    const run = (background: boolean) => {
      if (background) setRefreshing(true);
      loadRef
        .current()
        .then((result) => {
          if (!live) return;
          // A failed background refresh keeps the last good answer.
          if (background && result.status !== 'ready' && last.current.status === 'ready') return;
          setState(result);
        })
        .catch(() => live && !background && setState({ status: 'error' }))
        .finally(() => live && setRefreshing(false));
    };
    run(false);
    let timer: ReturnType<typeof setInterval> | null = null;
    if (pollMs) {
      timer = setInterval(() => {
        if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
        if (last.current.status === 'needs_server') return;
        run(true);
      }, pollMs);
    }
    return () => {
      live = false;
      if (timer) clearInterval(timer);
    };
  }, [key, nonce, pollMs, enabled]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { state, reload, refreshing };
}
