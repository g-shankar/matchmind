import type { MatchViewState } from '../state/matchStore';
import type { MatchActions } from '../state/useMatch';

// Every screen gets the whole match view state and the action set.
export interface ViewProps {
  match: MatchViewState;
  actions: MatchActions;
}
