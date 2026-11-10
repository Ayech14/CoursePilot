import { LogOut, Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../../features/auth/AuthContext";
import { Logo } from "../ui/Logo";
import { NAV_ITEMS } from "./navigation";

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth();
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center px-5">
        <Logo />
      </div>
      <nav aria-label="Main" className="flex-1 space-y-1 px-3 py-2">
        {NAV_ITEMS.map(({ to, label, icon: Icon, plannedMilestone }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-raised text-ink"
                  : "text-ink-muted hover:bg-raised/60 hover:text-ink"
              }`
            }
          >
            <Icon aria-hidden="true" className="size-4.5 shrink-0" />
            <span className="flex-1">{label}</span>
            {plannedMilestone && (
              <span className="text-xs font-normal text-ink-subtle">Soon</span>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="flex items-center gap-2 border-t border-line p-3">
        <div className="min-w-0 flex-1 px-2">
          <p className="truncate text-sm font-medium">{user?.display_name}</p>
          <p className="truncate text-xs text-ink-subtle">{user?.email}</p>
        </div>
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
            className="absolute inset-0 bg-black/60"
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
        <Outlet />
      </main>
    </div>
  );
}
