import React, { useEffect, useMemo, useRef, useState } from 'react';
import { BarChart3, Heart, Languages } from 'lucide-react';
import type { OverlayCard, PersonaType } from '../api/contract';
import { UI_LANGUAGES, useI18n, type UiLanguage } from '../i18n';
import { Pitch2D } from '../components/Pitch2D';
import { ReplayCard } from '../components/ReplayCard';
import { EvidenceTable, KIND_ICON, ProducedBadge, cardClock } from '../components/NarrativeFeed';
import { textLanguage } from '../lib/languages';
import { Badge, Panel, Segmented, cx } from '../components/ui';
import { ClubColumn, NumbersVerdict } from '../components/ClubHeart';
import { compareMoments } from '../components/MomentsList';
import type { ViewProps } from './types';
import { tagLabel } from '../lib/labels';

const STORY_SLOTS = new Set<OverlayCard['slot']>(['lower_third', 'side_panel', 'full_screen']);

type Load =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; casual: OverlayCard | null; tactical: OverlayCard | null; others: { lang: UiLanguage; card: OverlayCard | null }[] }
  | { status: 'clubs'; home: OverlayCard | null; away: OverlayCard | null };

/** Fan vs analyst (two audiences), or one fan of each club (two club hearts). */
export type Compare = 'persona' | 'clubs';

export const SplitView: React.FC<ViewProps> = ({ match, actions }) => {
  const { t } = useI18n();
  const [picked, setPicked] = useState<string | null>(null);
  const [load, setLoad] = useState<Load>({ status: 'idle' });
  const [compare, setCompare] = useState<Compare>('persona');
  const homeId = match.teams?.home.team_id ?? null;
  const awayId = match.teams?.away.team_id ?? null;
  const heartPersona: PersonaType = match.profile.persona === 'player_spotlight' ? 'casual' : match.profile.persona;
  const getMoment = useRef(actions.getMoment);
  getMoment.current = actions.getMoment;

  const lang = match.profile.language;
  const now = { clock_s: match.playback.clock_s, period: match.playback.period };
  const latest = useMemo(() => {
    for (let i = match.cards.length - 1; i >= 0; i--) if (STORY_SLOTS.has(match.cards[i].slot)) return match.cards[i];
    return null;
  }, [match.cards]);
  const played = useMemo(
    () => match.bookmarks.filter((b) => compareMoments(b, now) <= 0).sort((a, b) => compareMoments(b, a)),
    [match.bookmarks, now.clock_s, now.period],
  );
  // Opens on the newest moment worth comparing: a kick-off or half-time milestone says the
  // same thing to everyone, so a story moment (or the newest bookmark) comes first.
  const latestStory = useMemo(() => {
    for (let i = match.cards.length - 1; i >= 0; i--) {
      const c = match.cards[i];
      if (STORY_SLOTS.has(c.slot) && c.kind !== 'milestone') return c;
    }
    return null;
  }, [match.cards]);
  const latestBookmark = played.find((b) => b.kind !== 'milestone') ?? null;
  const autoId = latestStory?.moment_id ?? latestBookmark?.moment_id ?? latest?.moment_id ?? null;
  const autoBookmark = autoId ? match.bookmarks.find((b) => b.moment_id === autoId) ?? null : null;
  const momentId = picked ?? latestStory?.moment_id ?? latestBookmark?.moment_id ?? latest?.moment_id ?? null;

  useEffect(() => {
    if (!momentId) {
      setLoad({ status: 'idle' });
      return;
    }
    let live = true;
    setLoad({ status: 'loading' });
    const get = (persona: PersonaType, l: string) => getMoment.current(momentId, persona, l as typeof lang).catch(() => null);
    if (compare === 'clubs') {
      // Same moment, same audience and language: only the club in the viewer's heart changes.
      const forClub = (club: string | null) => getMoment.current(momentId, heartPersona, lang, club).catch(() => null);
      Promise.all([forClub(homeId), forClub(awayId)])
        .then(([home, away]) => {
          if (!live) return;
          if (!home && !away) return setLoad({ status: 'error' });
          setLoad({ status: 'clubs', home, away });
        })
        .catch(() => live && setLoad({ status: 'error' }));
      return () => {
        live = false;
      };
    }
    const otherLangs = UI_LANGUAGES.filter((l) => l !== lang);
    Promise.all([get('casual', lang), get('tactical', lang), Promise.all(otherLangs.map((l) => get('casual', l)))])
      .then(([casual, tactical, others]) => {
        if (!live) return;
        if (!casual && !tactical) return setLoad({ status: 'error' });
        setLoad({ status: 'ready', casual, tactical, others: otherLangs.map((l, i) => ({ lang: l, card: others[i] })) });
      })
      .catch(() => live && setLoad({ status: 'error' }));
    return () => {
      live = false;
    };
  }, [momentId, lang, compare, homeId, awayId, heartPersona]);

  const ready = load.status === 'ready' ? load : null;
  const clubs = load.status === 'clubs' ? load : null;
  const base = ready?.casual ?? ready?.tactical ?? clubs?.home ?? clubs?.away ?? null;
  const sourceId = base?.evidence.find((e) => e.source_event_id)?.source_event_id ?? null;
  const sourceEvent = sourceId ? match.events.find((e) => e.event_id === sourceId) ?? null : null;
  const clock = base ? cardClock(base, match) : null;

  return (
    <div className="space-y-4">
      <Panel title={t('studio.split.title')}>
        {(played.length > 0 || latest) && (
            <label className="mb-3 flex min-w-0 flex-wrap items-center gap-2 text-xs text-pp-mute">
              <span className="font-semibold">{t('studio.split.pick')}</span>
              <select
                value={picked ?? ''}
                onChange={(e) => setPicked(e.target.value || null)}
                className="min-h-[44px] w-full min-w-0 max-w-full rounded-lg border border-pp-line bg-pp-deep px-2 text-xs text-white sm:w-auto sm:max-w-md"
              >
                <option value="">
                  {t('studio.split.latest')}
                  {autoBookmark ? ` (${autoBookmark.match_clock} · ${autoBookmark.title})` : ''}
                </option>
                {played.map((b) => (
                  <option key={b.moment_id} value={b.moment_id}>
                    {b.match_clock} · {b.title}
                  </option>
                ))}
              </select>
            </label>
        )}
        <p className="text-sm text-pp-mute">{t(compare === 'clubs' ? 'heart.subtitle' : 'studio.split.subtitle')}</p>
        {match.teams && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-pp-mute">
            <span className="font-semibold">{t('heart.compare')}</span>
            <Segmented
              label={t('heart.compare')}
              value={compare}
              onChange={setCompare}
              className="[&>button]:min-h-[44px]"
              options={[
                { value: 'persona' as const, label: t('heart.option.persona') },
                { value: 'clubs' as const, label: t('heart.option.clubs', { home: match.teams.home.short_name, away: match.teams.away.short_name }) },
              ]}
            />
          </div>
        )}
      </Panel>

      {!momentId ? (
        <Panel>
          <p className="py-8 text-center text-sm text-pp-mute">{t('studio.split.empty')}</p>
        </Panel>
      ) : load.status === 'error' ? (
        <Panel>
          <p role="alert" className="py-8 text-center text-sm text-pp-pulseSoft">
            {t('studio.split.error')}
          </p>
        </Panel>
      ) : (
        <>
          {(ready || clubs) && base && (
            <div className="rounded-2xl border border-pp-line/70 bg-pp-panel/60 p-3">
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                <Badge tone="gold">
                  {React.createElement(KIND_ICON[base.kind], { className: 'h-3 w-3', 'aria-hidden': true })}
                  {t(`kind.${base.kind}`)}
                </Badge>
                {clock && <span className="ltr-nums font-bold text-pp-signal">{clock}</span>}
                <span className="text-pp-mute">{t('studio.split.facts')}</span>
              </div>
              {base.replay ? (
                <ReplayCard card={base} teams={match.teams} compact />
              ) : sourceEvent ? (
                <div dir="ltr">
                  <Pitch2D teams={match.teams} event={sourceEvent} showTags />
                </div>
              ) : (
                <p className="text-xs text-pp-mute">{t('studio.split.noPitch')}</p>
              )}
            </div>
          )}

          {compare === 'clubs' && match.teams ? (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <ClubColumn team={match.teams.home} card={clubs?.home ?? null} other={clubs?.away ?? null} loading={!clubs} />
                <ClubColumn team={match.teams.away} card={clubs?.away ?? null} other={clubs?.home ?? null} loading={!clubs} />
              </div>
              {clubs && <NumbersVerdict a={clubs.home} b={clubs.away} />}
              {match.status === 'demo' && <p className="text-xs text-pp-mute">{t('heart.demoNote')}</p>}
            </>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              <VoiceColumn persona="casual" card={ready?.casual ?? null} loading={!ready} />
              <VoiceColumn persona="tactical" card={ready?.tactical ?? null} loading={!ready} />
            </div>
          )}

          {compare === 'persona' && (
          <Panel
            title={
              <span className="flex items-center gap-2">
                <Languages className="h-4 w-4 text-pp-signal" aria-hidden />
                {t('studio.split.languages')}
              </span>
            }
          >
            <ul className="grid gap-2 sm:grid-cols-2">
              {(ready?.others ?? UI_LANGUAGES.filter((l) => l !== lang).map((l) => ({ lang: l, card: null }))).map((o) => (
                <li
                  key={o.lang}
                  lang={o.lang}
                  dir={o.lang === 'ar' ? 'rtl' : 'ltr'}
                  className="rounded-xl border border-pp-line/70 bg-pp-deep/70 p-3 text-start"
                >
                  <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-pp-mute">{t(`lang.${o.lang}`)}</span>
                  {!ready ? (
                    <Skeleton lines={1} />
                  ) : o.card && textLanguage(o.card) === o.lang ? (
                    <span className="font-display text-sm font-semibold text-white">{o.card.headline}</span>
                  ) : (
                    <span className="text-xs text-pp-mute">{t('studio.split.missing')}</span>
                  )}
                </li>
              ))}
            </ul>
          </Panel>
          )}
        </>
      )}
    </div>
  );
};

const Skeleton: React.FC<{ lines?: number }> = ({ lines = 3 }) => (
  <div className="animate-pulse space-y-2" aria-hidden>
    {Array.from({ length: lines }, (_, i) => (
      <div key={i} className={cx('h-3 rounded bg-pp-line/60', i === 0 ? 'w-3/4' : 'w-full')} />
    ))}
  </div>
);

const VoiceColumn: React.FC<{ persona: 'casual' | 'tactical'; card: OverlayCard | null; loading: boolean }> = ({ persona, card, loading }) => {
  const { t } = useI18n();
  const Icon = persona === 'casual' ? Heart : BarChart3;
  return (
    <section
      aria-label={t(`persona.${persona}`)}
      aria-busy={loading}
      className={cx(
        'rounded-2xl border p-4 shadow-lg shadow-black/30',
        persona === 'casual' ? 'border-pp-line border-t-4 border-t-pp-pulse bg-pp-panel' : 'border-pp-line border-t-4 border-t-pp-signal bg-pp-panel',
      )}
    >
      <header className="mb-3 flex items-center justify-between gap-2">
        <h2 className={cx('flex items-center gap-2 font-display text-lg font-bold uppercase tracking-wider', persona === 'casual' ? 'text-pp-pulseSoft' : 'text-pp-signal')}>
          <Icon className="h-5 w-5" aria-hidden />
          {t(`persona.${persona}`)}
        </h2>
        {card && <ProducedBadge card={card} />}
      </header>
      {loading ? (
        <>
          <span className="sr-only">{t('common.loading')}</span>
          <Skeleton lines={4} />
        </>
      ) : !card ? (
        <p className="text-sm text-pp-mute">{t('studio.split.missing')}</p>
      ) : (
        <div dir={card.rtl ? 'rtl' : 'ltr'} lang={textLanguage(card)}>
          <h3 className="font-display text-xl font-bold leading-tight text-white">{card.headline}</h3>
          {card.body && <p className="mt-2 text-sm leading-relaxed text-slate-200">{card.body}</p>}
          {card.why && (
            <div className="mt-3 rounded-lg border border-pp-line/70 bg-pp-deep/80 p-2.5">
              <span className="mb-0.5 block text-[10px] font-bold uppercase tracking-wider text-pp-pulseSoft">{t('studio.feed.why')}</span>
              <p className="text-xs leading-relaxed text-slate-200">{card.why}</p>
            </div>
          )}
          {card.tactical_tag && (
            <span className="mt-3 inline-block rounded-md border border-pp-line bg-pp-night px-2 py-0.5 text-[11px] font-semibold text-pp-mute">
              <bdi>#{tagLabel(t, card.tactical_tag)}</bdi>
            </span>
          )}
          {persona === 'tactical' && card.evidence.length > 0 && (
            <div className="mt-3">
              <h4 className="mb-1 text-[10px] font-bold uppercase tracking-wider text-pp-mute">{t('evidence.title')}</h4>
              <EvidenceTable evidence={card.evidence} />
            </div>
          )}
        </div>
      )}
    </section>
  );
};
