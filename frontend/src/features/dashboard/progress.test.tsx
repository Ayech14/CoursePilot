import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DateTime } from "luxon";
import { describe, expect, it } from "vitest";

import { bodiesSent, jsonResponse, stubApi } from "../../test/fakeServer";
import { renderApp } from "../../test/renderApp";

const ZONE = "America/Toronto";
const today = () => DateTime.now().setZone(ZONE);

const WORKLOAD = {
  course_id: "c1",
  name: "Biology",
  code: null,
  color: "#22aa55",
  open_tasks: 1,
  completed_tasks: 0,
  remaining_minutes: 120,
};

function dashboard(progress = {}, recent: unknown[] = []) {
  return {
    today: [],
    upcoming_assignments: [],
    upcoming_exams: [],
    attention: [],
    attention_total: 0,
    week: { week_start: "2026-11-09", studied_minutes: 65, planned_minutes: 0 },
    tasks: { completed: 0, remaining: 1, overdue: 0 },
    workload: [WORKLOAD],
    progress: { studied_minutes: 65, goal_minutes: 120, streak_days: 4, studied_today: true, ...progress },
    recent,
  };
}

/** A month as the server sends it: every day, with study on the 4th and a deadline on the 6th. */
function month(url: string) {
  const key = new URL(url, "http://x").searchParams.get("month")!;
  const first = DateTime.fromISO(`${key}-01`);
  const days = Array.from({ length: first.daysInMonth! }, (_, index) => {
    const date = first.plus({ days: index }).toISODate()!;
    const day = index + 1;
    return {
      date,
      studied_minutes: day === 4 ? 90 : 0,
      studied: day === 4 ? [{ task_id: "t1", title: "Cells", course_color: "#22aa55", minutes: 90 }] : [],
      completed: day === 4 ? [{ task_id: "t2", title: "Lab report", course_color: null }] : [],
      deadlines:
        day === 6
          ? [
              {
                task_id: "t3",
                title: "Midterm 1",
                task_type: "midterm",
                deadline_at: first.plus({ days: 5, hours: 15 }).setZone(ZONE, { keepLocalTime: true }).toUTC().toISO(),
                course_color: "#22aa55",
                completed: false,
              },
            ]
          : [],
    };
  });
  return jsonResponse(200, { month: first.toISODate(), goal_minutes: 120, days });
}

function open(routes = {}) {
  const mock = stubApi({
    "GET /dashboard": () => jsonResponse(200, dashboard()),
    "GET /month": (_body, url) => month(url),
    ...routes,
  });
  renderApp("/dashboard");
  return mock;
}

const card = (name: string) => within(screen.getByRole("region", { name }));
const cardSoon = async (name: string) => within(await screen.findByRole("region", { name }));

describe("today's progress", () => {
  it("measures today against the student's goal and shows the streak", async () => {
    open();
    expect(await screen.findByRole("img", { name: "1h 5m of a 2h daily goal" })).toBeInTheDocument();
    expect(card("Today's progress").getByText("54% of your 2h goal, 55m to go.")).toBeInTheDocument();
    expect(card("Today's progress").getByText("4 days in a row")).toBeInTheDocument();
    expect(card("Today's progress").getByRole("button", { name: "2h" })).toHaveAttribute("aria-pressed", "true");
  });

  it("says plainly when the goal is reached and when the streak needs today", async () => {
    stubApi({
      "GET /dashboard": () =>
        jsonResponse(200, dashboard({ studied_minutes: 130, streak_days: 1, studied_today: false })),
      "GET /month": (_b, url) => month(url),
    });
    renderApp("/dashboard");
    expect(await screen.findByText("Goal reached: 2h done.")).toBeInTheDocument();
    expect(screen.getByText("1 day in a row. Study today to keep it going.")).toBeInTheDocument();
  });

  it("invites a goal and a first streak when there are none", async () => {
    stubApi({
      "GET /dashboard": () =>
        jsonResponse(200, dashboard({ studied_minutes: 0, goal_minutes: null, streak_days: 0, studied_today: false })),
      "GET /month": (_b, url) => month(url),
    });
    renderApp("/dashboard");
    expect(await screen.findByText("Pick a daily goal to track today against it.")).toBeInTheDocument();
    expect(screen.getByText("Time any study today to start a streak.")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "0m studied today, no daily goal set" })).toBeInTheDocument();
  });

  it("sets the goal, and turns it off when the chosen goal is clicked again", async () => {
    const mock = open({ "PUT /preferences/daily-goal": () => jsonResponse(200, {}) });
    const user = userEvent.setup();
    await user.click((await cardSoon("Today's progress")).getByRole("button", { name: "3h" }));
    await user.click(card("Today's progress").getByRole("button", { name: "2h" }));
    await waitFor(() =>
      expect(bodiesSent(mock, "PUT /preferences/daily-goal")).toEqual([{ minutes: 180 }, { minutes: null }]),
    );
  });

  it("lists recent sessions with when they ended and how long they took", async () => {
    const ended = DateTime.now().minus({ hours: 2 }).toUTC().toISO();
    stubApi({
      "GET /dashboard": () =>
        jsonResponse(
          200,
          dashboard({}, [
            {
              session_id: "s1",
              task_id: "t1",
              task_title: "Cells",
              course_name: "Biology",
              course_color: "#22aa55",
              ended_at: ended,
              minutes: 58,
            },
          ]),
        ),
      "GET /month": (_b, url) => month(url),
    });
    renderApp("/dashboard");
    const recent = await cardSoon("Recent activity");
    expect(await recent.findByText("Cells")).toBeInTheDocument();
    expect(recent.getByText("Biology · 2h ago")).toBeInTheDocument();
    expect(recent.getByText("58m")).toBeInTheDocument();
  });

  it("explains the empty recent list", async () => {
    open();
    expect(await screen.findByText("Sessions you finish with the timer will show up here.")).toBeInTheDocument();
  });
});

describe("monthly overview", () => {
  it("draws every day of this month and details the selected one", async () => {
    open();
    const overview = await cardSoon("Monthly overview");
    expect(await overview.findByText(today().toFormat("LLLL yyyy"))).toBeInTheDocument();
    const days = await overview.findAllByRole("button", { pressed: false });
    expect(days.length).toBeGreaterThanOrEqual(today().daysInMonth! - 1);
    expect(overview.getByRole("button", { current: "date" })).toHaveAttribute("aria-pressed", "true");

    const fourth = today().set({ day: 4 });
    const user = userEvent.setup();
    await user.click(overview.getByRole("button", { name: `${fourth.toFormat("cccc, LLLL d")}, 1h 30m studied` }));
    const details = within(overview.getByRole("region", { name: "Selected day" }));
    expect(details.getByText(fourth.toFormat("cccc, LLL d"))).toBeInTheDocument();
    expect(within(details.getByRole("list", { name: "Studied" })).getByText("Cells")).toBeInTheDocument();
    expect(within(details.getByRole("list", { name: "Finished" })).getByText("Lab report")).toBeInTheDocument();

    const sixth = today().set({ day: 6 });
    await user.click(overview.getByRole("button", { name: `${sixth.toFormat("cccc, LLLL d")}, no study, 1 deadline` }));
    const due = within(details.getByRole("list", { name: "Due" }));
    expect(due.getByText("Midterm 1")).toBeInTheDocument();
    expect(due.getByText("Midterm · due 3:00 PM")).toBeInTheDocument();
  });

  it("moves between months and back to today", async () => {
    const mock = open();
    const overview = await cardSoon("Monthly overview");
    const user = userEvent.setup();
    await overview.findByText(today().toFormat("LLLL yyyy"));
    await user.click(overview.getByRole("button", { name: "Next month" }));
    const next = today().plus({ months: 1 });
    expect(await overview.findByText(next.toFormat("LLLL yyyy"))).toBeInTheDocument();
    expect(mock.mock.calls.some(([url]) => url === `/api/v1/month?month=${next.toFormat("yyyy-LL")}`)).toBe(true);
    await user.click(overview.getByRole("button", { name: "Today" }));
    expect(await overview.findByText(today().toFormat("LLLL yyyy"))).toBeInTheDocument();
    expect(overview.queryByRole("button", { name: "Today" })).not.toBeInTheDocument();
  });
});
