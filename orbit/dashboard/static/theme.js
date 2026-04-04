/**
 * Dashboard theme: light, dark, soft-dark.
 * Stored in localStorage (key: orbit-dashboard-theme).
 */

const STORAGE_KEY = "orbit-dashboard-theme";
const THEMES = ["light", "dark", "soft-dark"];

function detectTheme() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (THEMES.includes(stored)) return stored;
  if (typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)")?.matches) {
    return "soft-dark";
  }
  return "light";
}

let currentTheme = detectTheme();

export function getTheme() {
  return currentTheme;
}

export function setTheme(theme) {
  if (!THEMES.includes(theme)) return;
  currentTheme = theme;
  localStorage.setItem(STORAGE_KEY, theme);
}

export function applyTheme() {
  document.documentElement.setAttribute("data-theme", currentTheme);
  document.documentElement.setAttribute("color-scheme", currentTheme === "light" ? "light" : "dark");
}

export function getThemes() {
  return THEMES;
}
