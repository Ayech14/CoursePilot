import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { bodiesSent, errorResponse, jsonResponse, stubApi } from "../../test/fakeServer";
import { renderApp } from "../../test/renderApp";

const COURSE = { id: "c1", name: "Biology", code: "BIO1", color: "#22aa55", archived_at: null };

function task(id: string, title: string, overrides = {}) {
  return {
    id,
    course_id: null,
    title,
    description: null,
    task_type: "assignment",
    deadline_at: "2099-12-01T23:59:00Z",
    estimated_minutes: 120,
    remaining_minutes: 90,
    actual_minutes: 30,
    priority: 2,
    status: "todo",
    completed_at: null,
    ...overrides,
  };
}

const TASKS = [task("t1", "Essay"), task("t2", "Cells", { course_id: "c1" })];

const started = {
  session: {
    id: "s9",
    task_id: "t2",
    task_title: "Cells",
    course_name: "Biology",
    course_color: "#22aa55",
    start_at: new Date().toISOString(),
    end_at: new Date(Date.now() + 50 * 60_000).toISOString(),
    status: "in_progress",
    origin: "manual",
    is_locked: false,
    is_user_modified: false,
    explanation: null,
    actual_minutes: 0,
  },
  running: true,
  elapsed_seconds: 0,
};

const routes = {
  "GET /tasks": () => jsonResponse(200, { items: TASKS, total: TASKS.length }),
  "GET /courses": () => jsonResponse(200, [COURSE]),
  "GET /schedule/proposals/current": () => jsonResponse(200, null),
  "GET /schedule/status": () => jsonResponse(200, { needs_update: false }),
  "GET /sessions": () => jsonResponse(200, []),
  "GET /availability/windows": () => jsonResponse(200, []),
  "GET /calendar-feeds": () => jsonResponse(200, []),
  "GET /deadline-suggestions": () => jsonResponse(200, []),
};

const dialog = () => within(screen.getByRole("dialog"));

describe("start a timer on any task", () => {
  it("lets the student pick an open task from the schedule and start it", async () => {
    let active: unknown = null;
    const mock = stubApi({
      ...routes,
      "GET /sessions/active": () => jsonResponse(200, active),
      "POST /sessions/quick-start": () => {
        active = started;
        return jsonResponse(200, started);
      },
    });
    renderApp("/schedule");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start timer" }));
    const choice = await dialog().findByRole("combobox", { name: "What are you working on?" });
    expect(within(choice).getByRole("option", { name: "Cells (Biology)" })).toBeInTheDocument();
    await user.selectOptions(choice, "t2");
    await user.click(dialog().getByRole("button", { name: "Start timer" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(bodiesSent(mock, "POST /sessions/quick-start")).toEqual([{ task_id: "t2" }]);
    expect(await screen.findByRole("region", { name: "Study timer" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start timer" })).toBeDisabled();
  });

  it("shows the server's reason when the time is taken", async () => {
    stubApi({
      ...routes,
      "POST /sessions/quick-start": () =>
        errorResponse(409, "session_conflict", "You have “Lab” planned right now. Start that session, or move it first."),
    });
    renderApp("/schedule");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start timer" }));
    await dialog().findByRole("combobox");
    await user.click(dialog().getByRole("button", { name: "Start timer" }));
    expect(await dialog().findByText(/planned right now/)).toBeInTheDocument();
  });

  it("starts from a task row with that task already chosen", async () => {
    const mock = stubApi({ ...routes, "POST /sessions/quick-start": () => jsonResponse(200, started) });
    renderApp("/tasks");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Start timer on Cells" }));
    expect(await dialog().findByRole("combobox")).toHaveValue("t2");
    await user.click(dialog().getByRole("button", { name: "Start timer" }));
    await waitFor(() => expect(bodiesSent(mock, "POST /sessions/quick-start")).toEqual([{ task_id: "t2" }]));
  });

  it("says so when there is nothing open to time", async () => {
    stubApi({ ...routes, "GET /tasks": () => jsonResponse(200, { items: [], total: 0 }) });
    renderApp("/schedule");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Start timer" }));
    expect(await dialog().findByText("You have no open tasks to time. Add a task first.")).toBeInTheDocument();
    expect(dialog().getByRole("button", { name: "Start timer" })).toBeDisabled();
  });
});
