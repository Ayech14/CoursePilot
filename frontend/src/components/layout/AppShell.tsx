import { LogOut, Menu, Moon, PanelLeftClose, PanelLeftOpen, Sun, X } from "lucide-react";
import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../../features/auth/AuthContext";
import { NotificationBell } from "../../features/notifications/NotificationBell";
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

const ICON_BUTTON =
  "flex size-9 shrink-0 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-raised hover:text-ink";

function SidebarContent({
  onNavigate,
  collapsed = false,
  onToggle,
}: {
  onNavigate?: () => void;
  collapsed?: boolean;
  onToggle?: () => void;
}) {
  const { user, logout } = useAuth();
  const ToggleIcon = collapsed ? PanelLeftOpen : PanelLeftClose;
  const toggleLabel = collapsed ? "Expand sidebar" : "Collapse sidebar";
  return (
    <div className="flex h-full flex-col">
      <div
        className={`flex items-center ${collapsed ? "flex-col justify-center gap-1 py-3.5" : "h-16 justify-between px-5 pr-3"}`}
      >
        {!collapsed && <Logo />}
        {onToggle && (
          <div className={`flex items-center gap-0.5 ${collapsed ? "flex-col-reverse" : ""}`}>
            <NotificationBell placement="sidebar" />
          <button
            type="button"
            onClick={onToggle}
            aria-label={toggleLabel}
            aria-expanded={!collapsed}
            title={`${toggleLabel} (Ctrl or ⌘ + \\)`}
            className={ICON_BUTTON}
          >
            <ToggleIcon aria-hidden="true" className="size-4.5" />
          </button>
          </div>
        )}
      </div>
      <nav aria-label="Main" className={`flex-1 space-y-1 py-2 ${collapsed ? "px-2.5" : "px-3"}`}>
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              `group flex h-10 items-center gap-3 rounded-lg text-sm font-medium transition-colors ${
                collapsed ? "justify-center" : "px-3"
              } ${
                isActive
                  ? "bg-brand-soft text-ink [&>svg]:text-brand"
                  : "text-ink-muted hover:bg-raised hover:text-ink"
              }`
            }
          >
            <Icon aria-hidden="true" className="size-4.5 shrink-0" />
            <span className={collapsed ? "sr-only" : "flex-1"}>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div
        className={`flex items-center gap-2 border-t border-line p-3 ${collapsed ? "flex-col" : ""}`}
      >
        <span
          aria-hidden="true"
          title={collapsed ? user?.display_name : undefined}
          className={`flex size-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-soft to-accent-soft text-sm font-semibold text-ink ring-1 ring-line ${collapsed ? "" : "ml-1"}`}
        >
          {initials(user?.display_name ?? "")}
        </span>
        <div className={collapsed ? "sr-only" : "min-w-0 flex-1"}>
          <p className="truncate text-sm font-medium">{user?.display_name}</p>
          <p className="truncate text-xs text-ink-subtle">{user?.email}</p>
        </div>
        <ThemeToggle />
        <button
          type="button"
          onClick={() => void logout()}
          aria-label="Sign out"
          title="Sign out"
          className={ICON_BUTTON}
        >
          <LogOut aria-hidden="true" className="size-4.5" />
        </button>
      </div>
    </div>
  );
}

const SIDEBAR_STORAGE_KEY = "coursepilot.sidebar";

/** Whether the desktop sidebar is folded down to icons. Remembered on this device. */
function useCollapsedSidebar(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(SIDEBAR_STORAGE_KEY) === "collapsed");
  const toggle = useCallback(() => {
    setCollapsed((current) => {
      const next = !current;
      if (next) localStorage.setItem(SIDEBAR_STORAGE_KEY, "collapsed");
      else localStorage.removeItem(SIDEBAR_STORAGE_KEY);
      return next;
    });
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "\\") {
        event.preventDefault();
        toggle();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [toggle]);

  return [collapsed, toggle];
}

export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, toggleCollapsed] = useCollapsedSidebar();
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
    <div
      style={{ "--sidebar-width": collapsed ? "4rem" : "16rem" } as CSSProperties}
      className={`min-h-dvh transition-[padding] duration-200 ${collapsed ? "lg:pl-16" : "lg:pl-64"}`}
    >
      <aside
        className={`fixed inset-y-0 left-0 z-30 hidden border-r border-line bg-surface transition-[width] duration-200 lg:block ${
          collapsed ? "w-16" : "w-64"
        }`}
      >
        <SidebarContent collapsed={collapsed} onToggle={toggleCollapsed} />
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
        <div className="ml-auto">
          <NotificationBell placement="header" />
        </div>
      </header>

      <main className={`mx-auto px-4 py-8 sm:px-8 lg:py-10 ${collapsed ? "max-w-7xl" : "max-w-6xl"}`}>
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
