// Human labels for values the server sends as internal keys: tactical tags, recap match
// numbers and the kind of an upcoming moment (without giving it away).
import type { Bookmark, FactValue, MomentKind, Teams } from '../api/contract';

type T = (key: string, vars?: Record<string, string | number>) => string;

const has = (t: T, key: string) => t(key) !== key;

/** "decision_making" -> "Decision making" (translated when known). Never shows underscores. */
export function tagLabel(t: T, tag: string): string {
  const key = `tag.${tag}`;
  if (has(t, key)) return t(key);
  const plain = tag.replace(/_/g, ' ').trim();
  return plain.charAt(0).toUpperCase() + plain.slice(1);
}

// Facts the recap uses to write its sentences but that are not numbers a reader needs
// (names repeated elsewhere, the clock it was written at, winner and loser).
const RECAP_HIDDEN = new Set(['home', 'away', 'generated_at', 'winner', 'loser', 'score_w', 'score_l', 'potm', 'potm_short']);

/** The recap's "Match numbers": only facts with a human label, in the server's order. */
export function recapStatRows(t: T, stats: Record<string, FactValue>, teams: Teams | null): { key: string; label: string; value: FactValue }[] {
  const names = {
    home: teams?.home.name ?? String(stats.home ?? stats.home_team ?? t('common.home')),
    away: teams?.away.name ?? String(stats.away ?? stats.away_team ?? t('common.away')),
  };
  const rows: { key: string; label: string; value: FactValue }[] = [];
  for (const [key, value] of Object.entries(stats)) {
    if (RECAP_HIDDEN.has(key)) continue;
    const own = `recap.stat.${key}`;
    const shared = `broadcast.fact.${key}`;
    const label = has(t, own) ? t(own, names) : has(t, shared) ? t(shared) : null;
    if (label) rows.push({ key, label, value });
  }
  return rows;
}

const UPCOMING: Partial<Record<MomentKind, string>> = {
  goal: 'attack',
  big_chance: 'attack',
  rocket_shot: 'attack',
  card: 'referee',
  correction: 'referee',
  momentum_swing: 'flow',
  pressure_spell: 'flow',
  key_tackle: 'defence',
  milestone: 'milestone',
};

/** A label for a moment still to come that says what sort of moment, not what happens. */
export const upcomingLabelKey = (kind: MomentKind) => `visit.upcoming.${UPCOMING[kind] ?? 'other'}`;

const KIND_RANK: MomentKind[] = ['better_option', 'unfound_run', 'goal', 'correction', 'card', 'big_chance', 'key_tackle', 'momentum_swing', 'pressure_spell', 'milestone'];
const rank = (k: MomentKind) => {
  const i = KIND_RANK.indexOf(k);
  return i < 0 ? KIND_RANK.length : i;
};

/** One chip per clock: moments at the same time (a goal, its VAR check and the decision)
 * land on the same spot, so they share a chip led by the most important one. */
export function groupByClock<B extends Pick<Bookmark, 'match_clock' | 'kind' | 'period'>>(bookmarks: B[]): { lead: B; count: number }[] {
  const out: { lead: B; count: number }[] = [];
  const byClock = new Map<string, { lead: B; count: number }>();
  for (const b of bookmarks) {
    const key = `${b.period}|${b.match_clock}`;
    const group = byClock.get(key);
    if (!group) {
      const g = { lead: b, count: 1 };
      byClock.set(key, g);
      out.push(g);
      continue;
    }
    group.count += 1;
    if (rank(b.kind) < rank(group.lead.kind)) group.lead = b;
  }
  return out;
}
