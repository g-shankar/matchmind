import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Award,
  Bell,
  ChevronDown,
  Clock,
  Crosshair,
  Flame,
  Footprints,
  Gavel,
  Goal,
  Play,
  Rocket,
  Route,
  ShieldCheck,
  Sparkles,
  Split,
  Square,
  Target,
  TrendingUp,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import type { Evidence, FactValue, MatchEvent, MomentKind, OverlayCard, Teams } from '../api/contract';
import { useI18n } from '../i18n';
import { isTranslationReason, textLanguage } from '../lib/languages';
import type { MatchViewState } from '../state/matchStore';
import { TranslationTag } from './LanguagePicker';
import type { ViewProps } from '../views/types';
import { playerName, shortName, teamById } from '../lib/teams';
import { Badge, Panel, TeamDot, cx } from './ui';
import { ShowWorkingButton } from './ShowWorking';
import { CrewRelayToggle } from './CrewRelay';
import { tagLabel } from '../lib/labels';

export interface NarrativeFeedProps extends ViewProps {
  onOpenReplay: (card: OverlayCard) => void;
}

export const KIND_ICON: Record<MomentKind, LucideIcon> = {
  goal: Goal,
  card: Square,
  big_chance: Target,
  better_option: Split,
  unfound_run: Footprints,
  momentum_swing: TrendingUp,
  pressure_spell: Flame,
  speed_burst: Zap,
  rocket_shot: Rocket,
  distance_milestone: Route,
  hard_pass: Crosshair,
  key_tackle: ShieldCheck,
  milestone: Award,
  correction: Gavel,
};

export const isSpecialKind = (kind: MomentKind) => kind === 'better_option' || kind === 'unfound_run';

/** Translates a key, or returns `fallback` when no table has it. */
export function tOr(t: (k: string) => string, key: string, fallback: string) {
  const out = t(key);
  return out === key ? fallback : out;
}

/** Match clock for a card: from its source event, else from its bookmark, else none. */
export function cardClock(card: OverlayCard, match: Pick<MatchViewState, 'events' | 'bookmarks'>): string | null {
  for (const ev of card.evidence) {
    if (!ev.source_event_id) continue;
    const e = match.events.find((x) => x.event_id === ev.source_event_id);
    if (e) return e.match_clock;
  }
  return match.bookmarks.find((b) => b.moment_id === card.moment_id)?.match_clock ?? null;
}

export function formatFact(value: FactValue, num: (v: number, d?: number) => string, t: (k: string) => string) {
  if (typeof value === 'boolean') return t(value ? 'studio.feed.yes' : 'studio.feed.no');
  if (typeof value === 'number') {
    // Exactly as in the payload (up to three decimals), so it matches the fact-checked text.
    return num(value, Math.min(3, String(value).split('.')[1]?.length ?? 0));
  }
  return value;
}

export const EvidenceTable: React.FC<{ evidence: Evidence[]; className?: string }> = ({ evidence, className }) => {
  const { t, num } = useI18n();
  return (
    <dl className={cx('divide-y divide-pp-line/60 rounded-lg border border-pp-line/70 bg-pp-deep/80 text-xs', className)}>
      {evidence.map((ev, i) => (
        <div key={`${ev.label}-${i}`} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 px-3 py-1.5">
          <dt className="text-pp-mute">{tOr(t, `studio.ev.${ev.label}`, ev.label.replace(/_/g, ' '))}</dt>
          <dd className="flex items-baseline gap-2">
            <span className="ltr-nums font-bold text-white">
              {formatFact(ev.value, num, t)}
              {ev.unit ? ` ${ev.unit === 'km/h' ? t('unit.kmh') : ev.unit}` : ''}
            </span>
            {ev.source_event_id && (
              <span className="ltr-nums text-[10px] text-pp-mute/80">{t('evidence.source', { id: ev.source_event_id })}</span>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
};

export const ProducedBadge: React.FC<{ card: OverlayCard }> = ({ card }) => {
  const { t } = useI18n();
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <Badge tone={card.produced_by === 'ai' ? 'signal' : 'mute'} title={t(`studio.feed.producedHint.${card.produced_by}`)}>
        {t(`produced.${card.produced_by}`)}
      </Badge>
      {card.fallback_reason && !isTranslationReason(card.fallback_reason) && (
        <span className="text-[10px] text-pp-gold">{t('studio.feed.fallback', { reason: card.fallback_reason })}</span>
      )}
      <TranslationTag item={card} />
    </span>
  );
};

type Tab = 'stories' | 'events';

export const NarrativeFeed: React.FC<NarrativeFeedProps> = ({ match, onOpenReplay }) => {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>('stories');
  const cards = useMemo(() => match.cards.filter((c) => c.slot !== 'pitch_tag').slice().reverse(), [match.cards]);
  const events = useMemo(() => match.events.slice().reverse(), [match.events]);
  // Stable keys (not list positions), so a new card arriving on top never hands one
  // card's open evidence or "Show your working" to the card below it.
  const keys = useMemo(() => {
    const seen = new Map<string, number>();
    return cards.map((c) => {
      const n = seen.get(c.card_id) ?? 0;
      seen.set(c.card_id, n + 1);
      return n ? `${c.card_id}#${n}` : c.card_id;
    });
  }, [cards]);
  const favourite = teamById(match.teams, match.profile.favourite_team);
  const audienceNote = useAudienceNote(match.profile.persona);

  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: 'stories', label: t('studio.feed.stories'), count: cards.length },
    { id: 'events', label: t('studio.feed.events'), count: events.length },
  ];

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-pp-pulse" aria-hidden />
          {t('studio.feed.title')}
        </span>
      }
      actions={<span className="text-[11px] text-pp-mute">{t('studio.feed.newest')}</span>}
      className="flex flex-col lg:max-h-[calc(100vh-140px)]"
    >
      {audienceNote && (
        <p role="status" data-testid="audience-note" className="mb-3 border-s-4 border-pp-signal bg-pp-signal/10 px-3 py-2 text-xs text-pp-chalk">
          {t('guide.audience.now', { who: t(`persona.${audienceNote}`) })}
        </p>
      )}
      <div role="tablist" aria-label={t('studio.feed.tabs')} className="mb-3 flex gap-1 rounded-xl border border-pp-line bg-pp-deep p-1">
        {tabs.map((x) => (
          <button
            key={x.id}
            type="button"
            role="tab"
            id={`feed-tab-${x.id}`}
            aria-selected={tab === x.id}
            aria-controls={`feed-panel-${x.id}`}
            onClick={() => setTab(x.id)}
            className={cx(
              'flex min-h-[44px] flex-1 items-center justify-center gap-1.5 rounded-lg px-3 text-xs font-bold transition',
              tab === x.id ? 'bg-pp-raised text-white ring-1 ring-pp-pulse/60' : 'text-pp-mute hover:text-white',
            )}
          >
            {x.label}
            <span className="ltr-nums rounded-full bg-pp-night px-1.5 text-[10px] text-pp-mute">{x.count}</span>
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`feed-panel-${tab}`}
        aria-labelledby={`feed-tab-${tab}`}
        aria-live="polite"
        className="flex-1 space-y-2.5 lg:overflow-y-auto lg:pe-1"
      >
        {tab === 'stories' ? (
          cards.length === 0 ? (
            <Empty />
          ) : (
            cards.map((c, i) =>
              c.slot === 'metric_alert' ? (
                <AlertRow key={keys[i]} card={c} match={match} />
              ) : (
                <StoryCard
                  key={keys[i]}
                  card={c}
                  match={match}
                  isTop={i === 0}
                  favouriteColor={c.favourite_side ? favourite?.primary_color ?? null : null}
                  onOpenReplay={onOpenReplay}
                />
              ),
            )
          )
        ) : events.length === 0 ? (
          <Empty />
        ) : (
          <ol className="space-y-1.5">
            {events.map((e, i) => (
              <EventRow key={e.event_id} event={e} teams={match.teams} isTop={i === 0} />
            ))}
          </ol>
        )}
      </div>
    </Panel>
  );
};

const AUDIENCE_NOTE_MS = 8000;

/** After the viewer picks another audience (not on first load), a short note says what changed. */
function useAudienceNote(persona: string): string | null {
  const previous = useRef(persona);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => {
    if (persona === previous.current) return;
    previous.current = persona;
    setNote(persona);
    const id = setTimeout(() => setNote(null), AUDIENCE_NOTE_MS);
    return () => clearTimeout(id);
  }, [persona]);
  return note;
}

const Empty: React.FC = () => {
  const { t } = useI18n();
  return (
    <div className="flex h-40 flex-col items-center justify-center gap-2 text-center text-sm text-pp-mute">
      <Sparkles className="h-7 w-7 animate-pulse text-pp-line" aria-hidden />
      {t('common.waiting')}
    </div>
  );
};

const KindBadge: React.FC<{ kind: MomentKind; special?: boolean }> = ({ kind, special }) => {
  const { t } = useI18n();
  const Icon = KIND_ICON[kind] ?? Award;
  return (
    <Badge tone={special ? 'gold' : kind === 'goal' ? 'pulse' : 'signal'}>
      <Icon className="h-3 w-3" aria-hidden />
      {t(`kind.${kind}`)}
    </Badge>
  );
};

const ClockPill: React.FC<{ clock: string | null }> = ({ clock }) =>
  clock ? (
    <span className="inline-flex items-center gap-1 rounded-md border border-pp-line bg-pp-deep px-1.5 py-0.5 text-[11px] font-bold text-pp-signal">
      <Clock className="h-3 w-3" aria-hidden />
      <span className="ltr-nums">{clock}</span>
    </span>
  ) : null;

export const StoryCard: React.FC<{
  card: OverlayCard;
  match: MatchViewState;
  isTop: boolean;
  favouriteColor: string | null;
  onOpenReplay: (card: OverlayCard) => void;
  highlight?: boolean;
}> = ({ card, match, isTop, favouriteColor, onOpenReplay, highlight }) => {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  // On phones only the newest (or picked) card shows in full; older ones fold to their headline
  // and open on tap, so the feed reads as a list instead of one very long scroll.
  const [expanded, setExpanded] = useState(false);
  const articleRef = useRef<HTMLElement>(null);
  const compact = !isTop && !highlight && !expanded;
  const fold = compact ? 'max-sm:hidden' : undefined;
  const special = isSpecialKind(card.kind);
  const names = card.player_ids.map((id) => playerName(match.teams, id)).filter(Boolean);
  const team = teamById(match.teams, card.team);
  const ruledOut = match.cue.ruledOut.includes(card.moment_id);

  return (
    <article
      ref={articleRef}
      tabIndex={-1}
      data-ruled-out={ruledOut || undefined}
      dir={card.rtl ? 'rtl' : undefined}
      lang={textLanguage(card)}
      className={cx(
        'animate-slide-up rounded-xl border bg-pp-raised/60 p-3.5 focus:outline-none',
        special ? 'border-pp-signal bg-pp-raised border-s-4' : 'border-pp-line/80',
        isTop && 'ring-1 ring-pp-pulse/40',
        highlight && 'ring-2 ring-pp-signal',
        ruledOut && 'opacity-60 grayscale',
        card.kind === 'correction' && 'border-s-4 border-pp-pulse',
        favouriteColor && 'border-s-4',
      )}
      style={favouriteColor ? { borderInlineStartColor: favouriteColor } : undefined}
    >
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <ClockPill clock={cardClock(card, match)} />
        <KindBadge kind={card.kind} special={special} />
        {ruledOut && (
          <Badge tone="pulse">
            <Gavel className="h-3 w-3" aria-hidden />
            {t('cue.ruledOut')}
          </Badge>
        )}
        {card.favourite_side && (
          <Badge className="text-white" title={team?.name}>
            <TeamDot team={team} size={8} />
            {t('studio.feed.yourTeam')}
          </Badge>
        )}
        <span className="ms-auto">
          <ProducedBadge card={card} />
        </span>
      </div>

      <h3 className={cx('font-display text-base font-bold leading-tight text-white', ruledOut && 'line-through decoration-pp-pulse decoration-2')}>
        {card.headline}
      </h3>
      {names.length > 0 && (
        <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-pp-mute">
          <TeamDot team={team} size={8} />
          {names.join(' · ')}
        </p>
      )}
      {compact && (
        <div className="mt-2 flex flex-wrap items-center gap-2 sm:hidden">
          <button
            type="button"
            onClick={() => {
              setExpanded(true);
              // The button goes away once the card opens; keep the reader on the card.
              requestAnimationFrame(() => articleRef.current?.focus({ preventScroll: true }));
            }}
            aria-expanded={false}
            data-testid="card-expand"
            className="inline-flex min-h-[44px] items-center gap-1 rounded-lg px-2 text-xs font-semibold text-pp-signal hover:bg-pp-deep"
          >
            <ChevronDown className="h-3.5 w-3.5" aria-hidden />
            {t('layout.cardMore')}
          </button>
          {card.replay && (
            <button
              type="button"
              onClick={() => onOpenReplay(card)}
              className="ms-auto inline-flex min-h-[44px] items-center gap-1.5 rounded-lg bg-pp-pulseFill px-3 text-xs font-bold text-white shadow hover:bg-pp-pulseFill/85"
            >
              <Play className="h-3.5 w-3.5" aria-hidden />
              {t('studio.feed.replay')}
            </button>
          )}
        </div>
      )}
      <div className={fold}>
      {card.body && <p className="mt-2 text-sm leading-relaxed text-slate-200">{card.body}</p>}
      <p data-testid="card-voice" className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-pp-mute">
        {t('guide.voice', { who: t(`persona.${card.persona}`) })}
      </p>

      {card.why && (
        <div className="mt-2 rounded-lg border border-pp-line/70 bg-pp-deep/80 p-2.5">
          <span className="mb-0.5 block text-[10px] font-bold uppercase tracking-wider text-pp-pulseSoft">
            {t('studio.feed.why')}
            <span className="ms-1 font-semibold normal-case tracking-normal text-pp-mute">· {t('guide.whySame')}</span>
          </span>
          <p className="text-xs leading-relaxed text-slate-200">{card.why}</p>
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {card.tactical_tag && (
          <span className="rounded-md border border-pp-line bg-pp-night px-2 py-0.5 text-[11px] font-semibold text-pp-mute">
            <bdi>#{tagLabel(t, card.tactical_tag)}</bdi>
          </span>
        )}
        {card.evidence.length > 0 && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="inline-flex min-h-[44px] items-center gap-1 rounded-lg px-2 text-xs font-semibold text-pp-signal hover:bg-pp-deep"
          >
            <ChevronDown className={cx('h-3.5 w-3.5 transition', open && 'rotate-180')} aria-hidden />
            {open ? t('studio.feed.hideEvidence') : t('studio.feed.showEvidence', { count: card.evidence.length })}
          </button>
        )}
        <ShowWorkingButton momentId={card.moment_id} persona={card.persona} language={card.language} />
        <CrewRelayToggle momentId={card.moment_id} slot={card.slot} />
        {card.replay && (
          <button
            type="button"
            onClick={() => onOpenReplay(card)}
            className="ms-auto inline-flex min-h-[44px] items-center gap-1.5 rounded-lg bg-pp-pulseFill px-3 text-xs font-bold text-white shadow hover:bg-pp-pulseFill/85"
          >
            <Play className="h-3.5 w-3.5" aria-hidden />
            {t('studio.feed.replay')}
          </button>
        )}
      </div>
      {open && <EvidenceTable evidence={card.evidence} className="mt-2" />}
      </div>
    </article>
  );
};

const AlertRow: React.FC<{ card: OverlayCard; match: MatchViewState }> = ({ card, match }) => {
  const { t } = useI18n();
  const team = teamById(match.teams, card.team);
  const ev = card.evidence[0];
  const { num } = useI18n();
  return (
    <div
      dir={card.rtl ? 'rtl' : undefined}
      lang={textLanguage(card)}
      className="flex items-center gap-2 rounded-lg border border-pp-line/60 bg-pp-deep/70 px-2.5 py-1.5 text-xs"
      title={t('studio.feed.alert')}
    >
      <Bell className="h-3.5 w-3.5 shrink-0 text-pp-gold" aria-hidden />
      <ClockPill clock={cardClock(card, match)} />
      <TeamDot team={team} size={8} />
      <span className="min-w-0 flex-1 truncate text-slate-200">{card.headline}</span>
      {ev && (
        <span className="ltr-nums shrink-0 font-bold text-white">
          {formatFact(ev.value, num, t)}
          {ev.unit ? ` ${ev.unit === 'km/h' ? t('unit.kmh') : ev.unit}` : ''}
        </span>
      )}
    </div>
  );
};

const Chip: React.FC<{ tone?: 'signal' | 'gold' | 'pulse' | 'mute'; children: React.ReactNode }> = ({ tone = 'mute', children }) => (
  <Badge tone={tone} className="ltr-nums text-[10px]">
    {children}
  </Badge>
);

const EventRow: React.FC<{ event: MatchEvent; teams: Teams | null; isTop: boolean }> = ({ event: e, teams, isTop }) => {
  const { t, num } = useI18n();
  const team = teamById(teams, e.team);
  const name = playerName(teams, e.player_id);
  const m = e.metrics;
  return (
    <li
      className={cx(
        'flex items-start gap-2.5 rounded-lg border p-2.5 text-xs',
        isTop ? 'animate-slide-up border-pp-pulse/50 bg-pp-raised/80' : 'border-pp-line/60 bg-pp-deep/60',
      )}
    >
      <span className="ltr-nums shrink-0 rounded border border-pp-line bg-pp-night px-1.5 py-0.5 text-[11px] font-bold text-pp-mute">
        {e.match_clock}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <TeamDot team={team} size={8} />
          <span className="font-semibold text-white">{tOr(t, `event.${e.type}`, e.type)}</span>
          {name && <span className="text-pp-mute">{shortName(name)}</span>}
        </div>
        <div className="mt-1 flex flex-wrap gap-1">
          {m.progressive && e.type === 'pass' && <Chip tone="signal">{t('event.progressive')}</Chip>}
          {m.chance_quality != null && <Chip tone="pulse">{t('studio.chip.xg', { value: num(m.chance_quality, 2) })}</Chip>}
          {m.player_speed_kmh != null && <Chip tone="gold">{t('studio.chip.playerSpeed', { value: num(m.player_speed_kmh, 1) })}</Chip>}
          {m.ball_speed_kmh != null && <Chip>{t('studio.chip.ballSpeed', { value: num(m.ball_speed_kmh, 0) })}</Chip>}
          {m.pass_difficulty != null && <Chip>{t('studio.chip.difficulty', { value: num(m.pass_difficulty, 0) })}</Chip>}
        </div>
      </div>
    </li>
  );
};
