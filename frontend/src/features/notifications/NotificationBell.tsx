import {
  Bell,
  CalendarClock,
  CalendarSync,
  CircleAlert,
  Clock,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Spinner } from "../../components/ui/Spinner";
import { formatAgo } from "../../lib/datetime";
import { useAuth } from "../auth/AuthContext";
import {
  useMarkAllRead,
  useMarkRead,
  useNotifications,
  type AppNotification,
  type NotificationKind,
} from "./api";

const LOOK: Record<NotificationKind, { icon: LucideIcon; tone: string }> = {
  deadline_approaching: { icon: CalendarClock, tone: "bg-accent-soft text-accent" },
  task_overdue: { icon: TriangleAlert, tone: "bg-danger-soft text-danger" },
  task_unfinished: { icon: Clock, tone: "bg-accent-soft text-accent" },
  schedule_adjusted: { icon: CalendarSync, tone: "bg-brand-soft text-brand" },
  workload_conflict: { icon: CircleAlert, tone: "bg-danger-soft text-danger" },
};

/** Where a notification takes the student when they open it. */
export function destinationFor(item: AppNotification): string {
  if (item.kind === "schedule_adjusted" || item.kind === "task_unfinished") return "/schedule";
  if (item.kind === "workload_conflict" && item.task_id === null) return "/availability";
  if (item.kind === "workload_conflict") return "/schedule";
  return "/tasks";
}

function Item({ item, zone, onOpen }: { item: AppNotification; zone: string; onOpen: () => void }) {
  const { icon: Icon, tone } = LOOK[item.kind];
  const unread = item.read_at === null;
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full gap-3 px-4 py-3 text-left transition-colors hover:bg-raised"
      >
        <span className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full ${tone}`}>
          <Icon aria-hidden="true" className="size-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-start justify-between gap-2">
            <span className={`text-sm ${unread ? "font-semibold" : "font-medium text-ink-muted"}`}>
              {item.title}
            </span>
            {unread && (
              <span className="mt-1.5 size-2 shrink-0 rounded-full bg-brand">
                <span className="sr-only">Unread</span>
              </span>
            )}
          </span>
          <span className="mt-0.5 block text-xs text-ink-muted">{item.body}</span>
          <span className="mt-1 block text-[0.6875rem] text-ink-subtle">{formatAgo(item.created_at, zone)}</span>
        </span>
      </button>
    </li>
  );
}

/**
 * The bell and its panel. `placement` says where the panel opens: beside the desktop sidebar,
 * or below the phone header.
 */
export function NotificationBell({ placement }: { placement: "sidebar" | "header" }) {
  const zone = useAuth().user!.timezone;
  const notifications = useNotifications();
  const markRead = useMarkRead();
  const markAll = useMarkAllRead();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const unread = notifications.data?.unread ?? 0;

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !root.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  function openItem(item: AppNotification) {
    if (item.read_at === null) markRead.mutate(item.id);
    setOpen(false);
    navigate(destinationFor(item));
  }

  const label = unread > 0 ? `Notifications, ${unread} unread` : "Notifications";
  const panelPosition =
    placement === "sidebar" ? "fixed top-3 left-[calc(var(--sidebar-width)+0.5rem)] w-96" : "fixed inset-x-2 top-16";

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label={label}
        aria-expanded={open}
        aria-haspopup="dialog"
        title="Notifications"
        className="relative flex size-9 shrink-0 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-raised hover:text-ink"
      >
        <Bell aria-hidden="true" className="size-4.5" />
        {unread > 0 && (
          <span
            aria-hidden="true"
            className="absolute top-1 right-1 flex min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[0.625rem] leading-4 font-semibold text-canvas"
          >
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Notifications"
          className={`${panelPosition} z-50 flex max-h-[min(36rem,calc(100dvh-5rem))] flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-lift)]`}
        >
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <h2 className="text-sm font-semibold">Notifications</h2>
            {unread > 0 && (
              <button
                type="button"
                onClick={() => markAll.mutate()}
                disabled={markAll.isPending}
                className="text-xs font-medium text-brand hover:underline disabled:opacity-60"
              >
                Mark all as read
              </button>
            )}
          </div>
          <div className="overflow-y-auto overscroll-contain">
            {notifications.isPending ? (
              <div role="status" className="flex justify-center py-10 text-ink-muted">
                <Spinner />
                <span className="sr-only">Loading</span>
              </div>
            ) : notifications.isError ? (
              <p role="alert" className="px-4 py-8 text-center text-sm text-ink-muted">
                Notifications could not be loaded. {notifications.error.message}
              </p>
            ) : notifications.data.items.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <span className="mx-auto flex size-10 items-center justify-center rounded-full bg-brand-soft text-brand">
                  <Bell aria-hidden="true" className="size-5" />
                </span>
                <p className="mt-3 text-sm font-medium">You're all caught up</p>
                <p className="mt-1 text-xs text-ink-muted">
                  Approaching deadlines, missed sessions and schedule changes show up here.
                </p>
              </div>
            ) : (
              <ul className="divide-y divide-line">
                {notifications.data.items.map((item) => (
                  <Item key={item.id} item={item} zone={zone} onOpen={() => openItem(item)} />
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
