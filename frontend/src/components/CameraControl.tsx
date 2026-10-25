import React, { useCallback, useRef, useState } from 'react';
import { CAMERA_PRESETS, initialCamera, saveCamera, type CameraPreset } from '../lib/camera';

/** The viewer's camera preset: ?cam= deep link, then their saved choice; changes are remembered. */
export function useCameraPreset(): [CameraPreset, (cam: CameraPreset) => void] {
  const [cam, setCam] = useState<CameraPreset>(() => initialCamera());
  const set = useCallback((next: CameraPreset) => {
    setCam(next);
    saveCamera(next);
  }, []);
  return [cam, set];
}
import { useI18n } from '../i18n';
import { cx } from './ui';

/** Compact segmented control (a radio group) for the pitch camera presets. */
export const CameraControl: React.FC<{
  value: CameraPreset;
  onChange: (cam: CameraPreset) => void;
  className?: string;
}> = ({ value, onChange, className }) => {
  const i18n = useI18n();
  const { t } = i18n;
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const onKey = (e: React.KeyboardEvent, i: number) => {
    const n = CAMERA_PRESETS.length;
    const fwd = i18n.dir === 'rtl' ? 'ArrowLeft' : 'ArrowRight';
    const back = i18n.dir === 'rtl' ? 'ArrowRight' : 'ArrowLeft';
    let next = -1;
    if (e.key === fwd || e.key === 'ArrowDown') next = (i + 1) % n;
    else if (e.key === back || e.key === 'ArrowUp') next = (i - 1 + n) % n;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = n - 1;
    if (next < 0) return;
    e.preventDefault();
    onChange(CAMERA_PRESETS[next]);
    refs.current[next]?.focus();
  };
  return (
    <div
      role="radiogroup"
      aria-label={t('camera.label')}
      dir={i18n.dir}
      data-testid="camera-control"
      className={cx('pp-cam-cut inline-flex items-stretch bg-black/80 p-0.5 backdrop-blur-sm', className)}
    >
      {CAMERA_PRESETS.map((cam, i) => {
        const on = cam === value;
        return (
          <button
            key={cam}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={on}
            aria-label={t(`camera.${cam}.aria`)}
            title={t(`camera.${cam}.aria`)}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(cam)}
            onKeyDown={(e) => onKey(e, i)}
            data-testid={`camera-${cam}`}
            className={cx(
              'min-h-[44px] min-w-[44px] px-3 font-display text-xs font-bold uppercase tracking-wider outline-none transition-colors focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-pp-signal motion-reduce:transition-none',
              on ? 'bg-pp-signal text-black' : 'text-slate-200 hover:bg-white/10',
            )}
          >
            {t(`camera.${cam}`)}
          </button>
        );
      })}
    </div>
  );
};
