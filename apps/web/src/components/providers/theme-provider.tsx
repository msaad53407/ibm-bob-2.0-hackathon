"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * Class-based dark mode (`:is(.dark *)` variant in globals.css).
 * Defaults to the OS preference; the choice persists in localStorage.
 * Must wrap the app so `useTheme()` (Toaster, ThemeToggle) resolves.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
