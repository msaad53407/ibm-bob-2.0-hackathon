"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { RiSunLine, RiMoonLine, RiComputerLine } from "@remixicon/react";
import { Button } from "@/components/ui/button";

const ORDER = ["light", "dark", "system"] as const;
type Mode = (typeof ORDER)[number];

/** Header button cycling light → dark → system. */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  // next-themes recommended guard against hydration mismatch
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <Button variant="ghost" size="icon-xs" disabled aria-label="Toggle theme">
        <RiSunLine className="size-4" />
      </Button>
    );
  }

  const current: Mode = ORDER.includes(theme as Mode) ? (theme as Mode) : "system";
  const next = ORDER[(ORDER.indexOf(current) + 1) % ORDER.length];
  const Icon = current === "light" ? RiSunLine : current === "dark" ? RiMoonLine : RiComputerLine;

  return (
    <Button
      variant="ghost"
      size="icon-xs"
      onClick={() => setTheme(next)}
      aria-label={`Switch theme (now ${current})`}
      title={`Theme: ${current} — click for ${next}`}
    >
      <Icon className="size-4" />
    </Button>
  );
}
