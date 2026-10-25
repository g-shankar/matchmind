// "Choose a match": one floodlit card per recorded synthetic match. Each card carries the
// clubs' colour bars, a storyline tag derived from the goals and VAR reviews, the goal
// timeline and a mini pitch that draws the real ball path of the match's key moment.
// Only the match this session plays can be watched; the rest say so plainly.
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Play, X } from 'lucide-react';
import { useI18n } from '../i18n';
import { cx } from './ui';
import { inkOn } from '../lib/contrast';
import {
  PITCH_H,
  PITCH_W,
  ballTimeline,
  isPlayable,
  loadPreviews,
  minuteLabel,
  type MatchPreview,
} from '../lib/previews';

const SPOILER_KEY = 'pp.picker.hideResults';
const LEAVE_MS = 520;

const media = (q: string) => {
  try {
    return window.matchMedia(q).matches;
  } catch {
    return false;
  }
};

const readHide = () => {
  try {
    return window.localStorage.getItem(SPOILER_KEY) === '1';
  } catch {
    return false;
  }
};

const writeHide = (v: boolean) => {
  try {
    window.localStorage.setItem(SPOILER_KEY, v ? '1' : '0');
  } catch {
    /* private window: the choice lasts for this visit only */
  }
};

export interface MatchPickerProps {
  open: boolean;
  /** The match id the session plays (null until the first snapshot). */
  sessionMatchId: string | null;
  onClose: () => void;
  onWatch: (matchId: string) => void;
  /** Tests pass previews directly instead of fetching them. */
  previews?: MatchPreview[];
}

export const MatchPicker: React.FC<MatchPickerProps> = ({ open, sessionMatchId, onClose, onWatch, previews }) => {
  const { t, dir } = useI18n();
  const [list, setList] = useState<MatchPreview[] | null>(previews ?? null);
  const [failed, setFailed] = useState(false);
  const [hide, setHide] = useState(readHide);
  const [leaving, setLeaving] = useState<string | null>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const reduced = useMemo(() => media('(prefers-reduced-motion: reduce)'), []);
  const touch = useMemo(() => media('(hover: none)'), []);

  useEffect(() => {
    if (!open || list || previews) return;
    let live = true;
    loadPreviews()
      .then((p) => live && setList(p))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [open, list, previews]);

  useEffect(() => {
    if (!open) return;
    setLeaving(null);
    titleRef.current?.focus();
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  const watch = (id: string) => {
    if (leaving) return;
    setLeaving(id);
    window.setTimeout(() => onWatch(id), reduced ? 0 : LEAVE_MS);
  };

  return (
    <div
      dir={dir}
      role="dialog"
      aria-modal="true"
      aria-labelledby="picker-title"
      data-testid="match-picker"
      className={cx('pp-picker fixed inset-0 z-[60] overflow-y-auto bg-pp-night', leaving && 'pp-picker-leave')}
    >
      <div className="pp-floodlights pointer-events-none fixed inset-0" aria-hidden />
      <div className="relative mx-auto w-full max-w-7xl px-4 pb-12 pt-5 sm:px-6 sm:pt-8">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className="pp-pick-rise font-display text-xs font-bold uppercase tracking-broadcast text-pp-signal sm:text-sm">{t('picker.kicker')}</p>
            <h2
              id="picker-title"
              ref={titleRef}
              tabIndex={-1}
              className="pp-pick-title mt-1 font-display text-4xl font-extrabold uppercase italic leading-[0.9] tracking-broadcast text-pp-chalk outline-none sm:text-6xl"
            >
              {t('picker.title')}
            </h2>
            <div className="pp-pick-bar mt-3 h-1.5 w-40 bg-pp-pulse sm:w-64" aria-hidden />
            <p className="pp-pick-rise mt-3 max-w-2xl text-sm text-pp-mute sm:text-base">{t('picker.intro')}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('picker.close')}
            title={t('picker.close')}
            data-testid="picker-close"
            className="flex h-11 w-11 shrink-0 items-center justify-center border border-pp-line bg-pp-panel text-pp-chalk hover:border-pp-pulse"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>

        <label className="mt-4 inline-flex min-h-[44px] cursor-pointer items-center gap-2 text-sm text-pp-chalk">
          <input
            type="checkbox"
            checked={hide}
            onChange={(e) => {
              setHide(e.target.checked);
              writeHide(e.target.checked);
            }}
            className="h-5 w-5 accent-pp-signal"
            data-testid="picker-hide"
          />
          {t('picker.spoilers')}
        </label>

        {failed && (
          <p role="alert" className="mt-6 border border-pp-pulse/50 bg-pp-panel px-4 py-3 text-sm text-pp-chalk">
            {t('picker.failed')}
          </p>
        )}

        {!list && !failed && (
          <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-busy="true" aria-label={t('picker.loading')}>
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-80 animate-pulse border border-pp-line bg-pp-panel" />
            ))}
          </div>
        )}

        {list && (
          <ul className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {list.map((p, i) => (
              <MatchCard
                key={p.match_id}
                preview={p}
                index={i}
                playable={isPlayable(p, sessionMatchId)}
                hide={hide}
                autoPlay={touch}
                reduced={reduced}
                chosen={leaving === p.match_id}
                onWatch={() => watch(p.match_id)}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

interface CardProps {
  preview: MatchPreview;
  index: number;
  playable: boolean;
  hide: boolean;
  autoPlay: boolean;
  reduced: boolean;
  chosen: boolean;
  onWatch: () => void;
}

const MatchCard: React.FC<CardProps> = ({ preview: p, index, playable, hide, autoPlay, reduced, chosen, onWatch }) => {
  const { t, num } = useI18n();
  const [hover, setHover] = useState(false);
  const active = autoPlay || hover;
  const km = p.key_moment;
  const scorer = km ? (km.team === p.home.team_id ? p.home : p.away) : null;
  const titleId = `pick-${p.match_id}`;

  return (
    <li
      className={cx('pp-pick-card relative', chosen && 'pp-pick-chosen')}
      style={{ animationDelay: `${120 + index * 90}ms` }}
      data-testid={`pick-${p.match_id}`}
      data-active={active ? 'true' : 'false'}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocus={() => setHover(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setHover(false);
      }}
    >
      <article aria-labelledby={titleId} className={cx('pp-pick-cut flex h-full flex-col border bg-pp-panel', playable ? 'border-pp-signal/70' : 'border-pp-line')}>
        {/* Club colour bars, cut on a slant where they meet. */}
        <div className="flex h-2" aria-hidden>
          <span className="pp-bar-home flex-1" style={{ background: p.home.primary_color }} />
          <span className="pp-bar-away flex-1" style={{ background: p.away.primary_color }} />
        </div>
        <div className="flex items-center justify-between gap-2 px-4 pt-3">
          <span className="font-display text-[11px] font-bold uppercase tracking-broadcast text-pp-mute ltr-nums">{p.match_id}</span>
          {playable ? (
            <span className="inline-flex items-center gap-1.5 bg-pp-pulseFill px-2 py-0.5 font-display text-xs font-extrabold uppercase italic tracking-broadcast text-white">
              <span className="h-1.5 w-1.5 animate-heartbeat rounded-full bg-white" aria-hidden />
              {t('picker.onAir')}
            </span>
          ) : (
            <span className="border border-pp-line bg-pp-deep px-2 py-0.5 font-display text-xs font-bold uppercase tracking-broadcast text-pp-mute">
              {t('picker.previewOnly')}
            </span>
          )}
        </div>

        <h3 id={titleId} className="px-4 pt-2">
          <span className="sr-only">
            {hide
              ? `${p.home.name} – ${p.away.name}`
              : t('picker.score', { home: p.home.name, homeGoals: p.score.home, away: p.away.name, awayGoals: p.score.away })}
          </span>
          <span aria-hidden className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
            <ClubName club={p.home} align="start" />
            <span className="flex items-stretch font-display text-2xl font-extrabold leading-none tabular-nums">
              <span className="bg-pp-raised px-2 py-1 text-pp-chalk">{hide ? '–' : p.score.home}</span>
              <span className="bg-pp-pulseFill px-2 py-1 text-white">{hide ? '–' : p.score.away}</span>
            </span>
            <ClubName club={p.away} align="end" />
          </span>
        </h3>

        <div className="flex min-h-[28px] flex-wrap gap-1.5 px-4 pt-3">
          {!hide &&
            p.tags.slice(0, 3).map((tag, i) => (
              <span
                key={tag}
                className={cx(
                  'pp-slant px-2 pe-4 py-0.5 font-display text-xs font-extrabold uppercase italic tracking-broadcast',
                  i === 0 ? 'bg-pp-signal text-pp-night' : 'bg-pp-raised text-pp-chalk',
                )}
              >
                {t(`picker.tag.${tag}`)}
              </span>
            ))}
        </div>

        <div className="px-4 pt-3">
          <MiniPitch preview={p} active={active && !hide} reduced={reduced} hide={hide} focusable={!playable} />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 px-4 pt-2 text-xs text-pp-mute">
          {!hide && km && scorer ? (
            <>
              <span className="font-display font-bold uppercase tracking-broadcast text-pp-chalk">
                {t('picker.keyMoment', { minute: minuteLabel(km.minute, km.period) })}
              </span>
              {km.chance_quality !== null && <span className="ltr-nums">{t('picker.chance', { value: num(km.chance_quality, 2) })}</span>}
            </>
          ) : (
            <span>{t('picker.events', { count: num(p.events) })}</span>
          )}
        </div>

        {!hide && <GoalStrip preview={p} />}

        <div className="mt-auto px-4 pb-4 pt-4">
          {playable ? (
            <button
              type="button"
              onClick={onWatch}
              data-testid="picker-watch"
              className="pp-pick-cta flex h-12 w-full items-center justify-center gap-2 bg-pp-pulseFill font-display text-lg font-extrabold uppercase italic tracking-broadcast text-white hover:bg-pp-pulse focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pp-signal"
            >
              <Play className="h-4 w-4 rtl:-scale-x-100" aria-hidden />
              {t('picker.watch')}
            </button>
          ) : (
            <p className="flex h-12 w-full items-center justify-center border border-dashed border-pp-line font-display text-sm font-bold uppercase tracking-broadcast text-pp-mute">
              {t('picker.comingSoon')}
            </p>
          )}
        </div>
      </article>
    </li>
  );
};

const ClubName: React.FC<{ club: MatchPreview['home']; align: 'start' | 'end' }> = ({ club, align }) => (
  <span className={cx('flex min-w-0 flex-col', align === 'end' ? 'items-end text-end' : 'items-start text-start')}>
    <span
      className="px-1.5 font-display text-sm font-extrabold uppercase tracking-broadcast"
      style={{ background: club.primary_color, color: inkOn(club.primary_color) }}
    >
      {club.short_name}
    </span>
    <span className="mt-1 truncate font-display text-base font-bold uppercase leading-tight text-pp-chalk sm:text-lg">{club.name}</span>
  </span>
);

/** Goals along the match: one tick per goal at its minute, in the scoring club's colour. */
const GoalStrip: React.FC<{ preview: MatchPreview }> = ({ preview: p }) => {
  const { t } = useI18n();
  if (!p.goals.length) return null;
  const end = Math.max(95, ...p.goals.map((g) => g.minute));
  return (
    <div className="px-4 pt-3">
      <p className="sr-only">
        {t('picker.goals')}: {p.goals.map((g) => `${g.team === p.home.team_id ? p.home.short_name : p.away.short_name} ${minuteLabel(g.minute, g.period)}`).join(', ')}
      </p>
      <div className="relative h-4" aria-hidden>
        <span className="absolute inset-x-0 top-1/2 h-px bg-pp-line" />
        <span className="absolute top-0 h-full w-px bg-pp-mute/50" style={{ insetInlineStart: `${(45 / end) * 100}%` }} />
        {p.goals.map((g, i) => (
          <span
            key={i}
            className="absolute top-0 h-4 w-1.5 -translate-x-1/2 rtl:translate-x-1/2"
            style={{ insetInlineStart: `${(g.minute / end) * 100}%`, background: g.team === p.home.team_id ? p.home.primary_color : p.away.primary_color }}
            title={minuteLabel(g.minute, g.period)}
          />
        ))}
      </div>
    </div>
  );
};

const len = (s: { x1: number; y1: number; x2: number; y2: number }) => Math.max(0.1, Math.hypot(s.x2 - s.x1, s.y2 - s.y1));
const STEP_S = 0.85;
const HOLD_S = 1.6;
const DRAW_SHARE = 0.78;

/** The ball path of the key moment, drawn in on a loop: real coordinates, metres on a 105 x 68 pitch. */
export const MiniPitch: React.FC<{ preview: MatchPreview; active: boolean; reduced: boolean; hide: boolean; focusable: boolean }> = ({
  preview: p,
  active,
  reduced,
  hide,
  focusable,
}) => {
  const { t } = useI18n();
  const km = p.key_moment;
  const id = p.match_id.replace(/[^A-Za-z0-9]/g, '');
  const scorer = km ? (km.team === p.home.team_id ? p.home : p.away) : null;
  const other = scorer === p.home ? p.away : p.home;
  const animate = active && !reduced && !!km;

  const css = useMemo(() => {
    if (!km) return '';
    const stops = ballTimeline(km.path, DRAW_SHARE);
    const ball = stops.map((s) => `${s.at}%{transform:translate(${s.x}px,${s.y}px)}`).join('');
    const segs = km.path
      .map((s, i) => {
        const a = stops[i].at;
        const b = stops[i + 1].at;
        const L = len(s).toFixed(1);
        return `@keyframes pp-seg-${id}-${i}{0%,${a}%{stroke-dashoffset:${L};opacity:1}${b}%{stroke-dashoffset:0;opacity:1}92%{stroke-dashoffset:0;opacity:1}100%{stroke-dashoffset:0;opacity:0}}`;
      })
      .join('');
    const hit = stops[stops.length - 1].at;
    return (
      `@keyframes pp-ball-${id}{${ball}92%{transform:translate(${stops[stops.length - 1].x}px,${stops[stops.length - 1].y}px);opacity:1}100%{transform:translate(${stops[stops.length - 1].x}px,${stops[stops.length - 1].y}px);opacity:0}}` +
      segs +
      `@keyframes pp-hit-${id}{0%,${hit - 0.5}%{opacity:0;transform:scale(0.3)}${Math.min(99, hit + 4)}%{opacity:1;transform:scale(1.4)}92%{opacity:0.6;transform:scale(1)}100%{opacity:0}}`
    );
  }, [km, id]);

  const loop = km ? (km.path.length * STEP_S + HOLD_S).toFixed(2) : '0';
  const last = km?.path[km.path.length - 1];
  const label = hide
    ? t('picker.hidden')
    : km && scorer
      ? t('picker.pitchLabel', { steps: km.path.length, team: scorer.name })
      : t('picker.hidden');

  return (
    <div
      className="relative"
      role="img"
      aria-label={label}
      tabIndex={focusable ? 0 : undefined}
      data-testid="mini-pitch"
      data-animating={animate ? 'true' : 'false'}
    >
      <svg viewBox={`-3 -3 ${PITCH_W + 6} ${PITCH_H + 6}`} className="block w-full bg-pp-turf" aria-hidden>
        {animate && <style>{css}</style>}
        <defs>
          <pattern id={`mow-${id}`} width="15" height={PITCH_H} patternUnits="userSpaceOnUse">
            <rect width="7.5" height={PITCH_H} fill="rgba(255,255,255,0.025)" />
          </pattern>
        </defs>
        <rect x="0" y="0" width={PITCH_W} height={PITCH_H} fill={`url(#mow-${id})`} />
        <g fill="none" stroke="#5f9a72" strokeWidth="0.5" opacity="0.8">
          <rect x="0" y="0" width={PITCH_W} height={PITCH_H} />
          <line x1={PITCH_W / 2} y1="0" x2={PITCH_W / 2} y2={PITCH_H} />
          <circle cx={PITCH_W / 2} cy={PITCH_H / 2} r="9.15" />
          <rect x="0" y={PITCH_H / 2 - 20.16} width="16.5" height="40.32" />
          <rect x={PITCH_W - 16.5} y={PITCH_H / 2 - 20.16} width="16.5" height="40.32" />
          <rect x="0" y={PITCH_H / 2 - 9.16} width="5.5" height="18.32" />
          <rect x={PITCH_W - 5.5} y={PITCH_H / 2 - 9.16} width="5.5" height="18.32" />
          <rect x="-2" y={PITCH_H / 2 - 3.66} width="2" height="7.32" />
          <rect x={PITCH_W} y={PITCH_H / 2 - 3.66} width="2" height="7.32" />
        </g>
        {km && scorer && !hide && (
          <>
            {/* The shot's freeze frame: the scorer's side and the defenders, as recorded. */}
            <g>
              {km.players.map((pl, i) => (
                <circle
                  key={i}
                  cx={pl.x}
                  cy={pl.y}
                  r={pl.actor ? 1.9 : 1.4}
                  fill={pl.mate ? scorer.primary_color : other.primary_color}
                  stroke={pl.actor ? '#ffd400' : '#0c0c0b'}
                  strokeWidth={pl.actor ? 0.7 : 0.35}
                  className={animate ? 'pp-dot-in' : undefined}
                  style={animate ? { animationDelay: `${i * 30}ms` } : undefined}
                  opacity={active || reduced ? 1 : 0.55}
                />
              ))}
            </g>
            <g strokeLinecap="square">
              {km.path.map((s, i) => {
                const shot = s.kind === 'shot';
                const L = len(s);
                return (
                  <line
                    key={i}
                    x1={s.x1}
                    y1={s.y1}
                    x2={s.x2}
                    y2={s.y2}
                    stroke={shot ? '#ff3e32' : s.kind === 'pass' ? '#f2efe8' : '#ffd400'}
                    strokeWidth={shot ? 0.9 : 0.6}
                    strokeDasharray={animate ? `${L.toFixed(1)}` : s.kind === 'pass' || shot ? undefined : '1.4 1'}
                    opacity={animate || reduced || active ? 1 : 0.35}
                    style={animate ? { animation: `pp-seg-${id}-${i} ${loop}s linear infinite` } : undefined}
                  />
                );
              })}
            </g>
            {last && (
              <circle
                cx={last.x2}
                cy={last.y2}
                r="2.6"
                fill="none"
                stroke="#ff3e32"
                strokeWidth="0.6"
                style={animate ? { transformBox: 'fill-box', transformOrigin: 'center', animation: `pp-hit-${id} ${loop}s ease-out infinite` } : undefined}
                opacity={animate || reduced ? undefined : 0}
              />
            )}
            {animate ? (
              <circle cx="0" cy="0" r="1.1" fill="#ffffff" stroke="#0c0c0b" strokeWidth="0.3" style={{ animation: `pp-ball-${id} ${loop}s linear infinite` }} />
            ) : (
              last && <circle cx={last.x2} cy={last.y2} r="1.1" fill="#ffffff" stroke="#0c0c0b" strokeWidth="0.3" opacity={reduced || active ? 1 : 0.5} />
            )}
          </>
        )}
      </svg>
      {hide && (
        <span className="absolute inset-0 flex items-center justify-center font-display text-sm font-bold uppercase tracking-broadcast text-pp-chalk/80" aria-hidden>
          {t('picker.hidden')}
        </span>
      )}
    </div>
  );
};
