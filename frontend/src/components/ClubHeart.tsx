// Club-heart showcase for the split view: the same moment for a fan of each club.
// Personalisation may change what is picked (priority) and how it is framed, never
// the numbers: numbers printed in both versions are highlighted, and any number that
// appears in only one version is called out.
import React from 'react';
import { Check, Heart, TriangleAlert } from 'lucide-react';
import type { OverlayCard, TeamInfo } from '../api/contract';
import { useI18n } from '../i18n';
import { textLanguage } from '../lib/languages';
import { ProducedBadge } from './NarrativeFeed';
import { Badge, cx } from './ui';
import { Skeleton } from './InsightStatus';

const NUMBER = /\d+(?:[.,]\d+)?/g;
const ARABIC_DIGITS = /[٠-٩]/g;

/** Every number printed in a card's text (Arabic-Indic digits read as Western), in order. */
export function printedNumbers(card: OverlayCard | null): string[] {
  if (!card) return [];
  const text = [card.headline, card.body, card.why].join(' ').replace(ARABIC_DIGITS, (d) => String(d.charCodeAt(0) - 0x660));
  return [...text.matchAll(NUMBER)].map((m) => m[0].replace(',', '.'));
}

/** Numbers in both, and numbers only one side prints (as multisets, so "2" twice vs once differs). */
export function compareNumbers(a: OverlayCard | null, b: OverlayCard | null) {
  const left = printedNumbers(a);
  const right = printedNumbers(b);
  const pool = [...right];
  const same: string[] = [];
  const onlyA: string[] = [];
  for (const n of left) {
    const i = pool.indexOf(n);
    if (i >= 0) {
      same.push(n);
      pool.splice(i, 1);
    } else onlyA.push(n);
  }
  return { same, onlyA, onlyB: pool };
}

/** Evidence rows with the same label, value and unit on both cards. */
export function sameEvidence(a: OverlayCard | null, b: OverlayCard | null) {
  if (!a || !b) return { same: 0, total: Math.max(a?.evidence.length ?? 0, b?.evidence.length ?? 0) };
  const key = (e: OverlayCard['evidence'][number]) => `${e.label_key ?? e.label}|${String(e.value)}|${e.unit ?? ''}`;
  const right = new Set(b.evidence.map(key));
  const same = a.evidence.filter((e) => right.has(key(e))).length;
  return { same, total: Math.max(a.evidence.length, b.evidence.length) };
}

const Highlighted: React.FC<{ text: string; shared: Set<string> }> = ({ text, shared }) => {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(NUMBER)) {
    const at = m.index ?? 0;
    if (at > last) parts.push(text.slice(last, at));
    const norm = m[0].replace(',', '.');
    parts.push(
      shared.has(norm) ? (
        <mark key={at} data-same-number className="ltr-nums bg-pp-signal px-0.5 font-bold text-pp-night">
          {m[0]}
        </mark>
      ) : (
        <mark key={at} data-own-number className="ltr-nums bg-pp-pulseFill px-0.5 font-bold text-white">
          {m[0]}
        </mark>
      ),
    );
    last = at + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
};

export const ClubColumn: React.FC<{ team: TeamInfo; card: OverlayCard | null; other: OverlayCard | null; loading: boolean }> = ({
  team,
  card,
  other,
  loading,
}) => {
  const { t } = useI18n();
  const shared = new Set(compareNumbers(card, other).same);
  const label = t('heart.fanOf', { club: team.short_name });
  return (
    <section aria-label={label} aria-busy={loading} className="border border-pp-line bg-pp-panel p-4" style={{ borderTop: `4px solid ${team.primary_color}` }}>
      <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-display text-lg font-bold uppercase tracking-broadcast text-pp-chalk">
          <Heart className="h-5 w-5" style={{ color: team.primary_color }} fill={team.primary_color} aria-hidden />
          {label}
        </h2>
        {card && <ProducedBadge card={card} />}
      </header>
      {loading ? (
        <Skeleton lines={4} />
      ) : !card ? (
        <p className="text-sm text-pp-mute">{t('heart.notPicked')}</p>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
            <Badge tone={card.favourite_side ? 'signal' : 'mute'}>{t(card.favourite_side ? 'heart.ownClub' : 'heart.rivalClub')}</Badge>
            <span className="ltr-nums text-pp-mute">{t('heart.priority', { n: card.priority })}</span>
            {other && other.priority !== card.priority && (
              <span className="text-pp-mute">{t(card.priority > other.priority ? 'heart.rankedHigher' : 'heart.rankedLower')}</span>
            )}
          </div>
          <div dir={card.rtl ? 'rtl' : 'ltr'} lang={textLanguage(card)}>
            <h3 className="font-display text-xl font-bold leading-tight text-white">
              <Highlighted text={card.headline} shared={shared} />
            </h3>
            {card.body && (
              <p className="mt-2 text-sm leading-relaxed text-slate-200">
                <Highlighted text={card.body} shared={shared} />
              </p>
            )}
            {card.why && (
              <p className="mt-2 border border-pp-line/70 bg-pp-deep/80 p-2.5 text-xs leading-relaxed text-slate-200">
                <Highlighted text={card.why} shared={shared} />
              </p>
            )}
          </div>
        </>
      )}
    </section>
  );
};

export const NumbersVerdict: React.FC<{ a: OverlayCard | null; b: OverlayCard | null }> = ({ a, b }) => {
  const { t } = useI18n();
  const { same, onlyA, onlyB } = compareNumbers(a, b);
  const ev = sameEvidence(a, b);
  const identical = onlyA.length === 0 && onlyB.length === 0;
  const evidenceSame = ev.same === ev.total;
  return (
    <section
      aria-label={t('heart.verdict')}
      className={cx('flex flex-wrap items-start gap-3 border-s-4 p-3 text-sm', identical && evidenceSame ? 'border-pp-signal bg-pp-signal/10' : 'border-pp-gold bg-pp-gold/10')}
    >
      {identical && evidenceSame ? <Check className="mt-0.5 h-5 w-5 text-pp-signal" aria-hidden /> : <TriangleAlert className="mt-0.5 h-5 w-5 text-pp-gold" aria-hidden />}
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-bold text-pp-chalk">
          {identical ? t('heart.numbersSame', { n: same.length }) : t('heart.numbersDiffer', { n: onlyA.length + onlyB.length })}
        </p>
        <p className="ltr-nums text-xs text-pp-mute">{t('heart.evidence', { n: ev.same, total: ev.total })}</p>
        {!identical && (
          <p className="ltr-nums text-xs text-pp-gold">
            {[...onlyA, ...onlyB].join(' · ')}
          </p>
        )}
        <p className="text-xs text-pp-mute">{t('heart.legend')}</p>
      </div>
    </section>
  );
};
