// Catch-up mode for the offline demo: the same scrub the live server applies
// (backend/src/matchmind/crew/spoilers.py) to a viewer with `spoilers: false`.
// The live server never sends these fields to such a viewer; the demo replays
// a recording that has them, so it removes them before they reach the screen.
import type { Bookmark, MatchEvent, MatchState, MomentKind, OverlayCard, PlayerStats, SnapshotData, TickData } from './contract';

export const SPOILER_KINDS: readonly MomentKind[] = ['goal', 'correction'];
const SPOILER_DETAIL_KEYS = ['score_home', 'score_away', 'assist_id', 'blocked_by'];
const OUTCOME_HIDDEN_EVENTS = ['shot', 'var_review'];
// Where a shot ended is its outcome: every goal ends inside the goal mouth.
const END_HIDDEN_EVENTS = ['shot'];
// A VAR review always looks at a goal here, and every kick-off after the first whistle
// restarts play after one: a catch-up viewer never gets these events at all.
const WITHHELD_EVENTS = ['var_review'];
const WITHHELD_PASS_TYPES = ['kickoff'];

export const isWithheldEvent = (e: Pick<MatchEvent, 'type'> & { details?: MatchEvent['details'] }): boolean =>
  WITHHELD_EVENTS.includes(e.type) || (e.type === 'pass' && WITHHELD_PASS_TYPES.includes(String(e.details?.pass_type ?? '')));
const SPOILER_LABEL_KEYS = ['score_home', 'score_away', 'score_w', 'score_l', 'winner', 'loser', 'goals_line', 'ruled_out_clock', 'decision'];

export function isSpoilerCard(card: Pick<OverlayCard, 'kind' | 'retracts' | 'evidence'>): boolean {
  if (SPOILER_KINDS.includes(card.kind) || (card.retracts?.length ?? 0) > 0) return true;
  return card.evidence.some((e) => !!e.label_key && SPOILER_LABEL_KEYS.includes(e.label_key));
}

/** Events for a catch-up viewer: withheld ones dropped, the rest scrubbed. */
export const spoilerFreeEvents = (events: MatchEvent[]): MatchEvent[] => events.filter((e) => !isWithheldEvent(e)).map(scrubEvent);

export function scrubEvent(e: MatchEvent): MatchEvent {
  const details = { ...e.details };
  for (const k of SPOILER_DETAIL_KEYS) delete details[k];
  // No full-feed numbering: a withheld event would leave a gap in it.
  const out: MatchEvent = { ...e, details, seq: null };
  if (OUTCOME_HIDDEN_EVENTS.includes(e.type)) out.outcome = null;
  if (END_HIDDEN_EVENTS.includes(e.type)) out.end = null;
  if ('reviewed_event_id' in out) delete out.reviewed_event_id;
  if ('review_reason' in out) out.review_reason = null;
  return out;
}

export const scrubState = (s: MatchState): MatchState => ({ ...s, score_home: null, score_away: null });
export const scrubPlayer = (p: PlayerStats): PlayerStats => ({ ...p, goals: null, assists: null });
export const spoilerFreeCards = (cards: OverlayCard[]) => cards.filter((c) => !isSpoilerCard(c));

export function spoilerFreeBookmarks(bookmarks: Bookmark[]): Bookmark[] {
  return bookmarks.filter((b) => !SPOILER_KINDS.includes(b.kind)).map((b) => ({ ...b, ruled_out: false }));
}

export function spoilerFreeSnapshot(d: SnapshotData): SnapshotData {
  return {
    ...d,
    home_score: null,
    away_score: null,
    state: scrubState(d.state),
    recent_cards: spoilerFreeCards(d.recent_cards),
    bookmarks: spoilerFreeBookmarks(d.bookmarks),
    players: d.players.map(scrubPlayer),
    // The last events seed the pitch and feed; their score-bearing text goes too.
    ...(d.recent_events ? { recent_events: spoilerFreeEvents(d.recent_events) } : {}),
    // The cue sheet carries the scorebug, so a catch-up viewer gets none.
    cue_sheet: null,
  };
}

/** The tick for a catch-up viewer, or null when its event is withheld (a VAR review). */
export function spoilerFreeTick(d: TickData): TickData | null {
  if (isWithheldEvent(d.event)) return null;
  return {
    ...d,
    event: scrubEvent(d.event),
    score: null,
    state: scrubState(d.state),
    cards: spoilerFreeCards(d.cards),
    players_changed: d.players_changed.map(scrubPlayer),
  };
}

// Every key that holds a full-feed event id (or a list of them) in a payload.
const EVENT_ID_KEYS = ['event_id', 'source_event_id', 'shot_event_id', 'run_event_id'];
const EVENT_ID_LIST_KEYS = ['source_event_ids'];

/**
 * Catch-up event ids for the offline demo, as the live server gives them: random for this
 * session and unordered, so a withheld event leaves no gap. The same full-feed id always gets
 * the same catch-up id, so cards still point at the events on the pitch.
 */
export function catchUpIds(): (raw: string) => string {
  const ids = new Map<string, string>();
  const random = () => {
    const bytes = new Uint8Array(8);
    if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(bytes);
    else for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  };
  const used = new Set<string>();
  return (raw) => {
    const known = ids.get(raw);
    if (known) return known;
    let id = `ev-${random()}`;
    while (used.has(id)) id = `ev-${random()}`;
    ids.set(raw, id);
    used.add(id);
    return id;
  };
}

/** A copy of a catch-up payload with every event id replaced by its catch-up id. */
export function withCatchUpIds<T>(value: T, idFor: (raw: string) => string): T {
  if (Array.isArray(value)) return value.map((v) => withCatchUpIds(v, idFor)) as T;
  if (!value || typeof value !== 'object') return value;
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    if (EVENT_ID_KEYS.includes(k) && typeof v === 'string' && v) out[k] = idFor(v);
    else if (EVENT_ID_LIST_KEYS.includes(k) && Array.isArray(v)) out[k] = v.map((x) => (typeof x === 'string' ? idFor(x) : x));
    else out[k] = withCatchUpIds(v, idFor);
  }
  return out as T;
}
