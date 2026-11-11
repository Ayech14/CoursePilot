import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  ADA,
  bodiesSent,
  errorResponse,
  jsonResponse,
  session,
  stubApi,
} from "../test/fakeServer";
import { renderApp } from "../test/renderApp";

const NO_PROGRESS = {
  total_tasks: 0,
  completed_tasks: 0,
  estimated_minutes: 0,
  remaining_minutes: 0,
  actual_minutes: 0,
  next_deadline_at: null,
};

const COURSE = {
  id: "c1",
  name: "Algorithms",
  code: "EECS3101",
  description: null,
  color: "#45bfae",
  archived_at: null,
  created_at: "2026-09-01T00:00:00Z",
  progress: { ...NO_PROGRESS, total_tasks: 4, completed_tasks: 1, remaining_minutes: 150 },
};

const TASK = {
  id: "t1",
  course_id: "c1",
  title: "Problem set",
  description: null,
  task_type: "assignment",
  deadline_at: "2099-12-01T23:59:00Z",
  estimated_minutes: 120,
  remaining_minutes: 90,
  actual_minutes: 30,
  priority: 3,
  status: "in_progress",
  completed_at: null,
};

const inTokyo = () => jsonResponse(200, session("t", { ...ADA, timezone: "Asia/Tokyo" }));
const courses = (...list: unknown[]) => () => jsonResponse(200, list);
const tasks = (...items: unknown[]) => () => jsonResponse(200, { items, total: items.length });
const dialog = () => within(screen.getByRole("dialog"));

describe("courses", () => {
  it("shows an empty state", async () => {
    stubApi({ "GET /courses": courses() });
    renderApp("/courses");
    expect(await screen.findByText("No courses yet")).toBeInTheDocument();
  });

  it("shows real progress for each course", async () => {
    stubApi({ "GET /courses": courses(COURSE) });
    renderApp("/courses");
    expect(await screen.findByText("1 of 4 tasks done")).toBeInTheDocument();
    expect(screen.getByText("2h 30m left")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "25");
  });

  it("offers a retry when loading fails", async () => {
    let attempts = 0;
    stubApi({
      "GET /courses": () =>
        ++attempts === 1 ? errorResponse(400, "bad_request", "Could not load.") : jsonResponse(200, []),
    });
    renderApp("/courses");
    const user = userEvent.setup();

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load.");
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("No courses yet")).toBeInTheDocument();
  });

  it("creates a course, sending blank optional fields as null", async () => {
    const mock = stubApi({
      "GET /courses": courses(),
      "POST /courses": () => jsonResponse(201, COURSE),
    });
    renderApp("/courses");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "New course" }));
    await user.type(dialog().getByLabelText("Name"), "Algorithms");
    await user.click(dialog().getByRole("button", { name: "Violet" }));
    await user.click(dialog().getByRole("button", { name: "Create course" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(bodiesSent(mock, "POST /courses")).toEqual([
      { name: "Algorithms", code: null, description: null, color: "#9b87f5" },
    ]);
  });

  it("keeps the dialog open and shows field errors", async () => {
    stubApi({
      "GET /courses": courses(),
      "POST /courses": () =>
        errorResponse(422, "validation_error", "Invalid", [
          { field: "name", message: "This field is required." },
        ]),
    });
    renderApp("/courses");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "New course" }));
    await user.click(dialog().getByRole("button", { name: "Create course" }));

    expect(await dialog().findByText("This field is required.")).toBeInTheDocument();
    expect(dialog().getByLabelText("Name")).toBeInvalid();
  });

  it("closes a dialog with Escape", async () => {
    stubApi({ "GET /courses": courses() });
    renderApp("/courses");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "New course" }));
    expect(dialog().getByLabelText("Name")).toHaveFocus();
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("warns how many tasks a delete removes, then deletes", async () => {
    const mock = stubApi({
      "GET /courses": courses(),
      "GET /courses/c1": () => jsonResponse(200, { ...COURSE, upcoming_tasks: [] }),
      "DELETE /courses/c1": () => new Response(null, { status: 204 }),
    });
    renderApp("/courses/c1");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Delete" }));
    expect(dialog().getByText(/and its 4 task\(s\)/)).toBeInTheDocument();
    await user.click(dialog().getByRole("button", { name: "Delete course" }));

    expect(await screen.findByText("No courses yet")).toBeInTheDocument();
    expect(mock.mock.calls.some(([, init]) => init.method === "DELETE")).toBe(true);
  });
});

describe("tasks", () => {
  it("asks for open tasks by default", async () => {
    const mock = stubApi({ "GET /courses": courses(), "GET /tasks": tasks() });
    renderApp("/tasks");
    expect(await screen.findByText("No tasks here")).toBeInTheDocument();
    const [url] = mock.mock.calls.find(([u]) => u.startsWith("/api/v1/tasks"))!;
    expect(new URL(url, "http://x").searchParams.getAll("status")).toEqual(["todo", "in_progress"]);
  });

  it("applies the course from the link", async () => {
    const mock = stubApi({ "GET /courses": courses(COURSE), "GET /tasks": tasks() });
    renderApp("/tasks?course=c1");
    await screen.findByText("No tasks here");
    expect(mock.mock.calls.some(([url]) => url.includes("course_id=c1"))).toBe(true);
  });

  it("flags overdue work and shows deadlines in the profile's zone", async () => {
    stubApi({
      "POST /auth/refresh": inTokyo,
      "GET /courses": courses(COURSE),
      "GET /tasks": tasks({ ...TASK, deadline_at: "2020-03-02T15:00:00Z" }),
    });
    renderApp("/tasks");
    expect(await screen.findByText(/Overdue · Tue, Mar 3 2020, 12:00 AM/)).toBeInTheDocument();
    expect(within(screen.getByRole("list")).getByText("Algorithms")).toBeInTheDocument();
  });

  it("creates a task using the profile's time zone, not the browser's", async () => {
    const mock = stubApi({
      "POST /auth/refresh": inTokyo,
      "GET /courses": courses(COURSE),
      "GET /tasks": tasks(),
      "POST /tasks": () => jsonResponse(201, TASK),
    });
    renderApp("/tasks");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "New task" }));
    await user.type(dialog().getByLabelText("Title"), "Essay");
    await user.selectOptions(dialog().getByLabelText("Course"), "c1");
    fireEvent.change(dialog().getByLabelText("Deadline (optional)"), {
      target: { value: "2026-12-01T23:59" },
    });
    await user.type(dialog().getByLabelText("Estimated effort (hours)"), "1.5");
    await user.click(dialog().getByRole("button", { name: "Create task" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(bodiesSent(mock, "POST /tasks")).toEqual([
      {
        title: "Essay",
        description: null,
        course_id: "c1",
        task_type: "assignment",
        deadline_at: "2026-12-01T14:59:00.000Z",
        priority: 2,
        estimated_minutes: 90,
      },
    ]);
  });

  it("does not submit without a valid effort", async () => {
    const mock = stubApi({ "GET /courses": courses(), "GET /tasks": tasks() });
    renderApp("/tasks");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "New task" }));
    await user.click(dialog().getByRole("button", { name: "Create task" }));

    expect(dialog().getByLabelText("Estimated effort (hours)")).toBeInvalid();
    expect(bodiesSent(mock, "POST /tasks")).toEqual([]);
  });

  it("uses exam wording for exams", async () => {
    stubApi({ "GET /courses": courses(), "GET /tasks": tasks() });
    renderApp("/tasks");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "New task" }));
    await user.selectOptions(dialog().getByLabelText("Type"), "midterm");

    expect(dialog().getByLabelText("Exam date and time")).toBeInTheDocument();
    expect(dialog().getByLabelText("Study time needed (hours)")).toBeInTheDocument();
  });

  it("does not send remaining effort unless it was edited", async () => {
    const mock = stubApi({
      "GET /courses": courses(COURSE),
      "GET /tasks": tasks(TASK),
      "PATCH /tasks/t1": () => jsonResponse(200, TASK),
    });
    renderApp("/tasks");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Edit" }));
    await user.clear(dialog().getByLabelText("Title"));
    await user.type(dialog().getByLabelText("Title"), "Renamed");
    await user.click(dialog().getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const [body] = bodiesSent(mock, "PATCH /tasks/t1");
    expect(body.title).toBe("Renamed");
    expect(body).not.toHaveProperty("remaining_minutes");
  });

  it("sends a raised remaining effort when a task runs long", async () => {
    const mock = stubApi({
      "GET /courses": courses(COURSE),
      "GET /tasks": tasks(TASK),
      "PATCH /tasks/t1": () => jsonResponse(200, TASK),
    });
    renderApp("/tasks");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Edit" }));
    await user.clear(dialog().getByLabelText("Remaining effort (hours)"));
    await user.type(dialog().getByLabelText("Remaining effort (hours)"), "5");
    await user.click(dialog().getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(bodiesSent(mock, "PATCH /tasks/t1")[0].remaining_minutes).toBe(300);
  });

  it("keeps an archived course when editing its task", async () => {
    stubApi({
      "GET /courses": courses({ ...COURSE, archived_at: "2026-10-01T00:00:00Z" }),
      "GET /tasks": tasks(TASK),
    });
    renderApp("/tasks");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Edit" }));

    await waitFor(() => expect(dialog().getByLabelText("Course")).toHaveValue("c1"));
  });

  it("does not offer archived courses for new tasks", async () => {
    stubApi({
      "GET /courses": courses({ ...COURSE, archived_at: "2026-10-01T00:00:00Z" }),
      "GET /tasks": tasks(),
    });
    renderApp("/tasks");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "New task" }));

    expect(within(dialog().getByLabelText("Course")).queryByText("Algorithms")).toBeNull();
  });

  it("marks a task finished from the list", async () => {
    const mock = stubApi({
      "GET /courses": courses(COURSE),
      "GET /tasks": tasks(TASK),
      "PATCH /tasks/t1": () => jsonResponse(200, TASK),
    });
    renderApp("/tasks");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("checkbox", { name: "Mark Problem set finished" }));

    await waitFor(() =>
      expect(bodiesSent(mock, "PATCH /tasks/t1")).toEqual([{ status: "completed" }]),
    );
  });

  it("logs progress", async () => {
    const mock = stubApi({
      "GET /courses": courses(COURSE),
      "GET /tasks": tasks(TASK),
      "POST /tasks/t1/progress": () => jsonResponse(200, TASK),
    });
    renderApp("/tasks");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Log" }));
    await user.type(dialog().getByLabelText("Time spent (minutes)"), "25");
    await user.click(dialog().getByRole("button", { name: "Save progress" }));

    await waitFor(() =>
      expect(bodiesSent(mock, "POST /tasks/t1/progress")).toEqual([{ minutes_spent: 25 }]),
    );
  });

  it("logs a finished task", async () => {
    const mock = stubApi({
      "GET /courses": courses(COURSE),
      "GET /tasks": tasks(TASK),
      "POST /tasks/t1/progress": () => jsonResponse(200, TASK),
    });
    renderApp("/tasks");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Log" }));
    await user.click(dialog().getByLabelText("This task is finished"));
    await user.click(dialog().getByRole("button", { name: "Save progress" }));

    await waitFor(() =>
      expect(bodiesSent(mock, "POST /tasks/t1/progress")).toEqual([{ mark_completed: true }]),
    );
  });
});

describe("availability", () => {
  const PREFERENCES = {
    preferred_session_minutes: 50,
    min_session_minutes: 25,
    break_minutes: 10,
    max_daily_minutes: 360,
    deadline_buffer_hours: 12,
    planning_horizon_days: 28,
  };
  const base = {
    "GET /availability/windows": courses(),
    "GET /availability/recurring-blocks": courses(),
    "GET /availability/one-off-blocks": courses(),
    "GET /preferences": () => jsonResponse(200, PREFERENCES),
    "GET /calendar-feeds": courses(),
  };

  it("saves a range that runs to the end of the day as minute 1440", async () => {
    const mock = stubApi({ ...base, "PUT /availability/windows": () => jsonResponse(200, []) });
    renderApp("/availability");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Add Sunday time" }));
    fireEvent.change(screen.getByLabelText("Sunday start"), { target: { value: "20:00" } });
    fireEvent.change(screen.getByLabelText("Sunday end"), { target: { value: "00:00" } });
    await user.click(screen.getByRole("button", { name: "Save weekly hours" }));

    await waitFor(() =>
      expect(bodiesSent(mock, "PUT /availability/windows")).toEqual([
        { windows: [{ day_of_week: 6, start_minute: 1200, end_minute: 1440 }] },
      ]),
    );
  });

  it("loads existing hours", async () => {
    stubApi({
      ...base,
      "GET /availability/windows": courses({
        id: "w1",
        day_of_week: 0,
        start_minute: 540,
        end_minute: 1440,
      }),
    });
    renderApp("/availability");
    expect(await screen.findByLabelText("Monday start")).toHaveValue("09:00");
    expect(screen.getByLabelText("Monday end")).toHaveValue("00:00");
  });

  it("shows a server overlap error on the matching row", async () => {
    stubApi({
      ...base,
      "PUT /availability/windows": () =>
        errorResponse(422, "validation_error", "Invalid", [
          { field: "windows.1", message: "Overlaps another time range on this day." },
        ]),
    });
    renderApp("/availability");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Add Monday time" }));
    await user.click(screen.getByRole("button", { name: "Add Monday time" }));
    await user.click(screen.getByRole("button", { name: "Save weekly hours" }));

    expect(await screen.findByText("Overlaps another time range on this day.")).toBeInTheDocument();
    const [first, second] = screen.getAllByLabelText("Monday start");
    expect(first).toBeValid();
    expect(second).toBeInvalid();
  });

  it("removes a range", async () => {
    stubApi(base);
    renderApp("/availability");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Add Friday time" }));
    await user.click(screen.getByRole("button", { name: "Remove Friday time range" }));

    expect(screen.queryByLabelText("Friday start")).not.toBeInTheDocument();
  });

  it("saves preferences, converting daily hours to minutes", async () => {
    const mock = stubApi({ ...base, "PUT /preferences": () => jsonResponse(200, PREFERENCES) });
    renderApp("/availability");
    const user = userEvent.setup();

    const daily = await screen.findByLabelText("Most study in one day (hours)");
    await user.clear(daily);
    await user.type(daily, "4.5");
    await user.click(screen.getByRole("button", { name: "Save preferences" }));

    await waitFor(() =>
      expect(bodiesSent(mock, "PUT /preferences")).toEqual([{ ...PREFERENCES, max_daily_minutes: 270 }]),
    );
  });

  it("adds a weekly class", async () => {
    const mock = stubApi({
      ...base,
      "POST /availability/recurring-blocks": () => jsonResponse(201, {}),
    });
    renderApp("/availability");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Add weekly" }));
    await user.type(dialog().getByLabelText("Title"), "Lecture");
    await user.selectOptions(dialog().getByLabelText("Day"), "2");
    await user.click(dialog().getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(bodiesSent(mock, "POST /availability/recurring-blocks")).toEqual([
        { title: "Lecture", category: "class", day_of_week: 2, start_minute: 540, end_minute: 630 },
      ]),
    );
  });

  it("adds a one-time shift in the profile's time zone", async () => {
    const mock = stubApi({
      ...base,
      "POST /auth/refresh": inTokyo,
      "POST /availability/one-off-blocks": () => jsonResponse(201, {}),
    });
    renderApp("/availability");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Add one-time" }));
    await user.type(dialog().getByLabelText("Title"), "Trip");
    await user.selectOptions(dialog().getByLabelText("What is it?"), "work");
    fireEvent.change(dialog().getByLabelText("Starts"), { target: { value: "2026-12-24T09:00" } });
    fireEvent.change(dialog().getByLabelText("Ends"), { target: { value: "2026-12-26T09:00" } });
    await user.click(dialog().getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(bodiesSent(mock, "POST /availability/one-off-blocks")).toEqual([
        {
          title: "Trip",
          category: "work",
          start_at: "2026-12-24T00:00:00.000Z",
          end_at: "2026-12-26T00:00:00.000Z",
        },
      ]),
    );
  });
});

describe("privacy between sign-ins", () => {
  it("discards cached data on sign out", async () => {
    stubApi({
      "GET /courses": courses(COURSE),
      "POST /auth/logout": () => new Response(null, { status: 204 }),
    });
    const queryClient = renderApp("/courses");
    const user = userEvent.setup();

    await screen.findByText("Algorithms");
    expect(queryClient.getQueryCache().getAll().length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Sign out" }));

    await screen.findByRole("heading", { name: "Sign in" });
    expect(queryClient.getQueryCache().getAll()).toEqual([]);
  });
});
