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

const TASK = {
  id: "t9",
  course_id: "c1",
  title: "Midterm 2",
  description: null,
  task_type: "midterm",
  // 2:30 PM in Toronto on Thursday, Nov 19.
  deadline_at: "2026-11-19T19:30:00Z",
  estimated_minutes: 600,
  remaining_minutes: 600,
  actual_minutes: 0,
  priority: 3,
  status: "todo",
  completed_at: null,
};
const COURSE = { id: "c1", name: "Intro to AI", code: "EECS 3401", color: "#4fd1bd", archived_at: null };

describe("deadlines and views on the schedule calendar", () => {
  const withDeadlines = {
    "GET /tasks": () => jsonResponse(200, { items: [TASK, { ...TASK, id: "t8", title: "Lab report", task_type: "assignment", deadline_at: "2026-11-21T04:30:00Z" }], total: 2 }),
    "GET /courses": () => jsonResponse(200, [COURSE]),
  };

  beforeEach(() => {
    calendar.props = null;
  });

  it("asks for the tasks due in the visible range and puts them in the Due row of their local day", async () => {
    const mock = await open(withDeadlines);
    act(() =>
      calendar.props.datesSet({ start: new Date("2026-11-16T05:00:00Z"), end: new Date("2026-11-23T05:00:00Z") }),
    );
    await waitFor(() => expect(calendar.props.events.filter((e: any) => e.allDay)).toHaveLength(2));
    expect(
      mock.mock.calls.some(([url]) =>
        url.includes("/tasks?due_after=2026-11-16T05%3A00%3A00.000Z&due_before=2026-11-23T05%3A00%3A00.000Z"),
      ),
    ).toBe(true);
    const [exam, lab] = calendar.props.events.filter((e: any) => e.allDay);
    expect(exam).toMatchObject({ title: "Midterm 2", start: "2026-11-19", editable: false, borderColor: "#4fd1bd" });
    expect(exam.classNames).toContain("deadline-exam");
    // 04:30 UTC on the 21st is still the evening of the 20th in Toronto.
    expect(lab).toMatchObject({ title: "Lab report", start: "2026-11-20" });
    expect(lab.classNames).not.toContain("deadline-exam");
    expect(calendar.props.allDayText).toBe("Due");
  });

  it("shows the deadline's type and local time, and opens the task when clicked", async () => {
    await open(withDeadlines);
    act(() => calendar.props.datesSet({ start: new Date("2026-11-16T05:00:00Z"), end: new Date("2026-11-23T05:00:00Z") }));
    await waitFor(() => expect(calendar.props.events.filter((e: any) => e.allDay)).toHaveLength(2));
    const exam = calendar.props.events.find((e: any) => e.id === "due-t9");

    const { render } = await import("@testing-library/react");
    const body = render(
      calendar.props.eventContent({ event: { ...exam, extendedProps: exam.extendedProps }, timeText: "", view: { type: "timeGridWeek" } }),
    );
    expect(body.container).toHaveTextContent("Midterm 2Midterm · 2:30 PM");
    body.unmount();

    act(() => calendar.props.eventClick({ event: { extendedProps: exam.extendedProps } }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("Edit task");
  });

  it("offers month, week and day views, and only moves sessions where there are times", async () => {
    await open();
    expect(calendar.props.headerToolbar.right).toBe("dayGridMonth,timeGridWeek,timeGridDay");
    expect(calendar.props.views.dayGridMonth).toMatchObject({ editable: false, selectable: false });
  });

  it("ignores a selection in the Due row, which is not busy time", async () => {
    await open();
    const unselect = vi.fn();
    act(() =>
      calendar.props.select({ allDay: true, startStr: "2026-11-16", endStr: "2026-11-17", view: { calendar: { unselect } } }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("explains that nothing can be scheduled without study hours", async () => {
    await open({ "GET /availability/windows": () => jsonResponse(200, []) });
    const warning = await screen.findByRole("alert", { name: "No study hours set" });
    expect(warning).toHaveTextContent("You haven't set any study hours yet");
    expect(screen.getByRole("link", { name: "Set study hours" })).toHaveAttribute("href", "/availability");
  });

  it("does not warn when study hours exist", async () => {
    await open();
    await waitFor(() => expect(calendar.props.businessHours).toHaveLength(2));
    expect(screen.queryByRole("alert", { name: "No study hours set" })).not.toBeInTheDocument();
  });
});
