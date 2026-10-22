import { describe, expect, it } from 'vitest';
import tailwindConfig from '../../tailwind.config.js';
import { INK_DARK, INK_LIGHT, blend, contrastRatio, inkOn } from './contrast';

const pp = tailwindConfig.theme.extend.colors.pp as Record<string, string>;
const AA = 4.5;

describe('contrast helpers', () => {
  it('matches the WCAG reference values', () => {
    expect(contrastRatio('#ffffff', '#000000')).toBeCloseTo(21, 5);
    expect(contrastRatio('#777777', '#ffffff')).toBeCloseTo(4.48, 2);
    expect(contrastRatio('#fff', '#fff')).toBe(1);
  });

  it('keeps the dark ink equal to the night token', () => {
    expect(INK_DARK).toBe(pp.night);
  });
});

describe('theme token pairs meet WCAG AA (4.5:1 for normal text)', () => {
  const surfaces = ['night', 'deep', 'panel', 'raised'] as const;
  const textTokens = ['chalk', 'mute', 'pulse', 'pulseSoft', 'signal', 'gold', 'turfLine'] as const;
  for (const fg of textTokens) {
    for (const bg of surfaces) {
      it(`${fg} text on ${bg}`, () => {
        expect(contrastRatio(pp[fg], pp[bg])).toBeGreaterThanOrEqual(AA);
      });
    }
  }

  it('white and chalk text on the filled red (buttons, active tab, tags)', () => {
    expect(contrastRatio(INK_LIGHT, pp.pulseFill)).toBeGreaterThanOrEqual(AA);
    expect(contrastRatio(pp.chalk, pp.pulseFill)).toBeGreaterThanOrEqual(AA);
  });

  it.each(['signal', 'gold', 'chalk', 'pulseSoft'])('night text on filled %s', (bg) => {
    expect(contrastRatio(pp.night, pp[bg])).toBeGreaterThanOrEqual(AA);
  });

  it('chalk text on the turf', () => {
    expect(contrastRatio(pp.chalk, pp.turf)).toBeGreaterThanOrEqual(AA);
  });
});

describe('inkOn picks a readable ink for any team colour', () => {
  // Both synthetic clubs (home blue, away orange) plus a spread of kit colours.
  const kits = ['#2f6fde', '#f08a24', '#ffffff', '#000000', '#ffd400', '#1e8f3a', '#7a1f8f', '#c0c0c0', '#8b0000', '#00bcd4'];
  it.each(kits)('%s', (kit) => {
    // The better of two inks always reaches at least 4.5:1 for these kits.
    expect(contrastRatio(inkOn(kit), kit)).toBeGreaterThanOrEqual(AA);
  });

  it('uses dark ink on the away orange and light ink on the home blue', () => {
    expect(inkOn('#f08a24')).toBe(INK_DARK);
    expect(inkOn('#2f6fde')).toBe(INK_LIGHT);
  });

  it('works on a blended heat-map cell', () => {
    for (let a = 0.15; a <= 1; a += 0.05) {
      for (const top of [pp.signal, pp.pulse]) {
        const bg = blend(top, a, pp.deep);
        expect(contrastRatio(inkOn(bg), bg)).toBeGreaterThanOrEqual(AA);
      }
    }
  });
});
