import React, { useEffect, useState } from 'react';
import { Activity, Eye, EyeOff, Gavel, Radio } from 'lucide-react';
import type { Cue, Evidence, OverlayCard, Slot, Teams } from '../api/contract';
import { factLabel, factValue } from '../lib/facts';
import { useI18n, type I18n } from '../i18n';
import { activeCards } from '../state/matchStore';
import { teamById } from '../lib/teams';
import { isTranslationReason, textLanguage } from '../lib/languages';
import { translationReasonText } from './LanguagePicker';
import type { ViewProps } from '../views/types';
import { Badge, cx } from './ui';
import { Pitch2D } from './Pitch2D';
import { ReplayCard } from './ReplayCard';
import { ScoreValue } from './CatchUp';
import { inkOn } from '../lib/contrast';

type Layer = 'scorebug' | Slot;
const LAYERS: Layer[] = ['scorebug', 'lower_third', 'side_panel', 'pitch_tag', 'metric_alert', 'full_screen'];

export { factLabel, factValue } from '../lib/facts';

const unitLabel = (t: I18n['t'], unit: string | null) => {
  if (!unit) return '';
  if (unit === 'km/h') return t('unit.kmh');
  if (unit === 'm') return t('unit.m');
  if (unit === 'km') return t('unit.km');
  return unit;
};

export const EvidenceChip: React.FC<{ evidence: Evidence; className?: string }> = ({ evidence, className }) => {
  const i18n = useI18n();
  const unit = unitLabel(i18n.t, evidence.unit);
  return (
    <span
      className={cx(
        'inline-flex max-w-full items-center gap-1 truncate rounded-md border border-pp-signal/40 bg-pp-signal/10 px-1.5 py-0.5 font-semibold text-pp-signal',
        className,
      )}
      title={evidence.source_event_id ? i18n.t('evidence.source', { id: evidence.source_event_id }) : undefined}
    >
      <span className="truncate">{factLabel(i18n.t, evidence.label)}</span>
      <span className="ltr-nums text-white">
        {factValue(i18n, evidence.value)}
        {unit && (unit === 'x' ? 'x' : unit === '0-100' ? '/100' : ` ${unit}`)}
      </span>
    </span>
  );
};

const SourceLine: React.FC<{ card: OverlayCard }> = ({ card }) => {
  const { t } = useI18n();
  return (
    <p className="truncate text-[clamp(8px,1vw,11px)] text-pp-mute">
      {t('broadcast.source', { by: t(`broadcast.by.${card.produced_by}`) })}
      {card.fallback_reason && !isTranslationReason(card.fallback_reason) && (
        <> · {t('broadcast.fallback', { reason: card.fallback_reason })}</>
      )}
      {card.translated_by === 'azure_ai_translator' && (
        <span data-testid="translation-tag" className="text-pp-signal"> · {t('world.translated')}</span>
      )}
      {textLanguage(card) !== card.language && (
        <span data-testid="translation-fallback" className="text-pp-gold">
          {' · '}
          {t('world.inEnglishWhy', { reason: translationReasonText(t, card.fallback_reason) })}
        </span>
      )}
    </p>
  );
};

// Accent for a card: the favourite team's colour when the card is about their side.
function favouriteAccent(card: OverlayCard, teams: Teams | null, favourite: string | null) {
  if (!card.favourite_side) return null;
  return teamById(teams, favourite)?.primary_color ?? null;
}

const LowerThird: React.FC<{ card: OverlayCard; teams: Teams | null; favourite: string | null }> = ({ card, teams, favourite }) => {
  const { t } = useI18n();
  const accent = favouriteAccent(card, teams, favourite);
  const first = card.evidence[0];
  return (
    <div
      data-testid="lower-third"
      lang={textLanguage(card)}
      className="pointer-events-auto w-full max-w-3xl animate-slide-up rounded-xl border border-white/10 border-s-4 bg-pp-deep/90 px-[clamp(8px,2vw,18px)] py-[clamp(4px,1.2vw,12px)] shadow-2xl backdrop-blur"
      style={{ borderInlineStartColor: accent ?? '#ff3b2f', boxShadow: accent ? `0 0 0 1px ${accent}55, 0 20px 40px rgba(0,0,0,.5)` : undefined }}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        <Badge tone="pulse" className="text-[clamp(8px,1vw,11px)] uppercase tracking-wider">
          {t(`kind.${card.kind}`)}
        </Badge>
        {accent && (
          <span className="rounded-full px-1.5 py-0.5 text-[clamp(8px,1vw,11px)] font-bold" style={{ background: accent, color: inkOn(accent) }}>
            {t('broadcast.yourTeam')}
          </span>
        )}
        {first && <EvidenceChip evidence={first} className="text-[clamp(8px,1vw,11px)]" />}
      </div>
      <h3 className="mt-1 font-display text-[clamp(12px,2.2vw,24px)] font-bold uppercase leading-tight tracking-wide text-white">
        {card.headline}
      </h3>
      <p className="mt-0.5 line-clamp-2 text-[clamp(9px,1.3vw,14px)] leading-snug text-slate-200 max-sm:hidden">{card.body}</p>
      <SourceLine card={card} />
    </div>
  );
};

const SideCard: React.FC<{ card: OverlayCard; teams: Teams | null; favourite: string | null }> = ({ card, teams, favourite }) => {
  const { t } = useI18n();
  const accent = favouriteAccent(card, teams, favourite);
  return (
    <div
      lang={textLanguage(card)}
      className="animate-fade-in rounded-lg border border-white/10 border-s-4 bg-pp-deep/85 p-[clamp(6px,1vw,10px)] shadow-xl backdrop-blur"
      style={{ borderInlineStartColor: accent ?? '#ffd400' }}
    >
      <p className="text-[clamp(8px,0.9vw,10px)] font-bold uppercase tracking-wider text-pp-signal">{t(`kind.${card.kind}`)}</p>
      <p className="font-display text-[clamp(10px,1.3vw,14px)] font-semibold leading-tight text-white">{card.headline}</p>
      <p className="mt-0.5 line-clamp-2 text-[clamp(8px,1vw,11px)] text-slate-300">{card.body}</p>
      {card.evidence[0] && <EvidenceChip evidence={card.evidence[0]} className="mt-1 text-[clamp(8px,0.9vw,10px)]" />}
      <SourceLine card={card} />
    </div>
  );
};

/** The supersede card for a VAR decision: says plainly that the goal no longer counts. */
export const CorrectionCard: React.FC<{ card: OverlayCard; reason?: string | null }> = ({ card, reason }) => {
  const { t } = useI18n();
  const reasonKey = reason ? `cue.reason.${reason}` : '';
  const reasonText = reasonKey && t(reasonKey) !== reasonKey ? t(reasonKey) : null;
  return (
    <div
      data-testid="correction-card"
      role="status"
      lang={textLanguage(card)}
      className="pointer-events-auto w-full max-w-3xl animate-slide-up border-2 border-pp-pulse bg-pp-deep/95 px-[clamp(10px,2.4vw,22px)] py-[clamp(8px,1.6vw,16px)] shadow-2xl"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex animate-stamp-in items-center gap-1.5 border-2 border-pp-pulse bg-pp-pulseFill px-2 py-0.5 font-display text-[clamp(12px,2vw,22px)] font-extrabold uppercase tracking-broadcast text-white">
          <Gavel className="h-[1em] w-[1em]" aria-hidden />
          {t('cue.ruledOut')}
        </span>
        {reasonText && (
          <span className="font-display text-[clamp(11px,1.6vw,18px)] font-bold uppercase tracking-wide text-pp-pulseSoft">{reasonText}</span>
        )}
      </div>
      <h3 className="mt-2 font-display text-[clamp(12px,2.2vw,24px)] font-bold uppercase leading-tight tracking-wide text-white">
        {card.headline}
      </h3>
      <p className="mt-0.5 line-clamp-2 text-[clamp(9px,1.3vw,14px)] leading-snug text-slate-200 max-sm:hidden">{card.body}</p>
      <div className="mt-1 flex flex-wrap gap-1">
        {card.evidence.slice(0, 3).map((e, i) => (
            <EvidenceChip key={`${e.label}-${i}`} evidence={e} className="text-[clamp(8px,1vw,11px)]" />
          ))}
      </div>
      <SourceLine card={card} />
    </div>
  );
};

/** A card whose moment was just ruled out: it greys and slides away once, then stays hidden. */
const ExitingCard: React.FC<{ card: OverlayCard; teams: Teams | null; favourite: string | null }> = ({ card, teams, favourite }) => {
  const { t } = useI18n();
  return (
    <div data-testid="retracting-card" aria-hidden className="pointer-events-none relative w-full max-w-3xl animate-retract-out">
      <LowerThird card={card} teams={teams} favourite={favourite} />
      <span className="absolute end-3 top-2 -rotate-6 border-2 border-pp-pulse px-1.5 font-display text-[clamp(10px,1.4vw,16px)] font-extrabold uppercase text-pp-pulse">
        {t('cue.ruledOutShort')}
      </span>
    </div>
  );
};

const CueLog: React.FC<{ cues: Cue[] }> = ({ cues }) => {
  const { t } = useI18n();
  const recent = cues.slice(-8).reverse();
  return (
    <section data-testid="cue-log" className="rounded-2xl border border-pp-line/70 bg-pp-panel/80 p-4">
      <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-slate-200">{t('cue.panel')}</h3>
      <p className="mb-2 text-xs text-pp-mute">{t('cue.panelHint')}</p>
      {recent.length === 0 ? (
        <p className="text-xs text-pp-mute">{t('cue.empty')}</p>
      ) : (
        <ol className="space-y-1 text-xs">
          {recent.map((c) => (
            <li key={c.cue_id} className="flex min-w-0 items-center gap-2">
              <span className="ltr-nums shrink-0 text-pp-mute">#{c.seq}</span>
              <span className="ltr-nums shrink-0 font-bold text-pp-signal">{c.start.match_clock}</span>
              <span
                className={cx(
                  'shrink-0 px-1 font-bold uppercase',
                  c.op === 'retract' || c.op === 'supersede' ? 'bg-pp-pulseFill text-white' : 'bg-pp-raised text-slate-200',
                )}
              >
                {t(`cue.op.${c.op}`)}
              </span>
              <span className="shrink-0 text-pp-mute">{c.layer === 'all' ? '*' : t(`broadcast.slot.${c.layer}`) === `broadcast.slot.${c.layer}` ? c.layer.replace(/_/g, ' ') : t(`broadcast.slot.${c.layer}`)}</span>
              <span className="min-w-0 truncate text-slate-300">{c.text?.headline ?? ''}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
};

const Scorebug: React.FC<ViewProps & { corrected?: boolean }> = ({ match, corrected }) => {
  const { t, num } = useI18n();
  const { teams, score, clock, period, playback, controlChaos } = match;
  if (!teams) return null;
  const homePct = controlChaos?.home_control_pct ?? null;
  const awayPct = controlChaos?.away_control_pct ?? null;
  const tempoKey = controlChaos ? `tempo.${controlChaos.current_tempo}` : '';
  const tempo = controlChaos ? (t(tempoKey) === tempoKey ? controlChaos.current_tempo : t(tempoKey)) : '';
  return (
    <div data-testid="scorebug" className="pointer-events-auto overflow-hidden rounded-lg border border-white/15 bg-pp-deep/90 shadow-2xl backdrop-blur">
      <div className="flex items-stretch font-display text-[clamp(11px,1.8vw,18px)] font-bold text-white">
        <span className="flex items-center gap-1.5 px-[clamp(6px,1vw,12px)] py-1">
          <span aria-hidden className="h-[1.1em] w-1.5 rounded-sm" style={{ background: teams.home.primary_color }} />
          {teams.home.short_name}
        </span>
        <span
          key={corrected ? 'corrected' : 'live'}
          className={cx('ltr-nums flex items-center bg-pp-raised px-[clamp(6px,1vw,12px)] text-[1.15em]', corrected && 'animate-score-flash')}
        >
          <ScoreValue value={score.home} /> - <ScoreValue value={score.away} />
        </span>
        {corrected && (
          <span
            data-testid="scorebug-var"
            title={t('cue.scoreReverted')}
            className="flex items-center bg-pp-pulseFill px-1.5 text-[0.7em] font-extrabold uppercase tracking-wider"
          >
            {t('cue.var')}
            <span className="sr-only"> · {t('cue.scoreReverted')}</span>
          </span>
        )}
        <span className="flex items-center gap-1.5 px-[clamp(6px,1vw,12px)] py-1">
          {teams.away.short_name}
          <span aria-hidden className="h-[1.1em] w-1.5 rounded-sm" style={{ background: teams.away.primary_color }} />
        </span>
        <span className="flex flex-col items-center justify-center bg-pp-pulse/90 px-[clamp(6px,1vw,12px)] leading-none">
          <span className="ltr-nums text-[0.9em]">{playback.ended ? '' : clock}</span>
          <span className="text-[clamp(7px,0.8vw,10px)] font-semibold uppercase tracking-wider">
            {playback.ended ? t('play.ended') : t(period >= 2 ? 'broadcast.half2' : 'broadcast.half1')}
          </span>
        </span>
      </div>
      {homePct != null && awayPct != null && (
        <div
          className="flex items-center gap-1.5 border-t border-white/10 bg-black/60 px-2 py-0.5 text-[clamp(7px,0.85vw,10px)] text-pp-mute"
          aria-label={t('broadcast.controlSplit', {
            home: teams.home.short_name,
            away: teams.away.short_name,
            homePct: num(homePct),
            awayPct: num(awayPct),
            tempo,
          })}
        >
          <span className="font-semibold uppercase">{t('broadcast.control')}</span>
          <span className="ltr-nums text-white">{num(homePct)}%</span>
          <span dir="ltr" className="flex h-1.5 min-w-[40px] flex-1 overflow-hidden rounded-full bg-pp-line">
            <span style={{ width: `${homePct}%`, background: teams.home.primary_color }} />
            <span style={{ width: `${awayPct}%`, background: teams.away.primary_color }} />
          </span>
          <span className="ltr-nums text-white">{num(awayPct)}%</span>
          {tempo && <span className="truncate font-semibold text-pp-signal">{tempo}</span>}
        </div>
      )}
    </div>
  );
};

export const BroadcastOverlay: React.FC<ViewProps & { capture?: boolean }> = ({ match, actions, capture = false }) => {
  const { t } = useI18n();
  useEffect(() => {
    if (!capture) return;
    document.documentElement.classList.add('pp-capture');
    return () => document.documentElement.classList.remove('pp-capture');
  }, [capture]);
  const [shown, setShown] = useState<Record<Layer, boolean>>({
    scorebug: true,
    lower_third: true,
    side_panel: true,
    pitch_tag: true,
    metric_alert: true,
    full_screen: true,
  });
  const { teams, cards, playback, profile, crew } = match;
  const clockS = playback.clock_s;
  const ruledOut = match.cue.ruledOut;
  const bySlot = (slot: Slot) => activeCards(cards, clockS, slot, ruledOut);
  const lower = bySlot('lower_third');
  const side = bySlot('side_panel').slice(0, 2);
  const alerts = bySlot('metric_alert');
  const tags = bySlot('pitch_tag');
  const full = bySlot('full_screen');
  const replay = full.find((c) => c.replay) ?? null;
  const fullPlain = replay ? null : (full[0] ?? null);
  // VAR: cards that were on screen when their moment was ruled out leave with an animation.
  const exiting = activeCards(match.cue.exiting, clockS);
  const corrected = activeCards(cards, clockS, undefined, ruledOut).some((c) => c.kind === 'correction');
  const favourite = profile.favourite_team;
  const counts: Record<Layer, number> = {
    scorebug: teams ? 1 : 0,
    lower_third: lower.length,
    side_panel: side.length,
    pitch_tag: tags.length,
    metric_alert: alerts.length,
    full_screen: full.length,
  };
  const nothingOnAir = !lower.length && !side.length && !alerts.length && !tags.length && !full.length;

  const stage = (
      <section
        aria-label={t('broadcast.stageLabel')}
        data-testid="overlay-stage"
        className={cx(
          'relative w-full overflow-hidden',
          capture
            ? 'h-screen bg-transparent'
            : 'aspect-video rounded-2xl border border-pp-line bg-pp-turf shadow-2xl shadow-black/50',
        )}
      >
        {/* Backdrop: the synthetic match stands in for the video feed (left out when captured over real video). */}
        {!capture && (
        <div dir="ltr" aria-hidden className="absolute inset-0 flex items-center justify-center opacity-60">
          <div className="aspect-[105/68] h-full max-w-full">
            <Pitch2D
              teams={teams}
              event={match.lastEvent}
              recentEvents={match.events.slice(-6)}
              positions={match.positions}
              showTags={false}
              pitchTags={shown.pitch_tag ? tags : []}
              className="h-full w-full"
            />
          </div>
        </div>
        )}
        {!capture && (
          <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/50 via-transparent to-black/70" />
        )}

        {/* Corner badges */}
        {!capture && (
        <div className="absolute end-[2%] top-[3%] flex flex-col items-end gap-1">
          <span
            title={t('broadcast.feedHint')}
            className="flex items-center gap-1 rounded-md bg-black/70 px-1.5 py-0.5 text-[clamp(8px,1vw,11px)] font-semibold text-slate-200"
          >
            <Radio className="h-3 w-3 text-pp-pulse" aria-hidden />
            {t('broadcast.feed')}
          </span>
          {crew && (
            <span
              title={crew.mode === 'template' ? t('crew.templateHint') : undefined}
              className={cx(
                'rounded-md bg-black/70 px-1.5 py-0.5 text-[clamp(8px,1vw,11px)] font-semibold',
                crew.mode === 'ai' ? 'text-pp-signal' : 'text-pp-mute',
              )}
            >
              {t(crew.mode === 'ai' ? 'crew.ai' : 'crew.template')}
            </span>
          )}
        </div>
        )}

        {shown.scorebug && (
          <div className="absolute start-[2%] top-[3%] max-w-[62%]">
            <Scorebug match={match} actions={actions} corrected={corrected} />
          </div>
        )}

        {shown.side_panel && side.length > 0 && (
          <div className="absolute end-[2%] top-[22%] hidden w-[28%] flex-col gap-2 sm:flex">
            {side.map((c) => (
              <SideCard key={c.card_id} card={c} teams={teams} favourite={favourite} />
            ))}
          </div>
        )}

        {shown.lower_third && lower[0] && (
          <div
            className={cx(
              'absolute inset-x-[3%] flex justify-center',
              shown.metric_alert && alerts.length ? 'bottom-[13%]' : 'bottom-[4%]',
            )}
          >
            <LowerThird key={lower[0].card_id} card={lower[0]} teams={teams} favourite={favourite} />
          </div>
        )}

        {/* Phone: the side panel collapses to its top card along the bottom when the lower third is free. */}
        {shown.side_panel && side[0] && !(shown.lower_third && lower[0]) && (
          <div
            className={cx(
              'absolute inset-x-[3%] flex justify-center sm:hidden',
              shown.metric_alert && alerts.length ? 'bottom-[13%]' : 'bottom-[4%]',
            )}
          >
            <div className="w-full">
              <SideCard key={side[0].card_id} card={side[0]} teams={teams} favourite={favourite} />
            </div>
          </div>
        )}

        {shown.metric_alert && alerts.length > 0 && (
          <div
            data-testid="metric-ticker"
            className="absolute inset-x-0 bottom-0 flex h-[10%] min-h-[18px] items-center gap-3 overflow-hidden bg-black/80 px-[2%] text-[clamp(9px,1.2vw,13px)]"
          >
            <span className="flex shrink-0 items-center gap-1 rounded bg-pp-pulseFill px-1.5 font-bold uppercase text-white">
              <Activity className="h-3 w-3" aria-hidden />
              {t('broadcast.alert')}
            </span>
            {alerts.slice(0, 3).map((c) => (
              <span key={c.card_id} lang={textLanguage(c)} className="flex min-w-0 items-center gap-1.5 truncate text-white">
                <span className="truncate font-semibold">{c.headline}</span>
                {c.evidence[0] && <EvidenceChip evidence={c.evidence[0]} className="hidden text-[0.85em] md:inline-flex" />}
              </span>
            ))}
          </div>
        )}

        {shown.full_screen && (replay || fullPlain) && (
          <div className="absolute inset-0 z-10 flex animate-fade-in items-center justify-center bg-black/75 p-[3%]">
            {replay ? (
              <div className="max-h-full w-full max-w-[85%] overflow-hidden">
                <ReplayCard card={replay} teams={teams} compact />
                <div className="mt-1 text-center">
                  <SourceLine card={replay} />
                </div>
              </div>
            ) : (
              fullPlain && (
                <div className="w-full max-w-[70%]">
                  {fullPlain.kind === 'correction' ? (
                    <CorrectionCard
                      card={fullPlain}
                      reason={[...match.cue.onAir, ...match.cue.log].find((c) => c.moment_id === fullPlain.moment_id && c.reason)?.reason ?? null}
                    />
                  ) : (
                    <LowerThird card={fullPlain} teams={teams} favourite={favourite} />
                  )}
                </div>
              )
            )}
          </div>
        )}

        {exiting.length > 0 && (
          <div className="pointer-events-none absolute inset-x-[15%] bottom-[18%] z-20 flex flex-col items-center gap-2">
            {exiting.map((c) => (
              <ExitingCard key={`exit-${c.card_id}`} card={c} teams={teams} favourite={favourite} />
            ))}
          </div>
        )}

        {nothingOnAir && !playback.ended && !capture && (
          <p className="absolute inset-x-[10%] bottom-[5%] text-center text-[clamp(9px,1.2vw,13px)] text-slate-300/80">
            {match.events.length || match.playback.clock_s > 0 ? t('broadcast.idle') : t('common.waiting')}
          </p>
        )}
      </section>
  );

  if (capture) return stage;

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4">
      <div>
        <h2 className="font-display text-lg font-bold uppercase tracking-wide text-white">{t('broadcast.title')}</h2>
        <p className="text-sm text-pp-mute">{t('broadcast.subtitle')}</p>
      </div>

      {stage}

      <section className="rounded-2xl border border-pp-line/70 bg-pp-panel/80 p-4">
        <header className="mb-1 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-slate-200">{t('broadcast.producer')}</h3>
        </header>
        <p className="mb-3 text-xs text-pp-mute">{t('broadcast.producerHint')}</p>
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {LAYERS.map((layer) => {
            const on = shown[layer];
            const name = t(`broadcast.slot.${layer}`);
            return (
              <li key={layer}>
                <button
                  type="button"
                  aria-pressed={on}
                  aria-label={t('broadcast.layer.toggle', { layer: name })}
                  onClick={() => setShown((s) => ({ ...s, [layer]: !s[layer] }))}
                  className={cx(
                    'flex min-h-[44px] w-full items-start gap-2 rounded-xl border p-2.5 text-start transition',
                    on ? 'border-pp-signal/50 bg-pp-deep' : 'border-pp-line bg-pp-night/60 opacity-70',
                  )}
                >
                  {on ? (
                    <Eye className="mt-0.5 h-4 w-4 shrink-0 text-pp-signal" aria-hidden />
                  ) : (
                    <EyeOff className="mt-0.5 h-4 w-4 shrink-0 text-pp-mute" aria-hidden />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-x-2 text-sm font-semibold text-white">
                      {name}
                      <span className={cx('text-[11px] font-bold uppercase', on ? 'text-pp-signal' : 'text-pp-mute')}>
                        {t(on ? 'broadcast.layer.on' : 'broadcast.layer.off')}
                      </span>
                      {layer !== 'scorebug' && counts[layer] > 0 && (
                        <span className="rounded-full bg-pp-pulse/20 px-1.5 text-[11px] text-pp-pulseSoft">
                          {t('broadcast.activeCount', { n: counts[layer] })}
                        </span>
                      )}
                    </span>
                    <span className="block text-xs text-pp-mute">{t(`broadcast.slot.${layer}Hint`)}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      <CueLog cues={match.cue.log} />
    </div>
  );
};
