/**
 * Reads the real stylesheet and checks that every text and background pairing is readable in both
 * themes, to WCAG AA. Changing a colour that breaks this fails the build.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { applyTheme, resolveTheme, saveTheme, storedTheme } from "./lib/theme";

const css = readFileSync(resolve(__dirname, "index.css"), "utf8");

function tokens(block: string): Record<string, string> {
  return Object.fromEntries(
    [...block.matchAll(/--color-([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1]!, m[2]!]),
  );
}

const dark = tokens(css.slice(css.indexOf("@theme {"), css.indexOf(':root[data-theme="light"]')));
const light = { ...dark, ...tokens(css.slice(css.indexOf(':root[data-theme="light"]'))) };

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const v = parseInt(hex.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

// [text, background, minimum]. 4.5 is AA for normal text; 3 is for icons and large shapes.
const PAIRS: [string, string, number][] = [
  ["ink", "canvas", 4.5],
  ["ink", "surface", 4.5],
  ["ink", "raised", 4.5],
  ["ink-muted", "surface", 4.5],
  ["ink-muted", "raised", 4.5],
  ["ink-subtle", "canvas", 4.5],
  ["ink-subtle", "surface", 4.5],
  ["ink-subtle", "raised", 4.5],
  ["brand", "surface", 4.5],
  ["brand", "canvas", 4.5],
  ["brand", "brand-soft", 4.5],
  ["brand-ink", "brand", 4.5],
  ["brand-ink", "brand-hover", 4.5],
  ["ink", "brand-soft", 4.5],
  ["accent", "surface", 4.5],
  ["accent", "accent-soft", 4.5],
  ["ink-muted", "accent-soft", 4.5],
  ["danger", "surface", 4.5],
  ["danger", "danger-soft", 4.5],
  ["canvas", "danger", 4.5],
  ["chart-neutral", "surface", 2],
];

describe.each([
  ["dark", dark],
  ["light", light],
])("%s theme", (_name, palette) => {
  it.each(PAIRS)("%s on %s is readable", (text, background, minimum) => {
    expect(palette[text], text).toBeDefined();
    expect(palette[background], background).toBeDefined();
    expect(contrast(palette[text]!, palette[background]!)).toBeGreaterThanOrEqual(minimum);
  });
});

function mix(color: string, base: string, share: number): string {
  const channel = (hex: string, i: number) => parseInt(hex.slice(i, i + 2), 16);
  return (
    "#" +
    [1, 3, 5]
      .map((i) => Math.round(channel(color, i) * share + channel(base, i) * (1 - share)))
      .map((v) => v.toString(16).padStart(2, "0"))
      .join("")
  );
}

// Students pick any course color. Badges, calendar sessions and course marks put ink text on a wash
// of that color, at most 30% strong (exam deadlines), so check the most extreme colors on every surface.
describe.each([
  ["dark", dark],
  ["light", light],
])("course color washes in the %s theme", (_name, palette) => {
  const extremes = ["#000000", "#ffffff", "#ff0000", "#00ff00", "#0000ff", "#ffff00", "#ff00ff", "#00ffff"];
  it.each(extremes)("ink stays readable on a wash of %s", (color) => {
    for (const base of ["canvas", "surface", "raised"]) {
      const wash = mix(color, palette[base]!, 0.3);
      expect(contrast(palette.ink!, wash), `${color} over ${base}`).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("theme choice", () => {
  afterEach(() => {
    delete document.documentElement.dataset.theme;
    vi.unstubAllGlobals();
  });

  function prefersDark(dark: boolean) {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("dark") ? dark : !dark,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
  }

  it("follows the system by default", () => {
    prefersDark(false);
    expect(storedTheme()).toBe("system");
    expect(resolveTheme("system")).toBe("light");
    prefersDark(true);
    expect(resolveTheme("system")).toBe("dark");
  });

  it("an explicit choice wins over the system and is remembered", () => {
    prefersDark(true);
    saveTheme("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(storedTheme()).toBe("light");
    saveTheme("dark");
    expect(document.documentElement.dataset.theme).toBeUndefined();
    saveTheme("system");
    expect(localStorage.getItem("coursepilot.theme")).toBeNull();
  });

  it("the early script in index.html agrees with the app", () => {
    const html = readFileSync(resolve(__dirname, "../index.html"), "utf8");
    expect(html).toContain('localStorage.getItem("coursepilot.theme")');
    prefersDark(false);
    applyTheme("system");
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
