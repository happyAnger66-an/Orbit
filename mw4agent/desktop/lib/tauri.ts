/**
 * Detect Tauri desktop shell (no dependency on @tauri-apps/api).
 * Safe for SSR: returns false when `window` is undefined.
 */
export function isTauri(): boolean {
  if (typeof window === "undefined") return false;
  const w = window as Window & {
    __TAURI__?: unknown;
    __TAURI_INTERNALS__?: unknown;
    __TAURI_METADATA__?: unknown;
  };
  return Boolean(w.__TAURI__ || w.__TAURI_INTERNALS__ || w.__TAURI_METADATA__);
}
