// Per-match preview files for the "Choose a match" picker, built from the recorded
// synthetic matches by scripts/build_match_previews.py. Every number in them comes from
// the match events or the stats engine; the picker only lays them out.

export type StoryTag = 'comeback' | 'late_winner' | 'var_drama' | 'goal_fest' | 'tight_win' | 'goalless';
export const STORY_TAGS: StoryTag[] = ['comeback', 'late_winner', 'var_drama', 'goal_fest', 'tight_win', 'goalless'];

export interface PreviewClub {
  team_id: string;
  name: string;
  short_name: string;
  primary_color: string;
  secondary_color: string;
}

export interface PreviewStep {
  kind: 'pass' | 'carry' | 'dribble' | 'shot';
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface PreviewGoal {
  team: string;
  minute: number;
  period: number;
  home: number;
  away: number;
}

export interface MatchPreview {
  match_id: string;
  /** The match the default server session and the offline demo play. */
  playable: boolean;
  home: PreviewClub;
  away: PreviewClub;
  score: { home: number; away: number };
  goals: PreviewGoal[];
  var_reviews: number;
  var_overturned: number;
  events: number;
  tags: StoryTag[];
  key_moment: {
    event_id: string;
    team: string;
    minute: number;
    period: number;
    chance_quality: number | null;
    path: PreviewStep[];
    players: { x: number; y: number; mate: boolean; actor: boolean }[];
  } | null;
}

export const PITCH_W = 105;
export const PITCH_H = 68;

export const previewsBase = () => `${import.meta.env.BASE_URL}previews/`;

/** Football minute label: stoppage time reads 45+2 or 90+3, never 47 or 93. */
export function minuteLabel(minute: number, period: number): string {
  if (period === 1 && minute > 45) return `45+${minute - 45}'`;
  if (period === 2 && minute > 90) return `90+${minute - 90}'`;
  return `${minute}'`;
}

const COLOUR = /^#[0-9a-f]{6}$/i;
const MAX_PREVIEWS = 20;
const isClub = (c: PreviewClub | undefined) =>
  !!c && typeof c.name === 'string' && typeof c.short_name === 'string' && COLOUR.test(String(c.primary_color)) && COLOUR.test(String(c.secondary_color));

const isPreview = (d: unknown): d is MatchPreview => {
  const p = d as MatchPreview;
  return (
    !!p &&
    typeof p.match_id === 'string' &&
    /^MM-[A-Z]+-\d{3}$/.test(p.match_id) &&
    isClub(p.home) &&
    isClub(p.away) &&
    Number.isInteger(p.score?.home) &&
    Number.isInteger(p.score?.away) &&
    Array.isArray(p.tags) &&
    Array.isArray(p.goals)
  );
};

/** Loads the index and every listed preview; malformed files are dropped, not shown. */
export async function loadPreviews(base = previewsBase(), fetcher: typeof fetch = fetch): Promise<MatchPreview[]> {
  const r = await fetcher(`${base}index.json`);
  if (!r.ok) throw new Error('index');
  const idx = (await r.json()) as { matches?: unknown };
  const ids = Array.isArray(idx.matches) ? idx.matches.filter((m): m is string => typeof m === 'string' && /^MM-[A-Z]+-\d{3}$/.test(m)).slice(0, MAX_PREVIEWS) : [];
  const out = await Promise.all(
    ids.map(async (id) => {
      try {
        const res = await fetcher(`${base}${id}.json`);
        if (!res.ok) return null;
        const d: unknown = await res.json();
        if (!isPreview(d)) return null;
        return { ...d, tags: d.tags.filter((t) => STORY_TAGS.includes(t)) };
      } catch {
        return null;
      }
    }),
  );
  return out.filter((p): p is MatchPreview => p !== null);
}

/** Which card can really be played: the match this session plays, else the default one. */
export function isPlayable(p: MatchPreview, sessionMatchId: string | null): boolean {
  return sessionMatchId ? p.match_id === sessionMatchId : p.playable;
}

/**
 * The ball's waypoints and timing for the key-moment animation: each step's share of the
 * loop, so the ball, the arrows and the dots stay in step. Returns keyframe stops in %.
 */
export function ballTimeline(path: PreviewStep[], drawShare = 0.78): { at: number; x: number; y: number }[] {
  if (!path.length) return [];
  const weight = (s: PreviewStep) => (s.kind === 'shot' ? 0.7 : 1);
  const total = path.reduce((a, s) => a + weight(s), 0);
  const stops = [{ at: 0, x: path[0].x1, y: path[0].y1 }];
  let t = 0;
  for (const s of path) {
    t += weight(s);
    stops.push({ at: +((t / total) * drawShare * 100).toFixed(2), x: s.x2, y: s.y2 });
  }
  return stops;
}

/** Whole-match picker should open first: not for deep links into the studio or captures. */
export function pickerOnLoad(search: string, hash: string): boolean {
  const q = new URLSearchParams(search);
  for (const k of ['demo', 'live', 'capture', 'moment', 't']) if (q.has(k)) return false;
  return !hash.replace('#', '');
}
