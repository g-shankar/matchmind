import type React from 'react';
import type { OverlayCard } from '../api/contract';
import type { ViewProps } from '../views/types';

export interface NarrativeFeedProps extends ViewProps {
  onOpenReplay: (card: OverlayCard) => void;
}

// Placeholder until the ported screen lands.
export const NarrativeFeed: React.FC<NarrativeFeedProps> = () => null;
