import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { bodiesSent, errorResponse, jsonResponse, stubApi } from "../../test/fakeServer";
import { renderApp } from "../../test/renderApp";

/* eslint-disable @typescript-eslint/no-explicit-any */
const calendar = vi.hoisted(() => ({ props: null as any }));

vi.mock("@fullcalendar/react", () => ({
  default: (props: any) => {
    calendar.props = props;
    return <div data-testid="calendar" />;
  },
}));

const FEED = {
  id: "f1",
  name: "YorkU eClass",
  url_hint: "eclass.yorku.ca/…",
  last_synced_at: "2026-11-10T12:00:00Z",
  last_error: null,
  busy_count: 12,
  pending_deadlines: 2,
};

const SUGGESTION = {
  id: "g1",
  title: "Assignment 2 is due",
  due_at: "2026-11-20T04:59:00Z",
  feed_name: "YorkU eClass",
  course_id: "c1",
  course_name: "Software Design",
};

const COURSE = { id: "c1", name: "Software Design", code: "EECS2030", color: "#112233", archived_at: null };

const availability = {
  "GET /availability/windows": () => jsonResponse(200, []),
  "GET /availability/recurring-blocks": () => jsonResponse(200, []),
  "GET /availability/one-off-blocks": () => jsonResponse(200, []),
  "GET /preferences": () =>
    jsonResponse(200, {
      preferred_session_minutes: 50,
      min_session_minutes: 25,
      break_minutes: 10,
      max_daily_minutes: 360,
      deadline_buffer_hours: 12,
      planning_horizon_days: 28,
    }),
};

const feeds = () => within(screen.getByRole("list", { name: "Connected calendars" }));

describe("connected calendars", () => {
  it("connects a link and shows what it brought in, without the link itself", async () => {
    let connected = false;
    const mock = stubApi({
      ...availability,
      "GET /calendar-feeds": () => jsonResponse(200, connected ? [FEED] : []),
      "POST /calendar-feeds": () => {
        connected = true;
        return jsonResponse(201, FEED);
      },
    });
    renderApp("/availability");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Name"), "YorkU eClass");
    await user.type(screen.getByLabelText("Calendar link"), "webcal://eclass.yorku.ca/x?authtoken=s");
    await user.click(screen.getByRole("button", { name: "Connect" }));

    await waitFor(() =>
      expect(bodiesSent(mock, "POST /calendar-feeds")).toEqual([
        { name: "YorkU eClass", url: "webcal://eclass.yorku.ca/x?authtoken=s" },
      ]),
    );
    expect(await feeds().findByText(/12 busy times · 2 deadlines to review/)).toBeInTheDocument();
    expect(screen.getByLabelText("Calendar link")).toHaveValue("");
  });

  it("explains a link that could not be read", async () => {
    stubApi({
      ...availability,
      "GET /calendar-feeds": () => jsonResponse(200, []),
      "POST /calendar-feeds": () =>
        errorResponse(422, "validation_error", "The submitted data is invalid.", [
          { field: "url", message: "That link points to a private network address." },
        ]),
    });
    renderApp("/availability");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Calendar link"), "https://10.0.0.1/");
    await user.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByText("That link points to a private network address.")).toBeInTheDocument();
  });

  it("shows a failed sync honestly and syncs on request", async () => {
    const mock = stubApi({
      ...availability,
      "GET /calendar-feeds": () =>
        jsonResponse(200, [{ ...FEED, last_error: "The calendar's website answered with error 500." }]),
      "POST /calendar-feeds/f1/sync": () => jsonResponse(200, FEED),
    });
    renderApp("/availability");
    expect(await screen.findByText(/Last sync failed: The calendar's website answered with error 500/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Sync YorkU eClass now" }));
    await waitFor(() => expect(mock.mock.calls.some(([url]) => url.endsWith("/calendar-feeds/f1/sync"))).toBe(true));
  });

  it("disconnects only after confirming", async () => {
    const mock = stubApi({
      ...availability,
      "GET /calendar-feeds": () => jsonResponse(200, [FEED]),
      "DELETE /calendar-feeds/f1": () => new Response(null, { status: 204 }),
    });
    renderApp("/availability");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Disconnect YorkU eClass" }));
    expect(screen.getByText(/Tasks you already added stay/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Disconnect" }));
    await waitFor(() => expect(mock.mock.calls.some(([, init]) => init.method === "DELETE")).toBe(true));
  });
});

describe("deadline suggestions", () => {
  const tasksPage = {
    "GET /courses": () => jsonResponse(200, [COURSE]),
    "GET /tasks": () => jsonResponse(200, { items: [], total: 0 }),
  };

  it("are hidden when there are none", async () => {
    stubApi({ ...tasksPage, "GET /deadline-suggestions": () => jsonResponse(200, []) });
    renderApp("/tasks");
    await screen.findByRole("heading", { name: "Tasks" });
    expect(screen.queryByRole("region", { name: "Deadlines from your calendars" })).not.toBeInTheDocument();
  });

  it("become tasks only with the student's estimate", async () => {
    const mock = stubApi({
      ...tasksPage,
      "GET /deadline-suggestions": () => jsonResponse(200, [SUGGESTION]),
      "POST /deadline-suggestions/g1/accept": () => jsonResponse(201, {}),
    });
    renderApp("/tasks");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add Assignment 2 is due as a task" }));

    const form = within(screen.getByRole("dialog"));
    expect(form.getByLabelText("Title")).toHaveValue("Assignment 2");
    expect(form.getByLabelText("Course")).toHaveValue("c1");
    const hours = form.getByLabelText("Hours of work");
    await user.clear(hours);
    await user.click(form.getByRole("button", { name: "Add task" }));
    expect(await form.findByText("Enter how many hours this will take.")).toBeInTheDocument();
    expect(bodiesSent(mock, "POST /deadline-suggestions/g1/accept")).toEqual([]);

    await user.type(hours, "3.5");
    await user.selectOptions(form.getByLabelText("Priority"), "3");
    await user.click(form.getByRole("button", { name: "Add task" }));
    await waitFor(() =>
      expect(bodiesSent(mock, "POST /deadline-suggestions/g1/accept")).toEqual([
        {
          title: "Assignment 2",
          task_type: "assignment",
          course_id: "c1",
          estimated_minutes: 210,
          priority: 3,
        },
      ]),
    );
  });

  it("can be dismissed", async () => {
    let open = true;
    stubApi({
      ...tasksPage,
      "GET /deadline-suggestions": () => jsonResponse(200, open ? [SUGGESTION] : []),
      "POST /deadline-suggestions/g1/dismiss": () => {
        open = false;
        return new Response(null, { status: 204 });
      },
    });
    renderApp("/tasks");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Dismiss Assignment 2 is due" }));
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Deadlines from your calendars" })).not.toBeInTheDocument(),
    );
  });
});

describe("busy times on the schedule calendar", () => {
  const schedule = {
    "GET /schedule/proposals/current": () => jsonResponse(200, null),
    "GET /schedule/status": () => jsonResponse(200, { needs_update: false }),
    "GET /sessions": () => jsonResponse(200, []),
    "GET /availability/windows": () => jsonResponse(200, []),
    "POST /calendar-feeds/sync-stale": () => jsonResponse(200, []),
    "GET /busy-times": () =>
      jsonResponse(200, [
        {
          source: "calendar",
          id: "b1",
          title: "EECS 2030 Lecture",
          category: "other",
          start_at: "2026-11-16T15:00:00Z",
          end_at: "2026-11-16T16:20:00Z",
          feed_name: "YorkU eClass",
        },
      ]),
  };

  async function open(extra = {}) {
    const mock = stubApi({ ...schedule, ...extra });
    renderApp("/schedule");
    await screen.findByTestId("calendar", {}, { timeout: 4000 });
    act(() => calendar.props.datesSet({ start: new Date("2026-11-16T05:00:00Z"), end: new Date("2026-11-23T05:00:00Z") }));
    return mock;
  }

  it("asks stale calendars to refresh when the schedule opens", async () => {
    const mock = await open();
    await waitFor(() =>
      expect(mock.mock.calls.filter(([url]) => url.endsWith("/calendar-feeds/sync-stale"))).toHaveLength(1),
    );
  });

  it("draws busy times that cannot be dragged", async () => {
    await open();
    await waitFor(() => expect(calendar.props.events).toHaveLength(1));
    expect(calendar.props.events[0]).toMatchObject({
      title: "EECS 2030 Lecture",
      editable: false,
      classNames: ["busy-event"],
    });
  });

  it("draws the selection preview, which has no session or busy time", async () => {
    await open();
    const preview = render(
      calendar.props.eventContent({ event: { title: "", extendedProps: {} }, timeText: "1:00 - 5:00" }),
    );
    expect(preview.getByText("1:00 - 5:00")).toBeInTheDocument();
  });

  it("explains where an imported busy time comes from", async () => {
    await open();
    await waitFor(() => expect(calendar.props.events).toHaveLength(1));
    act(() => calendar.props.eventClick({ event: calendar.props.events[0] }));
    expect(await screen.findByText(/From a connected calendar/)).toBeInTheDocument();
    expect(screen.getByText("YorkU eClass")).toBeInTheDocument();
  });

  it("adds a one-time shift from a dragged range", async () => {
    const mock = await open({ "POST /availability/one-off-blocks": () => jsonResponse(201, {}) });
    const unselect = vi.fn();
    act(() =>
      calendar.props.select({
        startStr: "2026-11-18T17:00:00-05:00",
        endStr: "2026-11-18T22:00:00-05:00",
        view: { calendar: { unselect } },
      }),
    );
    const user = userEvent.setup();
    const form = within(await screen.findByRole("dialog"));
    await user.type(form.getByLabelText("Title"), "Shift at work");
    await user.click(form.getByRole("button", { name: "Add" }));
    await waitFor(() =>
      expect(bodiesSent(mock, "POST /availability/one-off-blocks")).toEqual([
        {
          title: "Shift at work",
          category: "work",
          start_at: "2026-11-18T22:00:00.000Z",
          end_at: "2026-11-19T03:00:00.000Z",
        },
      ]),
    );
    expect(unselect).toHaveBeenCalled();
  });

  it("adds a weekly busy time in local time", async () => {
    const mock = await open({ "POST /availability/recurring-blocks": () => jsonResponse(201, {}) });
    act(() =>
      calendar.props.select({
        startStr: "2026-11-18T18:00:00-05:00",
        endStr: "2026-11-18T20:30:00-05:00",
        view: { calendar: { unselect: vi.fn() } },
      }),
    );
    const user = userEvent.setup();
    const form = within(await screen.findByRole("dialog"));
    await user.type(form.getByLabelText("Title"), "Soccer");
    await user.click(form.getByRole("button", { name: "Friends and social" }));
    await user.click(form.getByLabelText("Every Wednesday at this time"));
    await user.click(form.getByRole("button", { name: "Add" }));
    await waitFor(() =>
      expect(bodiesSent(mock, "POST /availability/recurring-blocks")).toEqual([
        { title: "Soccer", category: "social", day_of_week: 2, start_minute: 1080, end_minute: 1230 },
      ]),
    );
  });

  it("only offers once for a range past midnight", async () => {
    await open();
    act(() =>
      calendar.props.select({
        startStr: "2026-11-18T22:00:00-05:00",
        endStr: "2026-11-19T02:00:00-05:00",
        view: { calendar: { unselect: vi.fn() } },
      }),
    );
    const form = within(await screen.findByRole("dialog"));
    expect(form.getByLabelText(/Every Wednesday/)).toBeDisabled();
    expect(form.getByText("Times that run past midnight can be added once.")).toBeInTheDocument();
  });
});
