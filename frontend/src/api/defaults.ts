import type { ViewerProfile } from './contract';

// A new viewer's choices before they pick anything.
export const DEFAULT_PROFILE: ViewerProfile = {
  persona: 'casual',
  language: 'en',
  favourite_team: null,
  focus_player_id: null,
  focus_metric: null,
  spoilers: true,
};
