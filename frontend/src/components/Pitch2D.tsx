import type React from 'react';
import type { MatchEvent, OverlayCard, Replay, Teams, XY } from '../api/contract';
import type { PlayerPosition } from '../state/matchStore';

export interface Pitch2DProps {
  teams: Teams | null;
  /** Event to draw now (pass line, shot, carry...). */
  event: MatchEvent | null;
  /** Recent events drawn faintly behind the current one. */
  recentEvents?: MatchEvent[];
  /** Draws the better-option or unfound-run geometry instead of the live event. */
  replay?: Replay | null;
  /** Highlights one player: marker, trail and a label. */
  focusPlayerId?: string | null;
  positions?: Record<string, PlayerPosition>;
  trails?: Record<string, XY[]>;
  /** Speed and distance tags on the current event (from event.metrics). */
  showTags?: boolean;
  /** Active pitch_tag cards from the crew. */
  pitchTags?: OverlayCard[];
  /** Zooms the view box around the focus player. */
  zoomOnFocus?: boolean;
  className?: string;
}

// Placeholder until the ported screen lands.
export const Pitch2D: React.FC<Pitch2DProps> = () => null;
