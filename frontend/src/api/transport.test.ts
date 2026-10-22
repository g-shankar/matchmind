import { describe, expect, it } from 'vitest';
import { wsUrl } from './transport';

describe('wsUrl', () => {
  it('carries the viewer choices so a catch-up viewer’s first snapshot never has the score', () => {
    expect(wsUrl('https://pp.example', { spoilers: false, persona: 'tactical', language: 'es' })).toBe(
      'wss://pp.example/ws/match?spoilers=0&persona=tactical&lang=es',
    );
    expect(wsUrl('http://localhost:8000', { spoilers: true, persona: 'casual', language: 'en' })).toBe(
      'ws://localhost:8000/ws/match?spoilers=1&persona=casual&lang=en',
    );
    expect(wsUrl('http://localhost:8000')).toBe('ws://localhost:8000/ws/match');
  });
});
