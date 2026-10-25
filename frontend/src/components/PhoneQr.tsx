// "Take it to your phone": a QR code on the broadcast overlay, drawn locally (qrcode-generator,
// MIT) as SVG. It links to this same page on the viewer's fan view, in their language and
// audience; never an external QR service. Hidden below desktop width and in ?capture=1.
import React, { useId, useMemo, useState } from 'react';
import { QrCode, X } from 'lucide-react';
import qrcode from 'qrcode-generator';
import type { ViewerProfile } from '../api/contract';
import { useI18n } from '../i18n';

/** Same origin and path; keeps ?demo=1; sets lang and persona; opens the fan view. */
export function phoneLink(loc: Pick<Location, 'origin' | 'pathname' | 'search'>, profile: Pick<ViewerProfile, 'language' | 'persona'>): string {
  const q = new URLSearchParams();
  if (new URLSearchParams(loc.search).get('demo') === '1') q.set('demo', '1');
  q.set('lang', profile.language);
  q.set('persona', profile.persona);
  return `${loc.origin}${loc.pathname}?${q.toString()}#fan`;
}

export function qrPath(text: string): { size: number; d: string } {
  const qr = qrcode(0, 'M');
  qr.addData(text);
  qr.make();
  const n = qr.getModuleCount();
  let d = '';
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (qr.isDark(r, c)) d += `M${c} ${r}h1v1h-1z`;
  return { size: n, d };
}

export const PhoneQr: React.FC<{ profile: Pick<ViewerProfile, 'language' | 'persona'> }> = ({ profile }) => {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const id = useId();
  const url = phoneLink(window.location, profile);
  const { size, d } = useMemo(() => qrPath(url), [url]);
  return (
    <div data-testid="phone-qr" className="relative hidden lg:block" onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={id}
        aria-label={t('qr.caption')}
        title={t('qr.caption')}
        className="flex h-11 w-11 items-center justify-center bg-black/70 text-pp-chalk hover:text-pp-signal focus:outline-none focus-visible:ring-2 focus-visible:ring-pp-signal"
      >
        <QrCode className="h-5 w-5" aria-hidden />
      </button>
      {open && (
        <figure id={id} className="absolute bottom-full end-0 mb-2 flex w-36 flex-col items-center gap-1 bg-pp-chalk p-2 shadow-2xl">
          <button type="button" onClick={() => setOpen(false)} aria-label={t('common.close')} className="absolute end-0 top-0 flex h-8 w-8 items-center justify-center text-pp-night">
            <X className="h-3.5 w-3.5" aria-hidden />
          </button>
          <svg viewBox={`-2 -2 ${size + 4} ${size + 4}`} role="img" aria-label={t('qr.label')} className="mt-5 h-auto w-full" shapeRendering="crispEdges">
            <path d={d} fill="#0c0c0b" />
          </svg>
          <figcaption className="text-center font-display text-[10px] font-extrabold uppercase leading-tight tracking-broadcast text-pp-night">{t('qr.caption')}</figcaption>
        </figure>
      )}
    </div>
  );
};
