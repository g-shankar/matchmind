// Read-aloud with the browser's own Web Speech API (speechSynthesis): no server,
// no account, nothing leaves the device. Off by default. It speaks only in a
// language the browser has a voice for, and never in capture mode (OBS / vMix
// Browser Source), where sound would go out on air.
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';

const PREF_KEY = 'pitchpulse.readAloud';

export function captureMode(search = typeof window === 'undefined' ? '' : window.location.search): boolean {
  try {
    return new URLSearchParams(search).get('capture') === '1';
  } catch {
    return false;
  }
}

function synth(): SpeechSynthesis | null {
  try {
    return typeof window !== 'undefined' && 'speechSynthesis' in window && typeof SpeechSynthesisUtterance !== 'undefined'
      ? window.speechSynthesis
      : null;
  } catch {
    return null;
  }
}

export const speechSupported = () => synth() !== null && !captureMode();

/** The best voice for a language code ('ar', 'es', 'zh-Hans'): an exact region-free match first, then any regional one. */
export function voiceFor(lang: string, voices: readonly Pick<SpeechSynthesisVoice, 'lang' | 'localService' | 'default'>[]) {
  const base = lang.toLowerCase().split('-')[0];
  const matching = voices.filter((v) => (v.lang || '').toLowerCase().replace('_', '-').split('-')[0] === base);
  if (!matching.length) return null;
  return [...matching].sort((a, b) => Number(b.localService) - Number(a.localService) || Number(b.default) - Number(a.default))[0];
}

function readPref(): boolean {
  try {
    return localStorage.getItem(PREF_KEY) === 'on';
  } catch {
    return false;
  }
}

function writePref(on: boolean) {
  try {
    localStorage.setItem(PREF_KEY, on ? 'on' : 'off');
  } catch {
    // Best effort only.
  }
}

// One switch for the whole page: the header toggle, the card reader and the answer button share it.
let enabledNow: boolean | null = null;
const listeners = new Set<() => void>();
const getEnabled = () => (enabledNow ??= readPref());
function setEnabledNow(on: boolean) {
  enabledNow = on;
  writePref(on);
  listeners.forEach((l) => l());
}
function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** Tests only: forget the remembered switch. */
export function resetReadAloudForTests() {
  enabledNow = null;
}

export interface ReadAloud {
  /** False when the browser has no speech synthesis, or in capture mode. */
  supported: boolean;
  enabled: boolean;
  setEnabled: (on: boolean) => void;
  /** Whether the browser has a voice for this language (voices can load late). */
  hasVoice: (lang: string) => boolean;
  /** Speaks plain text in `lang`, replacing anything still being read. Returns false when it did not. */
  speak: (text: string, lang: string) => boolean;
}

export function useReadAloud(): ReadAloud {
  const supported = speechSupported();
  const enabled = useSyncExternalStore(subscribe, getEnabled, () => false) && supported;
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>(() => synth()?.getVoices() ?? []);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  useEffect(() => {
    const s = synth();
    if (!s || !supported) return;
    const update = () => setVoices(s.getVoices());
    update();
    s.addEventListener?.('voiceschanged', update);
    return () => s.removeEventListener?.('voiceschanged', update);
  }, [supported]);

  // Stop talking when switched off or when the page goes away.
  useEffect(() => {
    if (!enabled) synth()?.cancel();
  }, [enabled]);

  const setEnabled = useCallback(
    (on: boolean) => {
      if (supported) setEnabledNow(on);
    },
    [supported],
  );

  const hasVoice = useCallback((lang: string) => voiceFor(lang, voices) !== null, [voices]);

  const speak = useCallback(
    (text: string, lang: string) => {
      const s = synth();
      if (!s || !enabledRef.current || captureMode() || !text.trim()) return false;
      const voice = voiceFor(lang, voices);
      if (!voice) return false;
      s.cancel();
      const u = new SpeechSynthesisUtterance(text.slice(0, 400));
      u.voice = voice as SpeechSynthesisVoice;
      u.lang = voice.lang || lang;
      s.speak(u);
      return true;
    },
    [voices],
  );

  return { supported, enabled, setEnabled, hasVoice, speak };
}
