import { describe, expect, it } from 'vitest';
import { makeI18n } from '../i18n';
import { groupByClock, recapStatRows, tagLabel, upcomingLabelKey } from './labels';

describe('human labels', () => {
  it('tags never show underscores, and are translated', () => {
    expect(tagLabel(makeI18n('en').t, 'decision_making')).toBe('Decision making');
    expect(tagLabel(makeI18n('ar').t, 'decision_making')).toBe('اتخاذ القرار');
    expect(tagLabel(makeI18n('en').t, 'brand_new_tag')).toBe('Brand new tag');
    expect(tagLabel(makeI18n('en').t, 'Shot selection')).toBe('Shot selection');
  });

  it('upcoming moments get a kind label that gives nothing away', () => {
    const t = makeI18n('en').t;
    expect(t(upcomingLabelKey('goal'))).toBe('Attack');
    expect(t(upcomingLabelKey('big_chance'))).toBe('Attack');
    expect(t(upcomingLabelKey('correction'))).toBe('Referee decision');
    expect(t(upcomingLabelKey('speed_burst'))).toBe('Key moment');
  });

  it('the recap shows only labelled match numbers, with club names', () => {
    const rows = recapStatRows(makeI18n('en').t, { home: 'Northbridge FC', away: 'Harbour City', xg_home: 2.2, generated_at: '90:00', score_w: 3, n_big_chances: 5, potm_short: 'Kerrigan' }, null);
    expect(rows.map((r) => r.label)).toEqual(['Northbridge FC chance quality (xG)', 'Big chances']);
  });

  it('groups moments at the same clock and half', () => {
    const b = (kind: 'goal' | 'correction' | 'card', match_clock: string, period = 1) => ({ kind, match_clock, period });
    const g = groupByClock([b('correction', '40:22'), b('goal', '40:22'), b('card', '40:22', 2), b('card', '41:00')]);
    expect(g.map((x) => [x.lead.kind, x.count])).toEqual([['goal', 2], ['card', 1], ['card', 1]]);
  });
});
