import type React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import { ballTimeline, isPlayable, loadPreviews, minuteLabel, pickerOnLoad, type MatchPreview } from '../lib/previews';
import { MatchPicker } from './MatchPicker';

const files = import.meta.glob('../../public/previews/*.json', { eager: true, import: 'default' });
const read = (f: string) => files[`../../public/previews/${f}`] as never;
const index = read('index.json') as { matches: string[] };
const previews: MatchPreview[] = index.matches.map((id) => read(`${id}.json`));
const byId = (id: string) => previews.find((p) => p.match_id === id)!;
const manifest = Object.values(import.meta.glob('../../../backend/data/matches/manifest.json', { eager: true, import: 'default' }))[0] as {
  match_id: string;
  score: string;
  home: string;
  away: string;
}[];

const media = (matches: (q: string) => boolean) =>
  vi.stubGlobal('matchMedia', (q: string) => ({ matches: matches(q), media: q, addEventListener() {}, removeEventListener() {} }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  try {
    window.localStorage.clear();
  } catch {
    /* ignore */
  }
});

const ui = (node: React.ReactNode, lang = 'en') => render(<I18nProvider lang={lang}>{node}</I18nProvider>);
const picker = (props: Partial<React.ComponentProps<typeof MatchPicker>> = {}, lang = 'en') =>
  ui(<MatchPicker open sessionMatchId={null} onClose={vi.fn()} onWatch={vi.fn()} previews={previews} {...props} />, lang);

describe('match preview files', () => {
  it('cover every recorded match with the manifest score and invented clubs only', () => {
    expect(index.matches.sort()).toEqual(manifest.map((m) => m.match_id).sort());
    for (const m of manifest) {
      const p = byId(m.match_id);
      expect(`${p.score.home}-${p.score.away}`).toBe(m.score);
      expect([p.home.team_id, p.away.team_id]).toEqual([m.home, m.away]);
      expect(p.goals.length).toBe(p.score.home + p.score.away);
      for (const c of [p.home, p.away]) expect(['Northbridge FC', 'Harbour City']).toContain(c.name);
    }
  });

  it('derive storylines honestly from the goals', () => {
    const demo = byId('MM-DEMO-001');
    // 2-0 up, then three away goals, the last in stoppage time; one goal ruled out by VAR.
    expect(demo.tags).toEqual(expect.arrayContaining(['comeback', 'late_winner', 'var_drama']));
    expect(demo.var_overturned).toBe(1);
    expect(byId('MM-SYN-003').tags).toEqual(['tight_win']);
    for (const p of previews) {
      const winnerHome = p.score.home > p.score.away;
      const trailed = p.goals.some((g) => (winnerHome ? g.away > g.home : g.home > g.away));
      expect(p.tags.includes('comeback')).toBe(trailed && p.score.home !== p.score.away);
    }
  });

  it('key moment ends in the shot of the decisive goal, on the pitch', () => {
    for (const p of previews) {
      const km = p.key_moment!;
      expect(km.path[km.path.length - 1].kind).toBe('shot');
      for (const s of km.path) {
        for (const x of [s.x1, s.x2]) expect(x).toBeGreaterThanOrEqual(0), expect(x).toBeLessThanOrEqual(105);
        for (const y of [s.y1, s.y2]) expect(y).toBeGreaterThanOrEqual(0), expect(y).toBeLessThanOrEqual(68);
      }
      expect(km.chance_quality).toBeGreaterThan(0);
      expect(km.chance_quality).toBeLessThan(1);
    }
  });

  it('only the demo match is marked playable by default', () => {
    expect(previews.filter((p) => p.playable).map((p) => p.match_id)).toEqual(['MM-DEMO-001']);
    expect(isPlayable(byId('MM-SYN-001'), 'MM-SYN-001')).toBe(true);
    expect(isPlayable(byId('MM-DEMO-001'), 'MM-SYN-001')).toBe(false);
  });
});

describe('preview helpers', () => {
  it('labels stoppage time', () => {
    expect(minuteLabel(93, 2)).toBe("90+3'");
    expect(minuteLabel(47, 1)).toBe("45+2'");
    expect(minuteLabel(47, 2)).toBe("47'");
  });

  it('times the ball path in order, ending before the hold', () => {
    const stops = ballTimeline(byId('MM-DEMO-001').key_moment!.path);
    expect(stops[0].at).toBe(0);
    for (let i = 1; i < stops.length; i++) expect(stops[i].at).toBeGreaterThan(stops[i - 1].at);
    expect(stops[stops.length - 1].at).toBeCloseTo(78, 0);
  });

  it('opens on first load but not for deep links', () => {
    expect(pickerOnLoad('', '')).toBe(true);
    expect(pickerOnLoad('?demo=1', '')).toBe(false);
    expect(pickerOnLoad('?live=1', '')).toBe(false);
    expect(pickerOnLoad('?capture=1', '#overlay')).toBe(false);
    expect(pickerOnLoad('', '#studio')).toBe(false);
  });

  it('drops malformed preview files', async () => {
    const files: Record<string, unknown> = {
      'index.json': { matches: ['MM-DEMO-001', 'MM-SYN-001', '../etc'] },
      'MM-DEMO-001.json': byId('MM-DEMO-001'),
      'MM-SYN-001.json': { match_id: 'MM-SYN-001', score: 'x' },
    };
    const fetcher = vi.fn(async (url: string) => {
      const name = url.split('/').pop()!;
      return { ok: name in files, json: async () => files[name] } as Response;
    }) as unknown as typeof fetch;
    const out = await loadPreviews('/p/', fetcher);
    expect(out.map((p) => p.match_id)).toEqual(['MM-DEMO-001']);
    expect(fetcher).toHaveBeenCalledTimes(3);
  });
});

describe('MatchPicker', () => {
  it('shows one card per match; only the playable one can be watched, the rest say preview only', () => {
    media(() => false);
    picker();
    expect(screen.getByRole('dialog', { name: 'Choose a match' })).toBeTruthy();
    expect(screen.getAllByRole('listitem')).toHaveLength(previews.length);
    const demo = screen.getByTestId('pick-MM-DEMO-001');
    expect(within(demo).getByText('On air')).toBeTruthy();
    expect(within(demo).getByRole('button', { name: /Watch this match/ })).toBeTruthy();
    expect(within(demo).getByText('Comeback')).toBeTruthy();
    expect(within(demo).getByText("Key moment 90+3'")).toBeTruthy();
    const other = screen.getByTestId('pick-MM-SYN-002');
    expect(within(other).getByText('Preview only')).toBeTruthy();
    expect(within(other).getByText('Full replay coming soon')).toBeTruthy();
    expect(within(other).queryByRole('button')).toBeNull();
    expect(screen.getAllByRole('button', { name: /Watch this match/ })).toHaveLength(1);
  });

  it('follows the match the session really plays', () => {
    media(() => false);
    picker({ sessionMatchId: 'MM-SYN-004' });
    expect(within(screen.getByTestId('pick-MM-SYN-004')).getByText('On air')).toBeTruthy();
    expect(within(screen.getByTestId('pick-MM-DEMO-001')).getByText('Preview only')).toBeTruthy();
  });

  it('animates the key moment on hover and focus, not before', () => {
    media(() => false);
    picker();
    const card = screen.getByTestId('pick-MM-SYN-001');
    const pitch = within(card).getByTestId('mini-pitch');
    expect(pitch.getAttribute('data-animating')).toBe('false');
    fireEvent.mouseEnter(card);
    expect(pitch.getAttribute('data-animating')).toBe('true');
    expect(pitch.querySelector('style')!.textContent).toContain('@keyframes pp-ball-MMSYN001');
    fireEvent.mouseLeave(card);
    expect(pitch.getAttribute('data-animating')).toBe('false');
    // Keyboard: preview-only cards take focus on the pitch itself.
    fireEvent.focus(pitch);
    expect(pitch.getAttribute('data-animating')).toBe('true');
    expect(pitch.getAttribute('tabindex')).toBe('0');
  });

  it('auto-plays on touch screens and stays still with reduced motion', () => {
    media((q) => q.includes('hover: none'));
    picker();
    expect(screen.getAllByTestId('mini-pitch').every((p) => p.getAttribute('data-animating') === 'true')).toBe(true);
    cleanup();
    media((q) => q.includes('hover: none') || q.includes('reduce'));
    picker();
    const pitches = screen.getAllByTestId('mini-pitch');
    expect(pitches.every((p) => p.getAttribute('data-animating') === 'false')).toBe(true);
    // Still shows the whole path, drawn in full.
    expect(pitches[0].querySelectorAll('line[stroke="#ff3e32"]').length).toBe(1);
  });

  it('hides results on request and remembers it', () => {
    media(() => false);
    picker();
    fireEvent.click(screen.getByTestId('picker-hide'));
    const demo = screen.getByTestId('pick-MM-DEMO-001');
    expect(within(demo).queryByText('Comeback')).toBeNull();
    expect(within(demo).queryByText(/Key moment/)).toBeNull();
    expect(within(demo).getByRole('img', { name: 'Results hidden' })).toBeTruthy();
    expect(demo.textContent).not.toMatch(/\b3\b/);
    fireEvent.mouseEnter(demo);
    expect(within(demo).getByTestId('mini-pitch').getAttribute('data-animating')).toBe('false');
    cleanup();
    picker();
    expect((screen.getByTestId('picker-hide') as HTMLInputElement).checked).toBe(true);
  });

  it('plays a select transition, then hands over to the studio', () => {
    vi.useFakeTimers();
    media(() => false);
    const onWatch = vi.fn();
    picker({ onWatch });
    fireEvent.click(screen.getByRole('button', { name: /Watch this match/ }));
    expect(screen.getByTestId('match-picker').className).toContain('pp-picker-leave');
    expect(screen.getByTestId('pick-MM-DEMO-001').className).toContain('pp-pick-chosen');
    expect(onWatch).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(onWatch).toHaveBeenCalledWith('MM-DEMO-001');
  });

  it('closes with Escape and the close button', () => {
    media(() => false);
    const onClose = vi.fn();
    picker({ onClose });
    fireEvent.keyDown(window, { key: 'Escape' });
    fireEvent.click(screen.getByTestId('picker-close'));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('speaks Arabic right to left', () => {
    media(() => false);
    picker({}, 'ar');
    const dlg = screen.getByRole('dialog', { name: 'اختر مباراة' });
    expect(dlg.getAttribute('dir')).toBe('rtl');
    expect(within(screen.getByTestId('pick-MM-SYN-002')).getByText('معاينة فقط')).toBeTruthy();
  });
});
