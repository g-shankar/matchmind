import type React from 'react';
import type { TeamInfo } from '../api/contract';

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ');

export const Panel: React.FC<{ title?: React.ReactNode; actions?: React.ReactNode; className?: string; children: React.ReactNode }> = ({
  title,
  actions,
  className,
  children,
}) => (
  <section className={cx('flex flex-col border border-pp-line bg-pp-panel/95', className)}>
    {(title || actions) && (
      <header className="flex items-stretch justify-between gap-3 border-b border-pp-line">
        {title ? (
          <h2 className="pp-slant flex items-center bg-pp-chalk py-1.5 pe-6 ps-3 font-display text-sm font-extrabold uppercase italic tracking-broadcast text-pp-night [&_svg]:text-pp-pulse">
            {title}
          </h2>
        ) : (
          <span />
        )}
        {actions && <div className="flex items-center px-3 py-1.5">{actions}</div>}
      </header>
    )}
    <div className="flex min-h-0 flex-1 flex-col p-4">{children}</div>
  </section>
);

export const Badge: React.FC<{ tone?: 'pulse' | 'signal' | 'gold' | 'mute'; className?: string; title?: string; children: React.ReactNode }> = ({
  tone = 'mute',
  className,
  title,
  children,
}) => {
  const tones = {
    pulse: 'bg-pp-pulse text-white',
    signal: 'bg-pp-signal text-pp-night',
    gold: 'bg-pp-gold text-pp-night',
    mute: 'border border-pp-line bg-pp-deep text-pp-mute',
  };
  return (
    <span
      title={title}
      className={cx(
        'inline-flex items-center gap-1 px-1.5 py-0.5 font-display text-[12px] font-bold uppercase tracking-broadcast',
        tones[tone],
        className,
      )}
    >
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
    <div role="radiogroup" aria-label={label} className={cx('flex items-stretch border border-pp-line bg-pp-deep', className)}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          title={o.title}
          onClick={() => onChange(o.value)}
          className={cx(
            'min-h-[32px] border-b-2 px-2.5 font-display text-[13px] font-bold uppercase tracking-broadcast transition',
            value === o.value ? 'border-pp-pulse bg-pp-chalk text-pp-night' : 'border-transparent text-pp-mute hover:text-pp-chalk',
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

// Wordmark mark: a heartbeat trace cut through a pitch's halfway line.
export const Logo: React.FC = () => (
  <svg viewBox="0 0 40 40" className="h-9 w-9 shrink-0" aria-hidden>
    <rect width="40" height="40" fill="#ff3b2f" />
    <path d="M20 4v32" stroke="#0c0c0b" strokeWidth="1.5" opacity="0.35" />
    <path d="M3 22h9l3-8 5 15 4-11 3 4h10" fill="none" stroke="#f2efe8" strokeWidth="3.2" strokeLinecap="square" strokeLinejoin="miter" />
  </svg>
);
