import React, { useState } from 'react';
import { Check, Copy, PlugZap, RotateCw } from 'lucide-react';
import { useI18n } from '../i18n';
import type { InsightState } from '../state/useInsight';
import { cx } from './ui';

/** Placeholder bars while a panel loads (never a blank wait). */
export const Skeleton: React.FC<{ lines?: number; className?: string }> = ({ lines = 3, className }) => {
  const { t } = useI18n();
  return (
    <div role="status" aria-live="polite" className={cx('space-y-2', className)}>
      <span className="sr-only">{t('common.loading')}</span>
      <div className="animate-pulse space-y-2" aria-hidden>
        {Array.from({ length: lines }, (_, i) => (
          <div key={i} className={cx('h-3 bg-pp-line/60', i % 3 === 0 ? 'w-3/4' : i % 3 === 1 ? 'w-full' : 'w-5/6')} />
        ))}
      </div>
    </div>
  );
};

/**
 * One plain message for a panel that is not ready: loading, needs the live
 * server (offline demo), nothing there, rate limited, or failed (with a retry).
 * Returns null when the state is ready.
 */
export function InsightGate<T>({
  state,
  onRetry,
  lines = 3,
  missingKey = 'insight.missing',
  needsServerKey = 'insight.needsServer',
}: {
  state: InsightState<T>;
  onRetry?: () => void;
  lines?: number;
  missingKey?: string;
  needsServerKey?: string;
}): React.ReactElement | null {
  const { t } = useI18n();
  if (state.status === 'ready') return null;
  if (state.status === 'loading') return <Skeleton lines={lines} />;
  if (state.status === 'needs_server') {
    return (
      <p className="flex items-start gap-2 border border-dashed border-pp-line bg-pp-deep/60 px-3 py-2.5 text-sm text-pp-mute">
        <PlugZap className="mt-0.5 h-4 w-4 shrink-0 text-pp-gold" aria-hidden />
        <span>{t(needsServerKey)}</span>
      </p>
    );
  }
  const key = state.status === 'missing' ? missingKey : state.status === 'busy' ? 'insight.busy' : 'insight.error';
  return (
    <div role={state.status === 'error' ? 'alert' : undefined} className="flex flex-wrap items-center gap-3 border border-pp-line bg-pp-deep/60 px-3 py-2.5 text-sm">
      <span className={state.status === 'error' ? 'text-pp-pulseSoft' : 'text-pp-mute'}>{t(key)}</span>
      {onRetry && state.status !== 'missing' && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex min-h-[44px] items-center gap-1.5 border border-pp-line px-3 font-display text-sm font-bold uppercase tracking-broadcast text-pp-chalk hover:border-pp-pulse focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
        >
          <RotateCw className="h-4 w-4" aria-hidden />
          {t('insight.retry')}
        </button>
      )}
    </div>
  );
}

/** A read-only value (URL, command) with a copy button. */
export const CopyField: React.FC<{ label: string; value: string; href?: string | null }> = ({ label, value, href }) => {
  const { t } = useI18n();
  const [copied, setCopied] = useState<'ok' | 'fail' | null>(null);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied('ok');
    } catch {
      setCopied('fail');
    }
    setTimeout(() => setCopied(null), 2000);
  };
  return (
    <div className="min-w-0">
      <span className="mb-1 block text-[11px] font-bold uppercase tracking-broadcast text-pp-mute">{label}</span>
      <div className="flex min-w-0 items-stretch border border-pp-line bg-pp-night">
        {href ? (
          <a href={href} target="_blank" rel="noreferrer noopener" dir="ltr" className="flex min-h-[44px] min-w-0 flex-1 items-center break-all px-3 py-2 font-mono text-xs text-pp-signal underline-offset-2 hover:underline">
            {value}
          </a>
        ) : (
          <code dir="ltr" className="flex min-h-[44px] min-w-0 flex-1 items-center break-all px-3 py-2 text-xs text-pp-chalk">
            {value}
          </code>
        )}
        <button
          type="button"
          onClick={copy}
          aria-label={t('insight.copy', { what: label })}
          title={t('insight.copy', { what: label })}
          className="flex w-11 shrink-0 items-center justify-center border-s border-pp-line text-pp-mute hover:text-pp-chalk focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
        >
          {copied === 'ok' ? <Check className="h-4 w-4 text-pp-signal" aria-hidden /> : <Copy className="h-4 w-4" aria-hidden />}
        </button>
      </div>
      <span aria-live="polite" className="block min-h-[1rem] text-[11px] text-pp-mute">
        {copied === 'ok' ? t('insight.copied') : copied === 'fail' ? t('insight.copyFailed') : ''}
      </span>
    </div>
  );
};

/** Section heading inside a panel, in the broadcast slab style. */
export const SubHead: React.FC<{ id?: string; children: React.ReactNode; className?: string }> = ({ id, children, className }) => (
  <h3 id={id} className={cx('mb-2 font-display text-sm font-extrabold uppercase italic tracking-broadcast text-pp-chalk', className)}>
    {children}
  </h3>
);
