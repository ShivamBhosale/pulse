import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type Theme = "dark" | "light";

interface ThemeCtx {
  theme: Theme;
  toggle: () => void;
}

const Ctx = createContext<ThemeCtx>({ theme: "dark", toggle: () => {} });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(
    () => (document.documentElement.dataset.theme as Theme | undefined) ?? "dark",
  );
  const toggle = useCallback(() => {
    setTheme((t) => {
      const next: Theme = t === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      document.querySelector('meta[name="theme-color"]')?.setAttribute("content", next === "dark" ? "#0e1014" : "#f4f3ef");
      try {
        localStorage.setItem("pulse-theme", next);
      } catch {
        /* private mode */
      }
      return next;
    });
  }, []);
  const value = useMemo(() => ({ theme, toggle }), [theme, toggle]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export const useTheme = () => useContext(Ctx);

/** Resolved CSS custom properties for chart options (re-read whenever the theme changes). */
export interface Palette {
  surface: string;
  line: string;
  grid: string;
  axis: string;
  ink: string;
  ink2: string;
  muted: string;
  accent: string;
  accentSoft: string;
  bandSleep: string;
  bandWorkout: string;
  zones: [string, string, string];
  stage: Record<"DEEP" | "LIGHT" | "REM" | "AWAKE", string>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function readPalette(): Palette {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string) => css.getPropertyValue(name).trim();
  return {
    surface: v("--surface"),
    line: v("--line"),
    grid: v("--grid"),
    axis: v("--axis"),
    ink: v("--ink"),
    ink2: v("--ink-2"),
    muted: v("--ink-muted"),
    accent: v("--accent"),
    accentSoft: v("--accent-soft"),
    bandSleep: v("--band-sleep"),
    bandWorkout: v("--band-workout"),
    zones: [v("--zone-1"), v("--zone-2"), v("--zone-3")],
    stage: { DEEP: v("--stage-deep"), LIGHT: v("--stage-light"), REM: v("--stage-rem"), AWAKE: v("--stage-awake") },
  };
}

// eslint-disable-next-line react-refresh/only-export-components
export function usePalette(): Palette {
  const { theme } = useTheme();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => readPalette(), [theme]);
}
