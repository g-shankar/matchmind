// How a fact from the stats engine is labelled and shown (shared by the overlay, recap and Ask).
import type { FactValue } from '../api/contract';
import type { I18n } from '../i18n';

// Label for a fact key: our translation when we have one, otherwise the key as sent.
export function factLabel(t: I18n['t'], key: string): string {
  const k = `broadcast.fact.${key}`;
  const text = t(k);
  return text === k ? key.replace(/_/g, ' ') : text;
}

// Shows a payload value as sent: numbers keep their own decimals (at most 3), booleans become yes/no.
export function factValue(i18n: Pick<I18n, 't' | 'num'>, value: FactValue): string {
  if (typeof value === 'number') {
    const decimals = Number.isInteger(value) ? 0 : Math.min(3, String(value).split('.')[1]?.length ?? 0);
    return i18n.num(value, decimals);
  }
  if (typeof value === 'boolean') return i18n.t(value ? 'broadcast.recap.yes' : 'broadcast.recap.no');
  return value;
}

