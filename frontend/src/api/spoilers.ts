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
// A VAR review always looks at a goal here, so a catch-up viewer never gets the event at all.
const WITHHELD_EVENTS = ['var_review'];

export const isWithheldEvent = (e: Pick<MatchEvent, 'type'>): boolean => WITHHELD_EVENTS.includes(e.type);
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
  const out: MatchEvent = { ...e, details };
  if (details.pass_type === 'kickoff') {
    // Restarts are kick-offs from the centre spot, and a restart follows a goal.
    delete details.pass_type;
    out.start = null;
  }
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
