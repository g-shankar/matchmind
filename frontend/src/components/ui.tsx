import type React from 'react';
import type { TeamInfo } from '../api/contract';

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ');

export const Panel: React.FC<{ title?: React.ReactNode; actions?: React.ReactNode; className?: string; children: React.ReactNode }> = ({
  title,
  actions,
  className,
  children,
}) => (
  <section className={cx('rounded-2xl border border-pp-line/70 bg-pp-panel/80 p-4 shadow-lg shadow-black/30', className)}>
    {(title || actions) && (
      <header className="mb-3 flex items-center justify-between gap-3">
        {title && <h2 className="font-display text-sm font-semibold uppercase tracking-wider text-slate-200">{title}</h2>}
        {actions}
      </header>
    )}
    {children}
  </section>
);

export const Badge: React.FC<{ tone?: 'pulse' | 'signal' | 'gold' | 'mute'; className?: string; title?: string; children: React.ReactNode }> = ({
  tone = 'mute',
  className,
  title,
  children,
}) => {
  const tones = {
    pulse: 'border-pp-pulse/50 bg-pp-pulse/15 text-pp-pulseSoft',
    signal: 'border-pp-signal/50 bg-pp-signal/10 text-pp-signal',
    gold: 'border-pp-gold/50 bg-pp-gold/10 text-pp-gold',
    mute: 'border-pp-line bg-pp-deep text-pp-mute',
  };
  return (
    <span title={title} className={cx('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold', tones[tone], className)}>
      {children}
    </span>
  );
};

export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  label,
  className,
}: {
  options: { value: T; label: React.ReactNode; title?: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cx('flex items-center gap-1 rounded-xl border border-pp-line bg-pp-deep p-1', className)}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          title={o.title}
          onClick={() => onChange(o.value)}
          className={cx(
            'min-h-[32px] rounded-lg px-2.5 text-xs font-semibold transition',
            value === o.value ? 'bg-pp-pulse text-white shadow' : 'text-pp-mute hover:text-white',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export const TeamDot: React.FC<{ team: TeamInfo | null; size?: number }> = ({ team, size = 10 }) => (
  <span
    aria-hidden
    className="inline-block shrink-0 rounded-full ring-1 ring-white/30"
    style={{ width: size, height: size, background: team?.primary_color ?? '#64748b' }}
  />
);

export const Logo: React.FC = () => (
  <svg viewBox="0 0 64 64" className="h-9 w-9" aria-hidden>
    <rect width="64" height="64" rx="14" fill="#18233b" />
    <path
      d="M8 34h12l5-12 8 24 6-16 4 4h13"
      fill="none"
      stroke="#ff4d6d"
      strokeWidth="5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);
