import type React from 'react';
import type { Recap, Teams } from '../api/contract';

export interface RecapModalProps {
  open: boolean;
  onClose: () => void;
  recap: Recap | null;
  loading: boolean;
  teams: Teams | null;
}

// Placeholder until the ported screen lands.
export const RecapModal: React.FC<RecapModalProps> = () => null;
