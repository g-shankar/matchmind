// "Show your working" button, on every crew card. The claim audit drawer it opens
// (ClaimAudit.tsx) is loaded on first use, so it is not part of the first screen.
import React, { Suspense, lazy, useRef, useState } from 'react';
import { ListChecks } from 'lucide-react';
import type { PersonaType } from '../api/contract';
import { useI18n } from '../i18n';
import { cx } from './ui';

const AuditDrawer = lazy(() => import('./ClaimAudit').then((m) => ({ default: m.AuditDrawer })));

export const LazyAuditDrawer: React.FC<React.ComponentProps<typeof AuditDrawer>> = (props) => (
  <Suspense fallback={null}>
    <AuditDrawer {...props} />
  </Suspense>
);


export const ShowWorkingButton: React.FC<{
  momentId: string;
  persona?: PersonaType;
  language?: string;
  className?: string;
}> = ({ momentId, persona, language, className }) => {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button
        ref={ref}
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        className={cx(
          'inline-flex min-h-[44px] items-center gap-1.5 border border-pp-line bg-pp-night px-3 font-display text-[13px] font-bold uppercase tracking-broadcast text-pp-chalk transition hover:border-pp-signal hover:text-pp-signal focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal',
          className,
        )}
      >
        <ListChecks className="h-4 w-4 text-pp-signal" aria-hidden />
        {t('audit.button')}
      </button>
      {open && (
        <LazyAuditDrawer
          momentId={momentId}
          persona={persona}
          language={language}
          onClose={() => {
            setOpen(false);
            ref.current?.focus();
          }}
        />
      )}
    </>
  );
};

