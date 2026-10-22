// WCAG 2.x contrast helpers. Team colours come from the match feed, so text drawn on a
// team colour picks whichever of the two inks (chalk white or matchday ink) reads better.

export const INK_LIGHT = '#ffffff';
export const INK_DARK = '#0c0c0b'; // pp.night

type Rgb = [number, number, number];

export function parseColor(input: string): Rgb | null {
  const s = input.trim().toLowerCase();
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/.exec(s);
  if (hex) {
    const h = hex[1].length === 3 ? hex[1].split('').map((c) => c + c).join('') : hex[1];
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as Rgb;
  }
  return null;
}

function channel(v: number): number {
  const c = v / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

export function luminance(rgb: Rgb): number {
  return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2]);
}

/** Contrast ratio between two colours (1 to 21). Unparseable input counts as 1. */
export function contrastRatio(a: string | Rgb, b: string | Rgb): number {
  const ca = typeof a === 'string' ? parseColor(a) : a;
  const cb = typeof b === 'string' ? parseColor(b) : b;
  if (!ca || !cb) return 1;
  const [hi, lo] = [luminance(ca), luminance(cb)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** `top` drawn at `alpha` over the opaque `under` colour. */
export function blend(top: string, alpha: number, under: string): Rgb {
  const t = parseColor(top) ?? [0, 0, 0];
  const u = parseColor(under) ?? [0, 0, 0];
  return [0, 1, 2].map((i) => Math.round(t[i] * alpha + u[i] * (1 - alpha))) as Rgb;
}

/** The ink (light or dark) with the higher contrast on `background`. */
export function inkOn(background: string | Rgb): string {
  return contrastRatio(INK_LIGHT, background) >= contrastRatio(INK_DARK, background) ? INK_LIGHT : INK_DARK;
}
