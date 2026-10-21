import type React from 'react';
import type { OverlayCard, Teams } from '../api/contract';

export interface ReplayCardProps {
  card: OverlayCard; // kind better_option or unfound_run, replay set
  teams: Teams | null;
  compact?: boolean;
  onClose?: () => void;
}

// Placeholder until the ported screen lands.
export const ReplayCard: React.FC<ReplayCardProps> = () => null;
