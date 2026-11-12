import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { formatAgo } from "../../lib/datetime";
import { jsonResponse, stubApi } from "../../test/fakeServer";
import { renderApp } from "../../test/renderApp";
import type { AppNotification } from "./api";
import { destinationFor } from "./NotificationBell";

// Midday in Toronto, so "1h ago" never crosses midnight into "Yesterday" whenever the tests run.
const now = new Date("2026-11-11T17:00:00Z");
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now });
});
afterEach(() => {
  vi.useRealTimers();
});
const minutesAgo = (m: number) => new Date(now.getTime() - m * 60_000).toISOString();

const OVERDUE: AppNotification = {
  id: "n1",
  kind: "task_overdue",
  title: "Lab report is overdue",
  body: "It was due Wed, Feb 4 at 1:00 PM.",
  task_id: "t1",
  read_at: null,
  created_at: minutesAgo(5),
};
const UPDATE: AppNotification = {
  id: "n2",
  kind: "schedule_adjusted",
  title: "Your schedule needs an update",
  body: "2 suggested changes.",
  task_id: null,
  read_at: minutesAgo(1),
  created_at: minutesAgo(90),
};

function serve(items: AppNotification[]) {
  let list = items;
  return stubApi({
    "GET /notifications": () =>
      jsonResponse(200, { items: list, unread: list.filter((n) => n.read_at === null).length }),
    "POST /notifications/n1/read": () => {
      list = list.map((n) => (n.id === "n1" ? { ...n, read_at: now.toISOString() } : n));
      return jsonResponse(200, list[0]);
    },
    "POST /notifications/read-all": () => {
      list = list.map((n) => ({ ...n, read_at: n.read_at ?? now.toISOString() }));
      return new Response(null, { status: 204 });
    },
    "GET /tasks": () => jsonResponse(200, { items: [], total: 0 }),
    "GET /courses": () => jsonResponse(200, []),
    "GET /deadline-suggestions": () => jsonResponse(200, []),
    "GET /dashboard": () => jsonResponse(500, {}),
  });
}

describe("notification bell", () => {
  it("shows the unread count and lists notifications, newest first, with how long ago", async () => {
    serve([OVERDUE, UPDATE]);
    renderApp("/dashboard");
    const [bell] = await screen.findAllByRole("button", { name: "Notifications, 1 unread" });
    await userEvent.setup().click(bell!);

    const panel = within(screen.getByRole("dialog", { name: "Notifications" }));
    const rows = panel.getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Lab report is overdue");
    expect(rows[0]).toHaveTextContent("Unread");
    expect(rows[0]).toHaveTextContent("5m ago");
    expect(rows[1]).not.toHaveTextContent("Unread");
    expect(rows[1]).toHaveTextContent("1h ago");
  });

  it("marks one read and takes the student to it", async () => {
    const mock = serve([OVERDUE, UPDATE]);
    renderApp("/dashboard");
    const user = userEvent.setup();
    const [bell] = await screen.findAllByRole("button", { name: "Notifications, 1 unread" });
    await user.click(bell!);
    await user.click(screen.getByRole("button", { name: /Lab report is overdue/ }));

    await waitFor(() => expect(mock.mock.calls.some(([url]) => url === "/api/v1/notifications/n1/read")).toBe(true));
    expect(await screen.findByRole("heading", { name: "Tasks" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Notifications" })).not.toBeInTheDocument();
    expect((await screen.findAllByRole("button", { name: "Notifications" })).length).toBeGreaterThan(0);
  });

  it("marks all as read", async () => {
    const mock = serve([OVERDUE, { ...UPDATE, id: "n3", read_at: null }]);
    renderApp("/dashboard");
    const user = userEvent.setup();
    const [bell] = await screen.findAllByRole("button", { name: "Notifications, 2 unread" });
    await user.click(bell!);
    await user.click(screen.getByRole("button", { name: "Mark all as read" }));
    await waitFor(() =>
      expect(mock.mock.calls.some(([url]) => url === "/api/v1/notifications/read-all")).toBe(true),
    );
    expect((await screen.findAllByRole("button", { name: "Notifications" })).length).toBeGreaterThan(0);
  });

  it("says when there is nothing, and closes with Escape", async () => {
    serve([]);
    renderApp("/dashboard");
    const user = userEvent.setup();
    const [bell] = await screen.findAllByRole("button", { name: "Notifications" });
    await user.click(bell!);
    expect(screen.getByText("You're all caught up")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Notifications" })).not.toBeInTheDocument();
  });

  it("sends each kind somewhere useful", () => {
    expect(destinationFor(OVERDUE)).toBe("/tasks");
    expect(destinationFor(UPDATE)).toBe("/schedule");
    expect(destinationFor({ ...OVERDUE, kind: "task_unfinished" })).toBe("/schedule");
    expect(destinationFor({ ...OVERDUE, kind: "workload_conflict" })).toBe("/schedule");
    expect(destinationFor({ ...OVERDUE, kind: "workload_conflict", task_id: null })).toBe("/availability");
    expect(destinationFor({ ...OVERDUE, kind: "deadline_approaching" })).toBe("/tasks");
  });
});

describe("formatAgo", () => {
  const zone = "America/Toronto";
  // 9 AM on Wednesday, Nov 11 2026 in Toronto.
  const at = new Date("2026-11-11T14:00:00Z");

  it("counts minutes, then hours, then calendar days in the profile's zone", () => {
    expect(formatAgo("2026-11-11T13:59:40Z", zone, at)).toBe("Just now");
    expect(formatAgo("2026-11-11T13:15:00Z", zone, at)).toBe("45m ago");
    expect(formatAgo("2026-11-11T06:00:00Z", zone, at)).toBe("8h ago");
    // 11 PM Tuesday in Toronto: yesterday there, though only ten hours ago.
    expect(formatAgo("2026-11-11T04:00:00Z", zone, at)).toBe("Yesterday");
    expect(formatAgo("2026-11-02T14:00:00Z", zone, at)).toBe("Nov 2");
    expect(formatAgo("2025-11-02T14:00:00Z", zone, at)).toBe("Nov 2 2025");
  });
});
