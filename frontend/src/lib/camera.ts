// Broadcast camera presets for the pitch view: wide, tactical (tilted) and follow ball.
export type CameraPreset = 'wide' | 'tactical' | 'follow';
export const CAMERA_PRESETS: CameraPreset[] = ['wide', 'tactical', 'follow'];
export const CAMERA_STORAGE_KEY = 'pp.camera';

export const isCameraPreset = (v: unknown): v is CameraPreset =>
  typeof v === 'string' && (CAMERA_PRESETS as string[]).includes(v);

/** Deep link (?cam=) wins, then the viewer's saved choice, then wide. */
export function initialCamera(search: string = typeof window !== 'undefined' ? window.location.search : ''): CameraPreset {
  const fromUrl = new URLSearchParams(search).get('cam');
  if (isCameraPreset(fromUrl)) return fromUrl;
  try {
    const saved = window.localStorage.getItem(CAMERA_STORAGE_KEY);
    if (isCameraPreset(saved)) return saved;
  } catch {
    /* storage blocked: fall back to the default */
  }
  return 'wide';
}

export function saveCamera(cam: CameraPreset): void {
  try {
    window.localStorage.setItem(CAMERA_STORAGE_KEY, cam);
  } catch {
    /* storage blocked: the choice lasts for this visit only */
  }
}
