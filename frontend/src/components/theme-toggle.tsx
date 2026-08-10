"use client";

import { useEffect, useState } from "react";
import { useTheme } from "./theme-provider";
import { MoonIcon, SunIcon } from "./icons";
import { cx } from "./ui";

export function ThemeToggle({
  className,
  showLabel = false,
}: {
  className?: string;
  showLabel?: boolean;
}) {
  const { theme, toggle } = useTheme();

  // The real theme is only known after mount (the inline script sets it before
  // paint, but the server rendered with no knowledge of it). Rendering a
  // neutral placeholder first avoids a hydration mismatch and a visible icon
  // flip.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const dark = mounted && theme === "dark";

  return (
    <button
      onClick={toggle}
      title={dark ? "Switch to light" : "Switch to dark"}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className={cx(
        "group relative flex items-center justify-center rounded-[10px]",
        "text-ink-faint transition-colors hover:bg-raised hover:text-ink",
        showLabel ? "h-9 w-full gap-2.5 px-2" : "size-9",
        className,
      )}
    >
      <span className="relative flex size-[18px] items-center justify-center">
        {/* Both icons are always mounted and cross-fade, so the swap reads as
            one control changing state rather than two different buttons. */}
        <SunIcon
          className={cx(
            "absolute size-[18px] transition-all duration-300",
            mounted && !dark
              ? "rotate-0 scale-100 opacity-100"
              : "-rotate-90 scale-50 opacity-0",
          )}
        />
        <MoonIcon
          className={cx(
            "absolute size-[18px] transition-all duration-300",
            dark
              ? "rotate-0 scale-100 opacity-100"
              : "rotate-90 scale-50 opacity-0",
          )}
        />
      </span>
      {showLabel && (
        <span className="flex-1 text-left text-[13px] font-medium text-ink">
          {dark ? "Light mode" : "Dark mode"}
        </span>
      )}
    </button>
  );
}
