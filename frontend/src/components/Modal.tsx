// One accessible modal for the replay and the recap: focus moves in, Tab stays inside,
// Esc and the browser Back button close it, focus goes back to whatever opened it, and the
// page behind does not scroll. The dialog is labelled by its own title.
import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../i18n';
import { cx } from './ui';

const FOCUSABLE = 'button:not([disabled]), a[href], select:not([disabled]), input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Lets the browser Back button close an open layer instead of leaving the app. */
export function useBackToClose(open: boolean, onClose: () => void, key: string) {
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!open) return;
    const marker = { pitchpulseLayer: key };
    try {
      window.history.pushState(marker, '', window.location.href);
    } catch {
      return;
    }
    let poppedByBack = false;
    const onPop = () => {
      poppedByBack = true;
      close.current();
    };
    window.addEventListener('popstate', onPop);
    return () => {
      window.removeEventListener('popstate', onPop);
      // Closed from inside (Esc, X, backdrop): take our history entry back off.
      const state = window.history.state as { pitchpulseLayer?: string } | null;
      if (!poppedByBack && state?.pitchpulseLayer === key) window.history.back();
    };
  }, [open, key]);
}

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** id of the element that names the dialog (its visible title). */
  labelledBy: string;
  /** Short name for the browser history entry. */
  name: string;
  className?: string;
  children: React.ReactNode;
}

export const Modal: React.FC<ModalProps> = ({ open, onClose, labelledBy, name, className, children }) => {
  const { dir } = useI18n();
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useBackToClose(open, onClose, name);

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const first = panel.current?.querySelector<HTMLElement>('[data-autofocus]') ?? panel.current?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? panel.current)?.focus();
    const body = document.body;
    const before = body.style.overflow;
    body.style.overflow = 'hidden';
    return () => {
      body.style.overflow = before;
      const back = opener.current;
      if (back && document.contains(back)) back.focus();
    };
  }, [open]);

  if (!open) return null;

  const onKeyDown = (e: React.KeyboardEvent) => {
    // Keys from a layer portalled on top (e.g. "Show your working") belong to that layer.
    if (e.defaultPrevented || !panel.current?.contains(e.target as Node)) return;
    if (e.key === 'Escape') {
      e.stopPropagation();
      onCloseRef.current();
      return;
    }
    if (e.key !== 'Tab' || !panel.current) return;
    const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => !el.closest('[aria-hidden="true"]'));
    if (!items.length) {
      e.preventDefault();
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === first || !panel.current.contains(active))) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && (active === last || !panel.current.contains(active))) {
      e.preventDefault();
      first.focus();
    }
  };

  return createPortal(
    <div
      dir={dir}
      className="fixed inset-0 z-50 flex animate-fade-in items-start justify-center overflow-y-auto bg-black/80 p-0 backdrop-blur-sm sm:items-center sm:p-4"
      onClick={() => onCloseRef.current()}
      onKeyDown={onKeyDown}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className={cx('relative w-full focus:outline-none sm:my-auto', className)}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
};
