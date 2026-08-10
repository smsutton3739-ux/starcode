"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useTheme } from "./ThemeProvider";
import { getAccessToken, getCurrentUser, logout } from "@/lib/api";
import type { User } from "@/lib/types";
import { Logo } from "./Logo";

const NAV = [
  { href: "/dashboard", label: "My analyses" },
  { href: "/explore", label: "Explore" },
  { href: "/about", label: "How it works" },
];

export function SiteHeader() {
  const pathname = usePathname();
  const { resolved, toggle } = useTheme();
  const [user, setUser] = useState<User | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!getAccessToken()) return;
    getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null));
  }, [pathname]);

  // The homepage is the product's front door and is deliberately uncluttered, so the
  // header stays out of its way there.
  const minimal = pathname === "/";

  return (
    <header
      className={`no-print sticky top-0 z-40 border-b backdrop-blur ${
        minimal
          ? "border-transparent bg-white/70 dark:bg-slate-950/70"
          : "border-slate-200 bg-white/90 dark:border-slate-800 dark:bg-slate-950/90"
      }`}
    >
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4">
        <Link
          href="/"
          className="flex items-center gap-2 font-semibold tracking-tight"
          aria-label="Starcode home"
        >
          <Logo className="h-7 w-7" />
          <span className={minimal ? "sr-only sm:not-sr-only" : ""}>Starcode</span>
        </Link>

        <nav aria-label="Main" className="ml-auto hidden items-center gap-1 md:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={pathname === item.href ? "page" : undefined}
              className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
                pathname === item.href
                  ? "bg-slate-100 font-medium text-slate-900 dark:bg-slate-800 dark:text-slate-100"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className={`flex items-center gap-2 ${minimal ? "ml-auto md:ml-0" : ""}`}>
          <button
            type="button"
            onClick={toggle}
            className="btn-ghost h-9 w-9 !px-0"
            aria-label={`Switch to ${resolved === "dark" ? "light" : "dark"} mode`}
            title={`Switch to ${resolved === "dark" ? "light" : "dark"} mode`}
          >
            <span aria-hidden="true">{resolved === "dark" ? "☀" : "☾"}</span>
          </button>

          {user ? (
            <div className="relative">
              <button
                type="button"
                onClick={() => setMenuOpen((open) => !open)}
                className="btn-secondary h-9"
                aria-expanded={menuOpen}
                aria-haspopup="menu"
              >
                <span className="max-w-[10rem] truncate">
                  {user.display_name || user.email}
                </span>
              </button>
              {menuOpen && (
                <div
                  role="menu"
                  className="card absolute right-0 mt-2 w-52 animate-fade-in p-1 text-sm"
                >
                  <Link
                    href="/dashboard"
                    role="menuitem"
                    className="block rounded px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-800"
                    onClick={() => setMenuOpen(false)}
                  >
                    Dashboard
                  </Link>
                  {user.role === "admin" && (
                    <Link
                      href="/admin"
                      role="menuitem"
                      className="block rounded px-3 py-2 hover:bg-slate-100 dark:hover:bg-slate-800"
                      onClick={() => setMenuOpen(false)}
                    >
                      Admin
                    </Link>
                  )}
                  <button
                    type="button"
                    role="menuitem"
                    className="block w-full rounded px-3 py-2 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                    onClick={async () => {
                      await logout();
                      setUser(null);
                      setMenuOpen(false);
                      window.location.href = "/";
                    }}
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <Link href="/login" className="btn-secondary h-9">
              Sign in
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
