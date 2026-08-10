"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";
import { MicIcon } from "./icons";
import { ThemeToggle } from "./theme-toggle";
import { Button, cx } from "./ui";

export function MarketingNav() {
  const [user, setUser] = useState<User | null>(null);
  const [checked, setChecked] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  // The auth cookie is HttpOnly, so the only way to know whether someone is
  // signed in is to ask. A failure here just means "logged out".
  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecked(true));
  }, []);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cx(
        "sticky top-0 z-50 transition-all duration-200",
        scrolled
          ? "border-b border-line bg-paper/85 backdrop-blur-md"
          : "border-b border-transparent",
      )}
    >
      <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="flex size-7 items-center justify-center rounded-lg bg-ink text-paper">
            <MicIcon className="size-3.5" />
          </span>
          <span className="font-serif text-[15px] text-ink">Study Coach</span>
        </Link>

        <div className="flex items-center gap-1.5">
          <a
            href="#how"
            className="hidden rounded-lg px-3 py-2 text-[13px] text-ink-soft transition-colors hover:bg-raised hover:text-ink sm:block"
          >
            How it works
          </a>
          <a
            href="#why"
            className="hidden rounded-lg px-3 py-2 text-[13px] text-ink-soft transition-colors hover:bg-raised hover:text-ink sm:block"
          >
            Why it works
          </a>

          <ThemeToggle className="mx-1" />

          {/* Nothing renders until the auth check settles, so the button never
              flips from "Sign in" to "Go to library" in front of the user. */}
          {checked &&
            (user ? (
              <Link href="/library">
                <Button size="sm">Go to your library</Button>
              </Link>
            ) : (
              <>
                <Link href="/login">
                  <Button size="sm" variant="ghost">
                    Sign in
                  </Button>
                </Link>
                <Link href="/signup">
                  <Button size="sm">Get started</Button>
                </Link>
              </>
            ))}
        </div>
      </nav>
    </header>
  );
}
