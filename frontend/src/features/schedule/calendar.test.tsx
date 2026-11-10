import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ADA, bodiesSent, errorResponse, jsonResponse, session, stubApi } from "../../test/fakeServer";
import { renderApp } from "../../test/renderApp";

/* eslint-disable @typescript-eslint/no-explicit-any */
const calendar = vi.hoisted(() => ({ props: null as any }));

// A browser is needed to really drag. That is checked by hand; here we prove what a drag does.
vi.mock("@fullcalendar/react", () => ({
  default: (props: any) => {
    calendar.props = props;
    return <div data-testid="calendar" />;
  },
}));

const SESSION = {
  id: "s1",
  task_id: "t1",
  origin: "auto",
  is_locked: false,
  is_user_modified: false,
  task_title: "Essay",
  course_name: "History",
  course_color: "#112233",
  start_at: "2026-11-16T14:00:00Z",
  end_at: "2026-11-16T14:50:00Z",
  status: "planned",
  actual_minutes: 0,
  explanation: "Due soon.",
};

const PLACEMENT = {
  ok: false,
  conflicts: [{ kind: "overlap", message: "This overlaps another session.", session_id: "s2" }],
  warnings: [],
  alternatives: [{ start_at: "2026-11-17T15:00:00Z", end_at: "2026-11-17T15:50:00Z" }],
};

const routes = {
  "POST /auth/refresh": () => jsonResponse(200, session("t", ADA)),
  "GET /schedule/proposals/current": () => jsonResponse(200, null),
  "GET /schedule/status": () => jsonResponse(200, { needs_update: false }),
  "GET /availability/windows": () =>
    jsonResponse(200, [
      { id: "w", day_of_week: 0, start_minute: 540, end_minute: 1440 },
      { id: "x", day_of_week: 6, start_minute: 600, end_minute: 660 },
    ]),
  "GET /sessions": () => jsonResponse(200, [SESSION]),
};

function eventFrom(overrides = {}) {
  const props = { session: { ...SESSION, ...overrides } };
  return { extendedProps: props, startStr: "2026-11-17T10:00:00-05:00", endStr: "2026-11-16T10:15:00-05:00" };
}

async function open(extra = {}) {
  const mock = stubApi({ ...routes, ...extra });
  renderApp("/schedule");
  await screen.findByTestId("calendar", {}, { timeout: 4000 });
  return mock;
}

describe("schedule calendar", () => {
  beforeEach(() => {
    calendar.props = null;
  });

  it("uses the profile's zone, Monday weeks and the student's hours", async () => {
    await open();
    await waitFor(() => expect(calendar.props.businessHours).toHaveLength(2));
    expect(calendar.props.timeZone).toBe("America/Toronto");
    expect(calendar.props.firstDay).toBe(1);
    expect(calendar.props.businessHours).toEqual([
      { daysOfWeek: [1], startTime: "09:00", endTime: "24:00" },
      { daysOfWeek: [0], startTime: "10:00", endTime: "11:00" },
    ]);
  });

  it("asks for the visible range and shows its sessions", async () => {
    const mock = await open();
    act(() =>
      calendar.props.datesSet({
        start: new Date("2026-11-16T05:00:00Z"),
        end: new Date("2026-11-23T05:00:00Z"),
      }),
    );
    await waitFor(() => expect(calendar.props.events).toHaveLength(1));
    expect(
      mock.mock.calls.some(([url]) =>
        url.includes("/sessions?start=2026-11-16T05:00:00.000Z&end=2026-11-23T05:00:00.000Z"),
      ),
    ).toBe(true);
    expect(calendar.props.events[0]).toMatchObject({
      id: "s1",
      start: SESSION.start_at,
      editable: true,
      borderColor: "#112233",
    });
  });

  it.each([
    ["locked", { is_locked: true }],
    ["completed", { status: "completed" }],
    ["missed", { status: "missed" }],
    ["running", { status: "in_progress" }],
  ])("does not let a %s session be dragged", async (_name, overrides) => {
    await open({ "GET /sessions": () => jsonResponse(200, [{ ...SESSION, ...overrides }]) });
    act(() => calendar.props.datesSet({ start: new Date(0), end: new Date(1) }));
    await waitFor(() => expect(calendar.props.events).toHaveLength(1));
    expect(calendar.props.events[0].editable).toBe(false);
  });

  it("saves a drop at the dropped time, with the same length", async () => {
    const mock = await open({ "PATCH /sessions/s1": () => jsonResponse(200, SESSION) });
    const revert = vi.fn();
    act(() => calendar.props.eventDrop({ event: eventFrom(), revert }));
    await waitFor(() =>
      expect(bodiesSent(mock, "PATCH /sessions/s1")).toEqual([
        {
          start_at: "2026-11-17T15:00:00.000Z",
          end_at: "2026-11-17T15:50:00.000Z",
          acknowledge_warnings: false,
        },
      ]),
    );
    expect(revert).not.toHaveBeenCalled();
  });

  it("saves a resize, keeping the start", async () => {
    const mock = await open({ "PATCH /sessions/s1": () => jsonResponse(200, SESSION) });
    act(() => calendar.props.eventResize({ event: eventFrom(), revert: vi.fn() }));
    await waitFor(() =>
      expect(bodiesSent(mock, "PATCH /sessions/s1")[0]).toMatchObject({
        start_at: SESSION.start_at,
        end_at: "2026-11-16T15:15:00.000Z",
      }),
    );
  });

  it("puts a refused drop back and offers better times", async () => {
    await open({
      "PATCH /sessions/s1": () => errorResponse(409, "session_conflict", "That time is not available.", PLACEMENT),
    });
    const revert = vi.fn();
    act(() => calendar.props.eventDrop({ event: eventFrom(), revert }));

    expect(await screen.findByText("This overlaps another session.")).toBeInTheDocument();
    expect(revert).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Nov 17, 10:00 AM/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Keep this time anyway" })).not.toBeInTheDocument();
  });

  it("lets a student confirm a drop that only bends their preferences", async () => {
    const warned = { ...PLACEMENT, conflicts: [], warnings: [{ kind: "daily_limit", message: "Over your limit." }] };
    let calls = 0;
    const mock = await open({
      "PATCH /sessions/s1": () =>
        ++calls === 1
          ? errorResponse(409, "placement_warnings", "Confirm.", warned)
          : jsonResponse(200, SESSION),
    });
    act(() => calendar.props.eventDrop({ event: eventFrom(), revert: vi.fn() }));

    await userEvent.setup().click(await screen.findByRole("button", { name: "Keep this time anyway" }));

    await waitFor(() => expect(bodiesSent(mock, "PATCH /sessions/s1")).toHaveLength(2));
    expect(bodiesSent(mock, "PATCH /sessions/s1")[1]).toMatchObject({
      start_at: "2026-11-17T15:00:00.000Z",
      acknowledge_warnings: true,
    });
  });

  it("shows other failures and puts the session back", async () => {
    await open({ "PATCH /sessions/s1": () => errorResponse(409, "session_not_editable", "Only sessions that have not started can be changed.") });
    const revert = vi.fn();
    act(() => calendar.props.eventDrop({ event: eventFrom(), revert }));
    expect(await screen.findByText("Only sessions that have not started can be changed.")).toBeInTheDocument();
    expect(revert).toHaveBeenCalled();
  });

  it("opens a session's details from the calendar", async () => {
    await open();
    act(() => calendar.props.eventClick({ event: eventFrom() }));
    expect(await screen.findByText("Due soon.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Lock" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change" })).toBeInTheDocument();
  });

  it("offers a retry when the calendar's sessions fail to load", async () => {
    await open({ "GET /sessions": () => errorResponse(500, "server_error", "Something went wrong.") });
    act(() => calendar.props.datesSet({ start: new Date(0), end: new Date(1) }));
    expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("remembers the chosen view", async () => {
    await open();
    await userEvent.setup().click(screen.getByRole("button", { name: "list" }));
    expect(localStorage.getItem("coursepilot.schedule.view")).toBe("list");
    expect(screen.queryByTestId("calendar")).not.toBeInTheDocument();
  });
});
