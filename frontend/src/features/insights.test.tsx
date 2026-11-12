import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { errorResponse, jsonResponse, stubApi } from "../test/fakeServer";
import { renderApp } from "../test/renderApp";

const COURSE = {
  course_id: "c1",
  name: "Algorithms",
  code: "CS201",
  color: "#112233",
  open_tasks: 2,
  completed_tasks: 1,
  remaining_minutes: 150,
};

const DASHBOARD = {
  today: [
    {
      id: "s1",
      task_id: "t1",
      task_title: "Graph problems",
      course_name: "Algorithms",
      course_color: "#112233",
      start_at: "2026-11-16T14:00:00Z",
      end_at: "2026-11-16T14:50:00Z",
      status: "completed",
      origin: "auto",
      is_locked: false,
      is_user_modified: false,
      explanation: null,
      actual_minutes: 47,
    },
  ],
  upcoming_assignments: [
    {
      task_id: "a1",
      title: "Problem set 4",
      task_type: "assignment",
      deadline_at: "2026-11-20T23:59:00Z",
      course_name: "Algorithms",
      course_color: "#112233",
      remaining_minutes: 90,
    },
  ],
  upcoming_exams: [],
  attention: [
    {
      task_id: "o1",
      title: "Late lab",
      course_color: null,
      deadline_at: "2026-11-10T20:00:00Z",
      reason: "overdue",
      unplanned_minutes: 30,
    },
    {
      task_id: "u1",
      title: "Essay outline",
      course_color: null,
      deadline_at: "2026-11-18T20:00:00Z",
      reason: "not_fully_planned",
      unplanned_minutes: 75,
    },
  ],
  attention_total: 3,
  week: { week_start: "2026-11-16", studied_minutes: 197, planned_minutes: 130 },
  tasks: { completed: 3, remaining: 9, overdue: 1 },
  workload: [COURSE, { ...COURSE, course_id: null, name: "No course", color: null, remaining_minutes: 40, open_tasks: 1 }],
  progress: { studied_minutes: 0, goal_minutes: null, streak_days: 0, studied_today: false },
  recent: [],
};

const EMPTY_DASHBOARD = {
  ...DASHBOARD,
  today: [],
  upcoming_assignments: [],
  attention: [],
  attention_total: 0,
  week: { week_start: "2026-11-16", studied_minutes: 0, planned_minutes: 0 },
  tasks: { completed: 0, remaining: 0, overdue: 0 },
  workload: [],
};

const week = (week_start: string, minutes: number) => ({ week_start, minutes });

const ANALYTICS = {
  weekly_minutes: [week("2026-11-02", 0), week("2026-11-09", 95)],
  minutes_per_course: [{ course_id: "c1", name: "Algorithms", color: "#112233", minutes: 95 }],
  completions: [
    { week_start: "2026-11-02", count: 0 },
    { week_start: "2026-11-09", count: 2 },
  ],
  workload: [COURSE],
  estimates: {
    tasks_compared: 2,
    estimated_minutes: 200,
    actual_minutes: 150,
    recent: [{ task_id: "t", title: "Quiz prep", estimated_minutes: 120, actual_minutes: 70 }],
  },
  upcoming: [{ date: "2026-11-16", planned_minutes: 50, deadlines: 1 }],
  consistency: {
    days: [
      { date: "2026-11-15", minutes: 0 },
      { date: "2026-11-16", minutes: 45 },
    ],
    active_days: 1,
    current_streak: 1,
    sessions_completed: 3,
    sessions_missed: 1,
  },
};

const EMPTY_ANALYTICS = {
  ...ANALYTICS,
  weekly_minutes: [week("2026-11-09", 0)],
  minutes_per_course: [],
  completions: [{ week_start: "2026-11-09", count: 0 }],
  workload: [],
  estimates: { tasks_compared: 0, estimated_minutes: 0, actual_minutes: 0, recent: [] },
  upcoming: [{ date: "2026-11-16", planned_minutes: 0, deadlines: 0 }],
  consistency: { ...ANALYTICS.consistency, active_days: 0, current_streak: 0, sessions_completed: 0, sessions_missed: 0 },
};

const card = (name: string) => within(screen.getByRole("region", { name }));

describe("dashboard", () => {
  it("shows what the server computed and nothing invented", async () => {
    stubApi({ "GET /dashboard": () => jsonResponse(200, DASHBOARD) });
    renderApp("/dashboard");

    expect(await screen.findByText("3h 17m")).toBeInTheDocument();
    expect(screen.getByText("2h 10m")).toBeInTheDocument();
    expect(card("Today").getByText("Graph problems")).toBeInTheDocument();
    expect(card("Today").getByText(/completed, 47m studied/)).toBeInTheDocument();
    expect(card("Upcoming assignments").getByText("Problem set 4")).toBeInTheDocument();
    expect(card("Upcoming exams").getByText("No exams coming up.")).toBeInTheDocument();
    expect(card("Needs attention").getByText(/^Overdue since/)).toBeInTheDocument();
    expect(card("Needs attention").getByText(/1h 15m not yet scheduled/)).toBeInTheDocument();
    expect(card("Needs attention").getByText(/And 1 more/)).toBeInTheDocument();
    expect(card("Task progress").getByText(/of 12 tasks completed/)).toBeInTheDocument();
    expect(card("Task progress").getByRole("link", { name: "Algorithms" })).toHaveAttribute("href", "/courses/c1");
    const load = within(card("Workload by course").getByRole("list"));
    expect(load.getAllByRole("listitem").map((row) => row.textContent)).toEqual(["Algorithms2h 30m", "No course40m"]);
  });

  it("sums up the week and the next deadline in the header from real figures", async () => {
    stubApi({ "GET /dashboard": () => jsonResponse(200, DASHBOARD) });
    renderApp("/dashboard");

    // 197 minutes timed of 197 + 130: 60%.
    expect(await screen.findByRole("img", { name: "60% of this week's study done" })).toBeInTheDocument();
    expect(screen.getByText("3h 17m studied, 2h 10m still planned")).toBeInTheDocument();
    const next = screen.getByText("Next deadline").closest("div")!.parentElement!;
    expect(within(next).getByText("Problem set 4")).toBeInTheDocument();
  });

  it("guides a new student instead of showing zeros", async () => {
    stubApi({ "GET /dashboard": () => jsonResponse(200, EMPTY_DASHBOARD) });
    renderApp("/dashboard");
    expect(await screen.findByText("Nothing to show yet")).toBeInTheDocument();
    expect(screen.queryByText("Studied this week")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add courses" })).toBeInTheDocument();
  });

  it("offers a retry when loading fails", async () => {
    let attempts = 0;
    stubApi({
      "GET /dashboard": () =>
        ++attempts === 1
          ? errorResponse(500, "server_error", "Something went wrong.")
          : jsonResponse(200, DASHBOARD),
    });
    renderApp("/dashboard");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("3h 17m")).toBeInTheDocument();
  });
});

describe("analytics", () => {
  it("shows every required figure, reachable as text", async () => {
    stubApi({ "GET /analytics": () => jsonResponse(200, ANALYTICS) });
    renderApp("/analytics");

    expect(await screen.findByRole("region", { name: "Weekly study hours" }, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText("Studied in this range").nextSibling).toHaveTextContent("1h 35m");
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("3 completed, 1 missed")).toBeInTheDocument();

    const weekly = card("Weekly study hours");
    expect(within(weekly.getByRole("table")).getByText("1h 35m")).toBeInTheDocument();
    expect(card("Tasks completed").getByRole("table")).toHaveTextContent("2 tasks");
    expect(card("Upcoming workload").getByRole("table")).toHaveTextContent("50m, 1 deadline");
    expect(card("Hours per course").getByText("Algorithms")).toBeInTheDocument();
    expect(card("Workload distribution").getByText("2h 30m, 2 tasks")).toBeInTheDocument();
    expect(card("Consistency").getByRole("img", { name: "Mon, Nov 16: 45m" })).toBeInTheDocument();
    const estimates = card("Estimated vs actual time");
    expect(estimates.getByText(/or 75% of the estimate/)).toBeInTheDocument();
    expect(estimates.getByText("2h estimated, 1h 10m actual")).toBeInTheDocument();
  });

  it("explains an empty account", async () => {
    stubApi({ "GET /analytics": () => jsonResponse(200, EMPTY_ANALYTICS) });
    renderApp("/analytics");
    expect(await screen.findByText("No data to chart yet", {}, { timeout: 4000 })).toBeInTheDocument();
  });

  it("explains an empty chart next to ones with data", async () => {
    stubApi({
      "GET /analytics": () => jsonResponse(200, { ...EMPTY_ANALYTICS, workload: [COURSE] }),
    });
    renderApp("/analytics");
    expect(await screen.findByText("Time a study session to see your weekly hours.", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText("Finish a task you timed to compare it with your estimate.")).toBeInTheDocument();
  });

  it("reloads for a different range", async () => {
    const mock = stubApi({ "GET /analytics": () => jsonResponse(200, ANALYTICS) });
    renderApp("/analytics");
    await userEvent.setup().selectOptions(await screen.findByLabelText("Range", {}, { timeout: 4000 }), "26");
    await waitFor(() => expect(mock.mock.calls.some(([url]) => url.endsWith("weeks=26"))).toBe(true));
  });

  it("offers a retry when loading fails", async () => {
    stubApi({ "GET /analytics": () => errorResponse(500, "server_error", "Something went wrong.") });
    renderApp("/analytics");
    expect(await screen.findByRole("button", { name: "Try again" }, { timeout: 4000 })).toBeInTheDocument();
  });
});
