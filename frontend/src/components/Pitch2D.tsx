import React, { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  isBetterOption,
  isUnfoundRun,
  type BetterOptionReplay,
  type FactValue,
  type MatchEvent,
  type OverlayCard,
  type Replay,
  type Teams,
  type UnfoundRunReplay,
  type XY,
} from '../api/contract';
import type { PlayerPosition } from '../state/matchStore';
import { useI18n, type I18n } from '../i18n';
import { playerById, shortName } from '../lib/teams';
import { cx } from './ui';
import { inkOn } from '../lib/contrast';
import type { CameraPreset } from '../lib/camera';

export interface Pitch2DProps {
  teams: Teams | null;
  /** Event to draw now (pass line, shot, carry...). */
  event: MatchEvent | null;
  /** Recent events drawn faintly behind the current one. */
  recentEvents?: MatchEvent[];
  /** Draws the better-option or unfound-run geometry instead of the live event. */
  replay?: Replay | null;
  /** Highlights one player: marker, trail and a label. */
  focusPlayerId?: string | null;
  positions?: Record<string, PlayerPosition>;
  trails?: Record<string, XY[]>;
  /** Speed and distance tags on the current event (from event.metrics). */
  showTags?: boolean;
  /** Active pitch_tag cards from the crew. */
  pitchTags?: OverlayCard[];
  /** Zooms the view box around the focus player. */
  zoomOnFocus?: boolean;
  /** Replay story step: 0 draws every layer, 1-3 draws layers up to that step and highlights it. */
  replayStep?: 0 | 1 | 2 | 3;
  /** False draws a picture only: no focusable or tappable player markers (e.g. a backdrop). */
  interactive?: boolean;
  /** Broadcast camera: wide (whole pitch), tactical (tilted) or follow (zoomed on the ball). */
  camera?: CameraPreset;
  className?: string;
}

// ---------------------------------------------------------------------------
// Geometry and formatting helpers (also used by ReplayCard).

const W = 105;
const H = 68;
const POSITION_MAX_AGE_S = 90;
const TRAIL_POINTS = 24;
const ZOOM_W = 45;
const FOLLOW_W = 50;
/** Tactical camera: the flat SVG pitch tilted away from the viewer (CSS 3D). */
export const TACTICAL_TRANSFORM = 'perspective(1100px) rotateX(32deg) scale(0.9)';

const C = {
  turf: '#0f2a1d',
  turfDark: '#0c2418',
  line: '#3c7a57',
  white: '#f2efe8',
  pulse: '#ff3b2f',
  pulseSoft: '#ff8a80',
  signal: '#ffd400',
  gold: '#ff9f1c',
  mute: '#a19c8f',
};

interface VB {
  x: number;
  y: number;
  w: number;
  h: number;
}

const FULL: VB = { x: 0, y: 0, w: W, h: H };

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Goal the play is heading for: the nearer goal line to a point in the attacking half. */
export const goalFor = (p: XY): XY => ({ x: p.x >= W / 2 ? W : 0, y: H / 2 });

/** Readable text colour on a team colour (the shared WCAG helper). */
export { inkOn };

/** Decimal places a payload number carries (capped), so displays match the evidence exactly. */
export function decimalsOf(value: number, max = 3): number {
  if (!Number.isFinite(value) || Number.isInteger(value)) return 0;
  const text = String(value);
  const dot = text.indexOf('.');
  return dot < 0 ? 0 : Math.min(max, text.length - dot - 1);
}

/** Formats a payload value for display (rounding only, never recomputing). */
export function fmtFact(value: FactValue, i18n: Pick<I18n, 'num' | 't'>): string {
  if (typeof value === 'boolean') return value ? i18n.t('pitch.yes') : i18n.t('pitch.no');
  if (typeof value === 'number') {
    return i18n.num(value, decimalsOf(value));
  }
  return value;
}

export function fmtUnit(unit: string | null, t: I18n['t']): string {
  if (!unit) return '';
  if (unit === 'km/h' || unit === 'kmh') return t('unit.kmh');
  if (unit === 'm') return t('unit.m');
  if (unit === 'km') return t('unit.km');
  return unit;
}

/** Translated label for an evidence key, falling back to a readable form of the key. */
export function evidenceLabel(label: string, t: I18n['t']): string {
  const key = `pitch.ev.${label}`;
  const text = t(key);
  if (text !== key) return text;
  const plain = label.replace(/_/g, ' ').trim();
  return plain.charAt(0).toUpperCase() + plain.slice(1);
}

/** Splits a translated sentence around a clock so the clock keeps left-to-right order. */
export function withClock(text: string, clock: string): React.ReactNode {
  const [before, after = ''] = text.split('\u0000');
  return (
    <>
      {before}
      <span className="ltr-nums">{clock}</span>
      {after}
    </>
  );
}

export const pct = (v: number) => `${Math.round(v <= 1 ? v * 100 : v)}`;

/** A window on the pitch around the points that matter, at the pitch's aspect ratio. */
export function boxAround(points: XY[], pad = 7, minW = 42): VB {
  if (!points.length) return FULL;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const x0 = Math.min(...xs) - pad;
  const x1 = Math.max(...xs) + pad;
  const y0 = Math.min(...ys) - pad;
  const y1 = Math.max(...ys) + pad;
  let w = Math.max(x1 - x0, minW, ((y1 - y0) * W) / H);
  w = Math.min(w, W);
  const h = (w * H) / W;
  const round = (v: number) => Math.round(v * 10) / 10;
  return {
    x: round(clamp((x0 + x1) / 2 - w / 2, 0, W - w)),
    y: round(clamp((y0 + y1) / 2 - h / 2, 0, H - h)),
    w: round(w),
    h: round(h),
  };
}

const near = (p: XY, refs: XY[], m: number) => refs.some((r) => Math.hypot(p.x - r.x, p.y - r.y) <= m);

function replayBox(r: Replay): VB {
  if (isBetterOption(r)) {
    const g = goalFor(r.shooter_pos);
    const core = [r.shooter_pos, r.teammate_pos];
    const extra = [...r.defenders, ...(r.keeper ? [r.keeper] : [])].filter((d) => near(d, core, 14));
    return boxAround([...core, ...extra, { x: g.x, y: 30 }, { x: g.x, y: 38 }]);
  }
  if (isUnfoundRun(r)) {
    const g = goalFor(r.target);
    return boxAround([r.carrier_pos, r.target, ...r.runner_path, ...r.defenders_at_pass, { x: g.x, y: g.y }]);
  }
  return FULL;
}

function useViewBox(target: VB): VB {
  const [vb, setVb] = useState<VB>(FULL);
  const current = useRef<VB>(FULL);
  useEffect(() => {
    const from = current.current;
    const same = from.x === target.x && from.y === target.y && from.w === target.w && from.h === target.h;
    if (same) return;
    const reduce =
      typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce || typeof requestAnimationFrame !== 'function') {
      current.current = target;
      setVb(target);
      return;
    }
    const start = performance.now();
    const dur = 650;
    let raf = 0;
    const step = (now: number) => {
      const k = clamp((now - start) / dur, 0, 1);
      const e = 1 - (1 - k) ** 3;
      const next = {
        x: from.x + (target.x - from.x) * e,
        y: from.y + (target.y - from.y) * e,
        w: from.w + (target.w - from.w) * e,
        h: from.h + (target.h - from.h) * e,
      };
      current.current = next;
      setVb(next);
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target.x, target.y, target.w, target.h]); // eslint-disable-line react-hooks/exhaustive-deps
  return vb;
}

/** Minimum touch target (WCAG 2.5.5 and section 3.7 of the project rules). */
export const TOUCH_TARGET_PX = 44;

const coarsePointer = () =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(pointer: coarse)').matches;

/** On a touch screen, the pitch's drawn width in CSS px (to size hit areas); null with a mouse. */
function useTouchWidth(ref: React.RefObject<HTMLDivElement>): number | null {
  const [coarse] = useState(coarsePointer);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!coarse || !el) return;
    const update = () => setWidth(el.clientWidth);
    update();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [coarse, ref]);
  return coarse && width > 0 ? width : null;
}

/** Nudges overlapping labels apart after layout (labels are measured, never guessed). */
function useLabelSpacing(ref: React.RefObject<HTMLDivElement>) {
  useLayoutEffect(() => {
    const root = ref.current;
    if (!root) return;
    const els = Array.from(root.querySelectorAll<HTMLElement>('[data-pp-label]'));
    els.forEach((el) => (el.style.translate = ''));
    const boxes = els
      .map((el) => ({ el, r: el.getBoundingClientRect() }))
      .filter((b) => b.r.width > 0 && b.r.height > 0)
      .sort((a, b) => a.r.top - b.r.top);
    const placed: { left: number; right: number; top: number; bottom: number }[] = [];
    for (const { el, r } of boxes) {
      let top = r.top;
      for (let guard = 0; guard < 8; guard++) {
        const hit = placed.find((p) => r.left < p.right && r.right > p.left && top < p.bottom && top + r.height > p.top);
        if (!hit) break;
        top = hit.bottom + 2;
      }
      if (top !== r.top) el.style.translate = `0 ${Math.round(top - r.top)}px`;
      placed.push({ left: r.left, right: r.right, top, bottom: top + r.height });
    }
  });
}

// ---------------------------------------------------------------------------
// SVG pieces.

const Markings: React.FC<{ k: number }> = ({ k }) => {
  const s = { fill: 'none', stroke: C.line, strokeWidth: 0.35 * k } as const;
  return (
    <g aria-hidden>
      <rect x={0} y={0} width={W} height={H} fill={C.turf} />
      {Array.from({ length: 12 }).map((_, i) =>
        i % 2 === 0 ? <rect key={i} x={(i * W) / 12} y={0} width={W / 12} height={H} fill={C.turfDark} /> : null,
      )}
      <rect x={0.4} y={0.4} width={W - 0.8} height={H - 0.8} {...s} />
      <line x1={W / 2} y1={0.4} x2={W / 2} y2={H - 0.4} {...s} />
      <circle cx={W / 2} cy={H / 2} r={9.15} {...s} />
      <circle cx={W / 2} cy={H / 2} r={0.5} fill={C.line} />
      {/* Left end */}
      <rect x={0.4} y={13.84} width={16.1} height={40.32} {...s} />
      <rect x={0.4} y={24.84} width={5.1} height={18.32} {...s} />
      <circle cx={11} cy={H / 2} r={0.45} fill={C.line} />
      <path d="M 16.5 26.69 A 9.15 9.15 0 0 1 16.5 41.31" {...s} />
      {/* Right end */}
      <rect x={W - 16.5} y={13.84} width={16.1} height={40.32} {...s} />
      <rect x={W - 5.5} y={24.84} width={5.1} height={18.32} {...s} />
      <circle cx={W - 11} cy={H / 2} r={0.45} fill={C.line} />
      <path d="M 88.5 26.69 A 9.15 9.15 0 0 0 88.5 41.31" {...s} />
      {/* Corner arcs */}
      <path d="M 0.4 1.4 A 1 1 0 0 0 1.4 0.4" {...s} />
      <path d="M 0.4 66.6 A 1 1 0 0 1 1.4 67.6" {...s} />
      <path d="M 104.6 1.4 A 1 1 0 0 1 103.6 0.4" {...s} />
      <path d="M 104.6 66.6 A 1 1 0 0 0 103.6 67.6" {...s} />
      {/* Goal mouths */}
      <line x1={0.5} y1={30.34} x2={0.5} y2={37.66} stroke="#ffffff" strokeWidth={1} opacity={0.85} />
      <line x1={W - 0.5} y1={30.34} x2={W - 0.5} y2={37.66} stroke="#ffffff" strokeWidth={1} opacity={0.85} />
    </g>
  );
};

/** Hover or keyboard focus on a tagged player dot shows his name. */
interface DotTag {
  id: string;
  /** Accessible name and tooltip, e.g. "9, Adam Kerrigan, Northbridge FC". */
  label: string;
  onShow: (id: string | null) => void;
  /** Radius of the invisible hit area in pitch units; set on touch screens so it is 44 px across. */
  hitR?: number;
}

const PlayerDot: React.FC<{
  at: XY;
  color: string;
  number?: number | string | null;
  r: number;
  opacity?: number;
  ring?: string;
  glow?: boolean;
  glowId?: string;
  dashed?: boolean;
  tag?: DotTag;
}> = ({ at, color, number, r, opacity = 1, ring = '#ffffff', glow, glowId, dashed, tag }) => (
  <g
    transform={`translate(${at.x} ${at.y})`}
    opacity={opacity}
    {...(tag
      ? {
          role: 'img',
          'aria-label': tag.label,
          tabIndex: 0,
          className: 'pp-dot cursor-default',
          'data-player-dot': tag.id,
          onMouseEnter: () => tag.onShow(tag.id),
          onMouseLeave: () => tag.onShow(null),
          onFocus: () => tag.onShow(tag.id),
          onBlur: () => tag.onShow(null),
        }
      : {})}
  >
    {tag && <title>{tag.label}</title>}
    {/* A larger, invisible hit area so the dot is easy to hover or tap. */}
    {tag && <circle r={Math.max(r * 2, tag.hitR ?? 0)} fill="transparent" data-hit-area />}
    {glow && (
      <>
        <circle r={r * 2.4} fill={C.signal} opacity={0.18} filter={glowId ? `url(#${glowId})` : undefined} />
        <circle r={r * 1.7} fill="none" stroke={C.signal} strokeWidth={r * 0.18} className="pp-ring" />
      </>
    )}
    <circle r={r} fill={color} stroke={ring} strokeWidth={r * 0.2} strokeDasharray={dashed ? `${r * 0.5} ${r * 0.35}` : undefined} />
    {number !== undefined && number !== null && number !== '' && (
      <text
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={String(number).length > 2 ? r * 0.8 : r * 1.05}
        fontWeight={700}
        fill={inkOn(color)}
        style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
      >
        {number}
      </text>
    )}
  </g>
);

// ---------------------------------------------------------------------------
// HTML labels laid over the SVG, so text stays readable on a phone at any zoom.

type Tone = 'dark' | 'signal' | 'gold' | 'pulse' | 'white';
/** Space between a label and the point it names, so it never covers the marker there. */
export const MARKER_GAP_PX = 16;
const TONES: Record<Tone, string> = {
  dark: 'border-white/15 bg-black/75 text-slate-100',
  signal: 'border-pp-signal/60 bg-pp-deep/90 text-pp-signal',
  gold: 'border-pp-gold/60 bg-pp-deep/90 text-pp-gold',
  pulse: 'border-pp-pulse/60 bg-pp-deep/90 text-pp-pulseSoft',
  white: 'border-white/70 bg-white text-pp-night',
};

const Label: React.FC<{
  at: XY;
  vb: VB;
  place?: 'above' | 'below';
  tone?: Tone;
  className?: string;
  /** Classes for the positioned wrapper, e.g. to hide a secondary label on phones. */
  wrapClassName?: string;
  testId?: string;
  children: React.ReactNode;
}> = ({ at, vb, place = 'above', tone = 'dark', className, wrapClassName, testId, children }) => {
  const { dir } = useI18n();
  const left = clamp(((at.x - vb.x) / vb.w) * 100, 2, 98);
  const top = clamp(((at.y - vb.y) / vb.h) * 100, 4, 96);
  const tx = left > 72 ? '-100%' : left < 28 ? '0%' : '-50%';
  const nudge = left > 72 ? '8px' : left < 28 ? '-8px' : '0px';
  // Clear of the player marker (about 12 px across on a phone, more on a desktop pitch).
  const ty = place === 'above' ? `calc(-100% - ${MARKER_GAP_PX}px)` : `${MARKER_GAP_PX}px`;
  const flipBelow = place === 'above' && top < 16;
  const flipAbove = place === 'below' && top > 84;
  const y = flipBelow ? `${MARKER_GAP_PX}px` : flipAbove ? `calc(-100% - ${MARKER_GAP_PX}px)` : ty;
  return (
    <div
      className={cx('pointer-events-none absolute z-10', wrapClassName)}
      style={{ left: `${left}%`, top: `${top}%`, transform: `translate(calc(${tx} + ${nudge}), ${y})` }}
      data-testid={testId}
      data-pp-label
    >
      <div
        dir={dir}
        className={cx(
          'animate-fade-in whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[10px] font-semibold leading-tight shadow-lg shadow-black/40 sm:text-xs',
          TONES[tone],
          className,
        )}
      >
        {children}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------

interface Ctx {
  teams: Teams | null;
  vb: VB;
  k: number; // marker scale (keeps markers the same size on screen when zoomed)
  ids: { glow: string; arrow: (c: string) => string };
}

const ARROW_COLORS: Record<string, string> = { white: C.white, pulse: C.pulseSoft, gold: C.gold, signal: C.signal };

const sideColors = (teams: Teams | null, playerId: string | null | undefined) => {
  const p = playerById(teams, playerId);
  if (!teams || !p) return { own: '#60a5fa', opp: '#f87171', number: p?.number ?? null };
  const opp = p.side === 'home' ? teams.away : teams.home;
  return { own: p.team.primary_color, opp: opp.primary_color, number: p.number };
};

const shown = (step: number, layer: number) => step === 0 || layer <= step;
const layerOpacity = (step: number, layer: number) => (step === 0 || layer === step ? 1 : 0.4);

// Labels follow the story: only the current step's labels (all of them when step is 0).
const labelled = (step: number, layer: number) => step === 0 || layer === step;

function betterLabels(r: BetterOptionReplay, vb: VB, step: number, { t, num }: I18n): React.ReactNode[] {
  const labels: React.ReactNode[] = [];
  const show = (layer: number) => labelled(step, layer);
  if (show(1)) {
    labels.push(
      <Label key="shot" at={r.shooter_pos} vb={vb} place="below" tone="gold" testId="replay-shot">
        <span className="tabular-nums">{t('pitch.shotTaken', { v: num(r.shot_chance_quality, Math.max(2, decimalsOf(r.shot_chance_quality))) })}</span>
      </Label>,
    );
  }
  if (show(2)) {
    labels.push(
      <Label key="odds" at={{ x: r.shooter_pos.x + (r.teammate_pos.x - r.shooter_pos.x) * 0.4, y: r.shooter_pos.y + (r.teammate_pos.y - r.shooter_pos.y) * 0.4 }} vb={vb} place="above" tone="signal" testId="replay-odds">
        <span className="tabular-nums">{t('pitch.passOdds', { v: pct(r.pass_success) })}</span>
      </Label>,
      <Label key="nearest" at={r.teammate_pos} vb={vb} place="below" testId="replay-nearest" wrapClassName="hidden sm:block">
        <span className="tabular-nums">{t('pitch.nearest', { v: num(r.nearest_marker_m, 1) })}</span>
      </Label>,
    );
  }
  if (show(3)) {
    labels.push(
      <Label key="alt" at={r.teammate_pos} vb={vb} place="above" tone="signal" testId="replay-alt">
        <span className="tabular-nums">{t('pitch.openMate', { v: num(r.alt_chance_quality, Math.max(2, decimalsOf(r.alt_chance_quality))) })}</span>
      </Label>,
    );
  }
  return labels;
}

const BetterOptionLayer: React.FC<{ r: BetterOptionReplay; ctx: Ctx; step: number }> = ({ r, ctx, step }) => {
  const { t } = useI18n();
  const { own, opp, number } = sideColors(ctx.teams, r.shooter_id);
  const mate = playerById(ctx.teams, r.teammate_id);
  const goal = goalFor(r.shooter_pos);
  const rr = 1.7 * ctx.k;
  const show = (layer: number) => shown(step, layer);
  const op = (layer: number) => layerOpacity(step, layer);

  return (
    <g>
      {/* Defenders and keeper */}
      {r.defenders.map((d, i) => (
        <PlayerDot key={`d${i}`} at={d} color={opp} r={rr * 0.85} opacity={0.95} />
      ))}
      {r.keeper && <PlayerDot at={r.keeper} color={opp} r={rr * 0.85} number={t('pitch.keeper')} ring={C.gold} />}

      {show(1) && (
        <g opacity={op(1)} key={`s1-${step}`}>
          <line x1={r.shooter_pos.x} y1={r.shooter_pos.y} x2={goal.x} y2={goal.y} stroke={C.gold} strokeWidth={0.55 * ctx.k} markerEnd={`url(#${ctx.ids.arrow('gold')})`} pathLength={1} strokeDasharray="1" className="pp-draw" />
        </g>
      )}
      {show(2) && (
        <g opacity={op(2)}>
          {/* Space around the free teammate: radius is the payload's nearest-marker distance */}
          <circle cx={r.teammate_pos.x} cy={r.teammate_pos.y} r={r.nearest_marker_m} fill={C.signal} fillOpacity={0.07} stroke={C.signal} strokeOpacity={0.5} strokeWidth={0.25 * ctx.k} strokeDasharray={`${0.8 * ctx.k} ${0.6 * ctx.k}`} />
          <line x1={r.shooter_pos.x} y1={r.shooter_pos.y} x2={r.teammate_pos.x} y2={r.teammate_pos.y} stroke={C.signal} strokeWidth={0.6 * ctx.k} strokeDasharray={`${1.6 * ctx.k} ${1 * ctx.k}`} className="pp-march" markerEnd={`url(#${ctx.ids.arrow('signal')})`} />
        </g>
      )}
      {show(3) && (
        <g opacity={op(3)} key={`s3-${step}`}>
          <line x1={r.teammate_pos.x} y1={r.teammate_pos.y} x2={goal.x} y2={goal.y} stroke={C.signal} strokeWidth={0.5 * ctx.k} strokeDasharray="1" pathLength={1} className="pp-draw" markerEnd={`url(#${ctx.ids.arrow('signal')})`} />
          <circle cx={goal.x} cy={goal.y} r={3.66} fill={C.signal} opacity={0.15} className="pp-flash" />
        </g>
      )}

      <PlayerDot at={r.teammate_pos} color={own} number={mate?.number} r={rr} glow={show(2)} glowId={ctx.ids.glow} />
      <PlayerDot at={r.shooter_pos} color={own} number={number} r={rr} ring={C.gold} />
    </g>
  );
};

function runLabels(r: UnfoundRunReplay, vb: VB, step: number, { t, num }: I18n): React.ReactNode[] {
  const labels: React.ReactNode[] = [];
  const show = (layer: number) => labelled(step, layer);
  const goal = goalFor(r.target);
  if (show(1)) {
    labels.push(
      <Label key="on" at={r.carrier_pos} vb={vb} place="above" tone="signal" testId="replay-pass-on">
        {withClock(t('pitch.passOnAt', { clock: '\u0000' }), r.pass_on_clock)}
      </Label>,
    );
  }
  if (show(2)) {
    labels.push(
      <Label key="clear" at={r.target} vb={vb} place="above" tone="gold" testId="replay-clear">
        <span className="tabular-nums">{t('pitch.clearOfLine', { m: num(r.clear_of_line_m, 1) })}</span>
      </Label>,
    );
  }
  if (show(3)) {
    labels.push(
      <Label key="proj" at={{ x: (r.target.x + goal.x) / 2, y: (r.target.y + goal.y) / 2 + 2 }} vb={vb} place="below" tone="white" testId="replay-projected">
        <span className="tabular-nums">{t('pitch.projected', { v: num(r.projected_chance_quality, Math.max(2, decimalsOf(r.projected_chance_quality))) })}</span>
      </Label>,
    );
  }
  return labels;
}

const UnfoundRunLayer: React.FC<{ r: UnfoundRunReplay; ctx: Ctx; step: number }> = ({ r, ctx, step }) => {
  const { own, opp } = sideColors(ctx.teams, r.runner_id);
  const runner = playerById(ctx.teams, r.runner_id);
  const carrier = playerById(ctx.teams, r.carrier_id);
  const rr = 1.7 * ctx.k;
  const show = (layer: number) => shown(step, layer);
  const op = (layer: number) => layerOpacity(step, layer);
  const line = [...r.defenders_at_pass].sort((a, b) => a.y - b.y);
  const path = r.runner_path.length ? r.runner_path : [r.target];
  const start = path[0];
  const goal = goalFor(r.target);

  return (
    <g>
      {/* Back line at the moment the pass was on */}
      {line.length > 1 && (
        <polyline points={line.map((p) => `${p.x},${p.y}`).join(' ')} fill="none" stroke={opp} strokeWidth={0.35 * ctx.k} strokeDasharray={`${0.8 * ctx.k} ${0.6 * ctx.k}`} opacity={0.85} />
      )}
      {line.map((d, i) => (
        <PlayerDot key={`d${i}`} at={d} color={opp} r={rr * 0.85} />
      ))}

      {show(1) && (
        <g opacity={op(1)} key={`r1-${step}`}>
          <polyline points={path.map((p) => `${p.x},${p.y}`).join(' ')} fill="none" stroke={C.signal} strokeWidth={0.6 * ctx.k} strokeLinecap="round" strokeLinejoin="round" pathLength={1} strokeDasharray="1" className="pp-draw" markerEnd={`url(#${ctx.ids.arrow('signal')})`} />
        </g>
      )}
      {show(2) && (
        <g opacity={op(2)}>
          <line x1={r.carrier_pos.x} y1={r.carrier_pos.y} x2={r.target.x} y2={r.target.y} stroke={C.gold} strokeWidth={0.55 * ctx.k} strokeDasharray={`${1.6 * ctx.k} ${1 * ctx.k}`} className="pp-march" markerEnd={`url(#${ctx.ids.arrow('gold')})`} />
          <g transform={`translate(${r.target.x} ${r.target.y})`}>
            <circle r={2.2 * ctx.k} fill="none" stroke={C.gold} strokeWidth={0.3 * ctx.k} className="pp-ring" />
            <circle r={0.6 * ctx.k} fill={C.gold} />
          </g>
        </g>
      )}
      {show(3) && (
        <g opacity={op(3)} key={`r3-${step}`}>
          <line x1={r.target.x} y1={r.target.y} x2={goal.x} y2={goal.y} stroke="#ffffff" strokeWidth={0.4 * ctx.k} strokeDasharray="1" pathLength={1} className="pp-draw" opacity={0.8} markerEnd={`url(#${ctx.ids.arrow('white')})`} />
          <circle cx={goal.x} cy={goal.y} r={3.66} fill="#ffffff" opacity={0.12} className="pp-flash" />
        </g>
      )}

      <PlayerDot at={r.carrier_pos} color={own} number={carrier?.number} r={rr} />
      <PlayerDot at={start} color={own} number={runner?.number} r={rr} glow={show(1)} glowId={ctx.ids.glow} />
    </g>
  );
};

function eventPaint(e: MatchEvent): { color: string; arrow: string | null; dash?: string; width: number } {
  switch (e.type) {
    case 'pass': {
      const ok = e.outcome === 'complete';
      if (!ok) return { color: C.pulseSoft, arrow: 'pulse', dash: '1.2 0.8', width: 0.5 };
      return e.metrics.progressive ? { color: C.signal, arrow: 'signal', width: 0.6 } : { color: C.white, arrow: 'white', width: 0.5 };
    }
    case 'shot':
      return { color: C.gold, arrow: 'gold', width: 0.65 };
    case 'carry':
    case 'dribble':
      return { color: C.white, arrow: 'white', dash: '0.4 0.7', width: 0.45 };
    case 'run':
      return { color: C.signal, arrow: 'signal', dash: '1.4 0.8', width: 0.5 };
    default:
      return { color: C.mute, arrow: null, width: 0.4 };
  }
}

const eventEnd = (e: MatchEvent): XY | null => {
  if (e.end) return e.end;
  if (e.type === 'shot' && e.start) return goalFor(e.start);
  return null;
};

// ---------------------------------------------------------------------------

export const Pitch2D: React.FC<Pitch2DProps> = ({
  teams,
  event,
  recentEvents = [],
  replay = null,
  focusPlayerId = null,
  positions,
  trails,
  showTags = false,
  pitchTags = [],
  zoomOnFocus = false,
  replayStep = 0,
  interactive = true,
  camera = 'wide',
  className,
}) => {
  const i18n = useI18n();
  const { t, num } = i18n;
  const wrapRef = useRef<HTMLDivElement>(null);
  const [shownId, setShownId] = useState<string | null>(null);
  const rawId = useId();
  const uid = `pp${rawId.replace(/[^a-zA-Z0-9]/g, '')}`;
  const ids = { glow: `${uid}-glow`, arrow: (c: string) => `${uid}-arrow-${c}` };

  const focusPos: XY | null = useMemo(() => {
    if (!focusPlayerId) return null;
    const p = positions?.[focusPlayerId];
    if (p) return p;
    const tr = trails?.[focusPlayerId];
    return tr && tr.length ? tr[tr.length - 1] : null;
  }, [focusPlayerId, positions, trails]);

  // Ball location for the follow camera: where the latest event ended (or started).
  const ballX = useMemo(() => {
    const evs = event ? [...recentEvents, event] : recentEvents;
    for (let i = evs.length - 1; i >= 0; i--) {
      const at = eventEnd(evs[i]) ?? evs[i].start;
      if (at) return `${Math.round(at.x * 10) / 10},${Math.round(at.y * 10) / 10}`;
    }
    return null;
  }, [event, recentEvents]);
  const ballPos: XY | null = useMemo(() => {
    if (!ballX) return null;
    const [x, y] = ballX.split(',').map(Number);
    return { x, y };
  }, [ballX]);

  const target: VB = useMemo(() => {
    if (replay) return replayBox(replay);
    const centre = zoomOnFocus && focusPos ? focusPos : camera === 'follow' ? ballPos : null;
    if (!centre) return FULL;
    const zw = zoomOnFocus && focusPos ? ZOOM_W : FOLLOW_W;
    const zh = (zw * H) / W;
    return {
      x: Math.round(clamp(centre.x - zw / 2, 0, W - zw) * 10) / 10,
      y: Math.round(clamp(centre.y - zh / 2, 0, H - zh) * 10) / 10,
      w: zw,
      h: zh,
    };
  }, [zoomOnFocus, focusPos, replay, camera, ballPos]);
  const vb = useViewBox(target);
  const touchPx = useTouchWidth(wrapRef);
  const hitR = touchPx ? (TOUCH_TARGET_PX / 2) * (vb.w / touchPx) : undefined;
  const k = Math.sqrt(vb.w / W); // 1 at full pitch; markers grow a little on screen when zoomed
  const ctx: Ctx = { teams, vb, k, ids };

  const labels: React.ReactNode[] = [];
  const better = isBetterOption(replay) ? replay : null;
  const run = isUnfoundRun(replay) ? replay : null;
  const live = !better && !run ? event : null;

  // Last-known positions, faded by age relative to the event clock.
  const refClock =
    live?.clock_s ?? (positions ? Math.max(0, ...Object.values(positions).map((p) => p.clock_s)) : 0);
  const skip = new Set([live?.player_id, live?.receiver_id, focusPlayerId].filter(Boolean) as string[]);
  const dots =
    !replay && positions
      ? Object.entries(positions)
          .filter(([id]) => !skip.has(id))
          .map(([id, p]) => ({ id, p, age: refClock - p.clock_s, info: playerById(teams, id) }))
          .filter((d) => d.age <= POSITION_MAX_AGE_S && d.age >= -5)
      : [];

  // Name on hover or keyboard focus, for every dot that stands for a known player.
  const tagFor = (id: string | null | undefined): DotTag | undefined => {
    const info = playerById(teams, id);
    if (!interactive || !info || !id) return undefined;
    return { id, label: t('pitch.player', { number: info.number, name: info.name, team: info.team.name }), onShow: setShownId, hitR };
  };
  const shownAt: XY | null = (() => {
    if (!shownId || replay) return null;
    if (live?.player_id === shownId && live.start) return live.start;
    if (live?.receiver_id === shownId && live.outcome === 'complete') return eventEnd(live);
    if (shownId === focusPlayerId) return focusPos;
    return positions?.[shownId] ?? null;
  })();

  // Live event pieces.
  const actor = live ? playerById(teams, live.player_id) : null;
  const receiver = live ? playerById(teams, live.receiver_id) : null;
  const liveEnd = live ? eventEnd(live) : null;
  const paint = live ? eventPaint(live) : null;
  const isGoal = live?.type === 'shot' && live.outcome === 'goal';

  if (live?.start && live.type === 'shot' && live.metrics.chance_quality !== null) {
    labels.push(
      <Label key="xg" at={live.start} vb={vb} place="below" tone="gold" testId="xg-bubble">
        <span className="tabular-nums">{t('pitch.xg', { v: num(live.metrics.chance_quality, Math.max(2, decimalsOf(live.metrics.chance_quality))) })}</span>
      </Label>,
    );
  }
  if (isGoal && liveEnd) {
    labels.push(
      <Label key="goal" at={goalFor(live!.start ?? liveEnd)} vb={vb} place="above" tone="gold" className="font-display text-sm tracking-widest sm:text-base">
        {t('pitch.goal')}
      </Label>,
    );
  }

  const tagLines: { label: string; value: string; testId: string }[] = [];
  if (live && showTags) {
    const m = live.metrics;
    const ballEvent = live.type === 'pass' || live.type === 'shot';
    if (ballEvent && m.ball_speed_kmh !== null) {
      tagLines.push({ label: t('pitch.ballSpeed'), value: `${num(m.ball_speed_kmh, 0)} ${t('unit.kmh')}`, testId: 'tag-speed' });
    } else if (m.player_speed_kmh !== null) {
      tagLines.push({ label: t('pitch.speed'), value: `${num(m.player_speed_kmh, 1)} ${t('unit.kmh')}`, testId: 'tag-speed' });
    }
    if (live.type === 'pass' && m.pass_distance_m !== null) {
      tagLines.push({ label: t('pitch.passDistance'), value: `${num(m.pass_distance_m, 1)} ${t('unit.m')}`, testId: 'tag-distance' });
    } else if (live.type === 'shot' && m.distance_to_goal_m !== null) {
      tagLines.push({ label: t('pitch.toGoal'), value: `${num(m.distance_to_goal_m, 1)} ${t('unit.m')}`, testId: 'tag-distance' });
    }
  }
  if (live?.start && tagLines.length) {
    labels.push(
      <Label key="tags" at={live.start} vb={vb} place="above" testId="event-tags">
        <span className="flex flex-col gap-0.5">
          {tagLines.map((l) => (
            <span key={l.testId} data-testid={l.testId} className="flex items-baseline justify-between gap-2">
              <span className="text-pp-mute">{l.label}</span>
              <span className="ltr-nums text-white">{l.value}</span>
            </span>
          ))}
        </span>
      </Label>,
    );
  }

  const tagAnchor = live ? (liveEnd ?? live.start) : null;
  if (tagAnchor && pitchTags.length) {
    labels.push(
      <Label key="pitch-tags" at={tagAnchor} vb={vb} place="below" tone="pulse" testId="pitch-tags">
        <span className="flex flex-col gap-0.5">
          {pitchTags.slice(0, 2).map((c) => {
            const ev = c.evidence[0];
            return (
              <span key={c.card_id} className="flex items-baseline gap-1.5">
                <span className="max-w-[11rem] truncate text-white">{c.headline}</span>
                {ev && (
                  <span className="ltr-nums text-pp-gold">
                    {fmtFact(ev.value, i18n)}
                    {ev.unit ? ` ${fmtUnit(ev.unit, t)}` : ''}
                  </span>
                )}
              </span>
            );
          })}
        </span>
      </Label>,
    );
  }

  const focusInfo = playerById(teams, focusPlayerId);
  if (focusPos && focusInfo && !replay) {
    labels.push(
      <Label key="focus" at={focusPos} vb={vb} place="above" tone="white" testId="focus-label">
        {shortName(focusInfo.name)}
      </Label>,
    );
  }
  const shownInfo = playerById(teams, shownId);
  if (shownAt && shownInfo && shownId !== focusPlayerId) {
    labels.push(
      <Label key="shown" at={shownAt} vb={vb} place="below" tone="signal" testId="player-name-label">
        <span className="ltr-nums">{shownInfo.number}</span> {shortName(shownInfo.name)}
      </Label>,
    );
  }

    const replayLayer = better ? (
    <BetterOptionLayer r={better} ctx={ctx} step={replayStep} />
  ) : run ? (
    <UnfoundRunLayer r={run} ctx={ctx} step={replayStep} />
  ) : null;
  const replayLabels = better ? betterLabels(better, vb, replayStep, i18n) : run ? runLabels(run, vb, replayStep, i18n) : [];

  // Accessible summary of what is drawn.
  let aria = t('pitch.aria.empty');
  if (better) {
    aria = t('pitch.aria.better', {
      shooter: playerById(teams, better.shooter_id)?.name ?? '',
      teammate: playerById(teams, better.teammate_id)?.name ?? '',
      xg: num(better.shot_chance_quality, Math.max(2, decimalsOf(better.shot_chance_quality))),
      alt: num(better.alt_chance_quality, Math.max(2, decimalsOf(better.alt_chance_quality))),
      x: num(better.times_better, 1),
    });
  } else if (run) {
    aria = t('pitch.aria.run', {
      runner: playerById(teams, run.runner_id)?.name ?? '',
      carrier: playerById(teams, run.carrier_id)?.name ?? '',
      clock: run.pass_on_clock,
      m: num(run.clear_of_line_m, 1),
    });
  } else if (live) {
    aria = t('pitch.aria.event', { event: t(`event.${live.type}`), player: actor?.name ?? '', clock: live.match_clock });
  }
  if (focusInfo && !replay) aria = `${aria} ${t('pitch.aria.focus', { player: focusInfo.name })}`;

  const rr = 1.7 * k;
  const trail = focusPlayerId ? trails?.[focusPlayerId]?.slice(-TRAIL_POINTS) : undefined;
  useLabelSpacing(wrapRef);

  return (
    <div
      dir="ltr"
      ref={wrapRef}
      data-testid="pitch-wrapper"
      data-camera={camera}
      style={{ transform: camera === 'tactical' ? TACTICAL_TRANSFORM : 'none', transformOrigin: '50% 60%' }}
      className={cx(
        'relative aspect-[105/68] w-full select-none overflow-hidden rounded-xl border border-pp-turfLine/40 bg-pp-turf shadow-2xl shadow-black/40 transition-transform duration-700 ease-out motion-reduce:transition-none',
        className,
      )}
    >
      <svg
        role="figure"
        aria-label={aria}
        viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
        preserveAspectRatio="xMidYMid meet"
        className="absolute inset-0 h-full w-full"
      >
        <defs>
          <style>{`
            .pp-draw { animation: ppDraw 0.35s ease-out both; }
            .pp-march { animation: ppMarch 0.9s linear infinite; }
            .pp-ring { transform-box: fill-box; transform-origin: center; animation: ppRing 1.8s ease-in-out infinite; }
            .pp-flash { transform-box: fill-box; transform-origin: center; animation: ppFlash 1.4s ease-out infinite; }
            .pp-fade { animation: ppFade 0.4s ease-out both; }
            .pp-dot:focus { outline: none; }
            .pp-dot:focus-visible { outline: 2px solid ${C.signal}; outline-offset: 1px; }
            @keyframes ppDraw { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
            @keyframes ppMarch { to { stroke-dashoffset: -2.6; } }
            @keyframes ppRing { 0%,100% { transform: scale(1); opacity: 0.9; } 50% { transform: scale(1.25); opacity: 0.45; } }
            @keyframes ppFlash { 0% { transform: scale(0.6); opacity: 0.8; } 100% { transform: scale(2.4); opacity: 0; } }
            @keyframes ppFade { from { opacity: 0; } to { opacity: 1; } }
          `}</style>
          <filter id={ids.glow} x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="1" />
          </filter>
          {Object.entries(ARROW_COLORS).map(([name, color]) => (
            <marker key={name} id={ids.arrow(name)} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
            </marker>
          ))}
        </defs>

        <Markings k={vb.w / W} />

        {/* Recent events, fading with age */}
        {!replay &&
          recentEvents
            .filter((e) => e.event_id !== live?.event_id && e.start)
            .slice(-6)
            .map((e, i, arr) => {
              const end = eventEnd(e);
              const p = eventPaint(e);
              const opacity = 0.1 + (0.25 * (i + 1)) / arr.length;
              return end ? (
                <line key={e.event_id} x1={e.start!.x} y1={e.start!.y} x2={end.x} y2={end.y} stroke={p.color} strokeWidth={p.width * 0.7 * k} strokeDasharray={p.dash} opacity={opacity} strokeLinecap="round" />
              ) : (
                <circle key={e.event_id} cx={e.start!.x} cy={e.start!.y} r={0.6 * k} fill={p.color} opacity={opacity} />
              );
            })}

        {/* Last-known positions */}
        {dots.map(({ id, p, age, info }) => (
          <PlayerDot
            key={id}
            at={p}
            color={info?.team.primary_color ?? C.mute}
            number={info?.number}
            r={1.25 * k}
            opacity={clamp(0.85 - (Math.max(0, age) / POSITION_MAX_AGE_S) * 0.6, 0.2, 0.85)}
            ring="rgba(255,255,255,0.6)"
            tag={tagFor(id)}
          />
        ))}

        {/* Focus trail */}
        {!replay && trail && trail.length > 1 && (
          <polyline points={trail.map((p) => `${p.x},${p.y}`).join(' ')} fill="none" stroke={C.signal} strokeWidth={0.45 * k} strokeLinecap="round" strokeLinejoin="round" opacity={0.7} strokeDasharray={`${0.9 * k} ${0.5 * k}`} />
        )}

        {/* Live event */}
        {live && live.start && paint && (
          <g key={live.event_id}>
            {liveEnd && (
              <line
                x1={live.start.x}
                y1={live.start.y}
                x2={liveEnd.x}
                y2={liveEnd.y}
                stroke={paint.color}
                strokeWidth={paint.width * k}
                strokeLinecap="round"
                {...(paint.dash
                  ? { strokeDasharray: paint.dash.split(' ').map((n) => Number(n) * k).join(' '), className: 'pp-fade' }
                  : { pathLength: 1, strokeDasharray: '1', className: 'pp-draw' })}
                markerEnd={paint.arrow ? `url(#${ids.arrow(paint.arrow)})` : undefined}
                data-testid="event-line"
              />
            )}
            {isGoal && liveEnd && <circle cx={liveEnd.x} cy={liveEnd.y} r={4} fill={C.gold} opacity={0.35} className="pp-flash" />}
            {receiver && liveEnd && live.outcome === 'complete' && (
              <PlayerDot at={liveEnd} color={receiver.team.primary_color} number={receiver.number} r={rr * 0.9} opacity={0.95} tag={tagFor(live.receiver_id)} />
            )}
            {live.type !== 'shot' && liveEnd && !(receiver && live.outcome === 'complete') && (
              <circle cx={liveEnd.x} cy={liveEnd.y} r={0.7 * k} fill="#ffffff" className="pp-fade" />
            )}
            <PlayerDot at={live.start} color={actor?.team.primary_color ?? C.mute} number={actor?.number} r={rr} tag={tagFor(live.player_id)} />
          </g>
        )}

        {/* Focus player */}
        {!replay && focusPos && focusInfo && (
          <g>
            <circle cx={focusPos.x} cy={focusPos.y} r={2.8 * k} fill="none" stroke="#ffffff" strokeWidth={0.35 * k} className="pp-ring" />
            <PlayerDot at={focusPos} color={focusInfo.team.primary_color} number={focusInfo.number} r={rr} ring={C.signal} tag={tagFor(focusPlayerId)} />
          </g>
        )}

        {replayLayer}
      </svg>

      {/* Readable labels on top of the drawing */}
      {labels}
      {replayLabels}

      {live?.type === 'pass' && live.metrics.progressive && live.outcome === 'complete' && (
        <div className="pointer-events-none absolute start-2 top-2 z-10">
          <span dir={i18n.dir} className="inline-flex items-center gap-1 rounded-full border border-pp-signal/60 bg-pp-deep/90 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-pp-signal sm:text-xs">
            {t('event.progressive')}
          </span>
        </div>
      )}

      {better && (step3(replayStep)) && (
        <div className="pointer-events-none absolute inset-x-0 top-2 z-20 flex justify-center">
          <span dir={i18n.dir} data-testid="replay-verdict" className="animate-slide-up rounded-full border border-pp-signal bg-pp-night/90 px-3 py-1 font-display text-sm font-bold uppercase tracking-wide text-white shadow-lg shadow-pp-signal/20 sm:text-lg">
            <span className="tabular-nums text-pp-signal">{t('pitch.timesBetter', { x: num(better.times_better, 1) })}</span>
          </span>
        </div>
      )}
      {run && step3(replayStep) && run.one_on_one && (
        <div className="pointer-events-none absolute inset-x-0 top-2 z-20 flex justify-center">
          <span dir={i18n.dir} data-testid="replay-one-on-one" className="animate-slide-up rounded-full border border-pp-gold bg-pp-night/90 px-3 py-1 font-display text-sm font-bold uppercase tracking-wide text-pp-gold shadow-lg sm:text-lg">
            {t('pitch.oneOnOne')}
          </span>
        </div>
      )}
    </div>
  );
};

const step3 = (s: number) => s === 0 || s === 3;
