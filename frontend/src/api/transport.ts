import type {
  ClientAction,
  Language,
  OverlayCard,
  PersonaType,
  Recap,
  ServerMessage,
} from './contract';

export type TransportKind = 'live' | 'demo';
export type MessageHandler = (message: ServerMessage) => void;

// One viewer's connection to a match session: the live WebSocket server or the
// in-browser demo replay. Both speak the same contract.
export interface MatchTransport {
  readonly kind: TransportKind;
  send(action: ClientAction): void;
  getMoment(
    momentId: string,
    persona: PersonaType,
    language: Language,
    favouriteTeam: string | null,
  ): Promise<OverlayCard | null>;
  getRecap(persona: PersonaType, language: Language): Promise<Recap | null>;
  close(): void;
}

// VITE_API_URL wins; otherwise the page's own origin (the backend serves the built app).
export function apiBase(): string {
  const fromEnv = (import.meta.env.VITE_API_URL as string | undefined)?.trim();
  return (fromEnv || window.location.origin).replace(/\/+$/, '');
}

export function wsUrl(base = apiBase()): string {
  return `${base.replace(/^http/, 'ws')}/ws/match`;
}
