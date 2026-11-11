/**
 * The colour theme. Stored on this device only: it is a display preference, not account data, and
 * keeping it local lets the page pick it before anything is drawn (see index.html).
 */
export type ThemeChoice = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "coursepilot.theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

export function storedTheme(): ThemeChoice {
  const value = localStorage.getItem(THEME_STORAGE_KEY);
  return value === "light" || value === "dark" ? value : "system";
}

export function resolveTheme(choice: ThemeChoice): "light" | "dark" {
  if (choice !== "system") return choice;
  return window.matchMedia?.(DARK_QUERY).matches === false ? "light" : "dark";
}

export function applyTheme(choice: ThemeChoice): void {
  const resolved = resolveTheme(choice);
  if (resolved === "light") document.documentElement.dataset.theme = "light";
  else delete document.documentElement.dataset.theme;
}

export function saveTheme(choice: ThemeChoice): void {
  if (choice === "system") localStorage.removeItem(THEME_STORAGE_KEY);
  else localStorage.setItem(THEME_STORAGE_KEY, choice);
  applyTheme(choice);
}

/** Follows the operating system while the choice is "system". Returns a function that stops. */
export function followSystemTheme(getChoice: () => ThemeChoice): () => void {
  const query = window.matchMedia?.(DARK_QUERY);
  if (!query) return () => {};
  const update = () => {
    if (getChoice() === "system") applyTheme("system");
  };
  query.addEventListener("change", update);
  return () => query.removeEventListener("change", update);
}
