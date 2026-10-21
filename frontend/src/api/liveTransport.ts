import type { ClientAction, Language, OverlayCard, PersonaType, Recap, ServerMessage } from './contract';
import { apiBase, wsUrl, type MatchTransport, type MessageHandler } from './transport';

export interface LiveCallbacks {
  onMessage: MessageHandler;
  onOpen: () => void;
  onClose: (everOpened: boolean) => void;
}

// Thin wrapper around the match WebSocket and REST routes. Reconnection is the caller's job.
export class LiveTransport implements MatchTransport {
  readonly kind = 'live' as const;
  private ws: WebSocket;
  private opened = false;
  private closedByUs = false;
  private readonly base: string;

  constructor(callbacks: LiveCallbacks, base = apiBase()) {
    this.base = base;
    this.ws = new WebSocket(wsUrl(base));
    this.ws.onopen = () => {
      this.opened = true;
      callbacks.onOpen();
    };
    this.ws.onmessage = (event) => {
      try {
        callbacks.onMessage(JSON.parse(event.data as string) as ServerMessage);
      } catch {
        // A malformed frame is dropped; the next tick or snapshot carries full state.
      }
    };
    this.ws.onclose = () => {
      if (!this.closedByUs) callbacks.onClose(this.opened);
    };
    this.ws.onerror = () => this.ws.close();
  }

  send(action: ClientAction) {
    if (this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(action));
  }

  async getMoment(
    momentId: string,
    persona: PersonaType,
    language: Language,
    favouriteTeam: string | null,
  ): Promise<OverlayCard | null> {
    const q = new URLSearchParams({ persona, lang: language });
    if (favouriteTeam) q.set('favourite_team', favouriteTeam);
    return this.getJson<OverlayCard>(`/api/match/moment/${encodeURIComponent(momentId)}?${q}`);
  }

  async getRecap(persona: PersonaType, language: Language): Promise<Recap | null> {
    const q = new URLSearchParams({ persona, lang: language });
    return this.getJson<Recap>(`/api/match/recap?${q}`);
  }

  close() {
    this.closedByUs = true;
    this.ws.close();
  }

  private async getJson<T>(path: string): Promise<T | null> {
    try {
      const res = await fetch(`${this.base}${path}`);
      return res.ok ? ((await res.json()) as T) : null;
    } catch {
      return null;
    }
  }
}
