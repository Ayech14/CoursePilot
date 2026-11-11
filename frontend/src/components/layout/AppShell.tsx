import { LogOut, Menu, Moon, Sun, X } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../../features/auth/AuthContext";
import { TimerBar } from "../../features/timer/TimerBar";
import { resolveTheme } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";
import { ErrorBoundary } from "../ui/ErrorBoundary";
import { Logo } from "../ui/Logo";
import { NAV_ITEMS } from "./navigation";

function ThemeToggle() {
  const [choice, setChoice] = useTheme();
  const dark = resolveTheme(choice) === "dark";
  const Icon = dark ? Sun : Moon;
  const label = dark ? "Switch to light theme" : "Switch to dark theme";
  return (
    <button
      type="button"
      onClick={() => setChoice(dark ? "light" : "dark")}
      aria-label={label}
      title={label}
      className="flex size-9 shrink-0 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-raised hover:text-ink"
    >
      <Icon aria-hidden="true" className="size-4.5" />
    </button>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => [...part][0]!.toUpperCase()).join("") || "?";
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth();
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center px-5">
        <Logo />
      </div>
      <nav aria-label="Main" className="flex-1 space-y-1 px-3 py-2">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) =>
              `group flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-brand-soft text-ink [&>svg]:text-brand"
                  : "text-ink-muted hover:bg-raised hover:text-ink"
              }`
            }
          >
            <Icon aria-hidden="true" className="size-4.5 shrink-0" />
            <span className="flex-1">{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="flex items-center gap-2 border-t border-line p-3">
        <span
          aria-hidden="true"
          className="ml-1 flex size-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-soft to-accent-soft text-sm font-semibold text-ink ring-1 ring-line"
        >
          {initials(user?.display_name ?? "")}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{user?.display_name}</p>
          <p className="truncate text-xs text-ink-subtle">{user?.email}</p>
        </div>
        <ThemeToggle />
        <button
          type="button"
          onClick={() => void logout()}
          aria-label="Sign out"
          title="Sign out"
          className="flex size-9 shrink-0 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-raised hover:text-ink"
        >
          <LogOut aria-hidden="true" className="size-4.5" />
        </button>
      </div>
    </div>
  );
}

export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => {
    if (!drawerOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [drawerOpen]);

  const currentLabel = NAV_ITEMS.find((item) => pathname.startsWith(item.to))?.label;

  return (
    <div className="min-h-dvh lg:pl-64">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-line bg-surface lg:block">
        <SidebarContent />
      </aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            aria-hidden="true"
            className="absolute inset-0 bg-overlay backdrop-blur-[2px]"
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85vw] border-r border-line bg-surface">
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              aria-label="Close menu"
              className="absolute top-3.5 right-3 flex size-9 items-center justify-center rounded-lg text-ink-muted hover:bg-raised"
            >
              <X aria-hidden="true" className="size-5" />
            </button>
            <SidebarContent onNavigate={() => setDrawerOpen(false)} />
          </aside>
        </div>
      )}

      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface px-4 lg:hidden">
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          aria-label="Open menu"
          className="flex size-9 items-center justify-center rounded-lg text-ink-muted hover:bg-raised"
        >
          <Menu aria-hidden="true" className="size-5" />
        </button>
        <span className="text-sm font-semibold">{currentLabel ?? "CoursePilot"}</span>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-8 lg:py-10">
        <ErrorBoundary resetKey={pathname}>
          <TimerBar />
          <div key={pathname} className="page-enter">
            <Outlet />
          </div>
        </ErrorBoundary>
      </main>
    </div>
  );
}
