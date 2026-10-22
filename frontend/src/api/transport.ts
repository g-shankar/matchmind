import type {
  AskRequest,
  AskResult,
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
  /** spoilers false: the spoiler-free story so far (catch-up mode). */
  getRecap(persona: PersonaType, language: Language, spoilers?: boolean): Promise<Recap | null>;
  /** Ask the studio: one question or suggested chip, answered as of the match clock. */
  ask(request: AskRequest): Promise<AskResult>;
  close(): void;
}

// VITE_API_URL wins; otherwise the page's own origin (the backend serves the built app).
export function apiBase(): string {
  const fromEnv = (import.meta.env.VITE_API_URL as string | undefined)?.trim();
  return (fromEnv || window.location.origin).replace(/\/+$/, '');
}

/** The viewer's starting choices, on the URL so the very first snapshot already fits them
 * (a catch-up viewer's first frame never carries the score). */
export interface WsView {
  spoilers: boolean;
  persona: PersonaType;
  language: Language;
}

export function wsUrl(base = apiBase(), view?: WsView): string {
  const url = `${base.replace(/^http/, 'ws')}/ws/match`;
  if (!view) return url;
  const q = new URLSearchParams({ spoilers: view.spoilers ? '1' : '0', persona: view.persona, lang: view.language });
  return `${url}?${q}`;
}
