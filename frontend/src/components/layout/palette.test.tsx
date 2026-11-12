import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { jsonResponse, stubApi } from "../../test/fakeServer";
import { renderApp } from "../../test/renderApp";
import { matches } from "./CommandPalette";

const COURSE = {
  id: "c1",
  name: "Organic Chemistry",
  code: "CHEM 2020",
  description: null,
  color: "#aa3355",
  archived_at: null,
  created_at: "2026-09-01T00:00:00Z",
  progress: {
    total_tasks: 2,
    completed_tasks: 1,
    estimated_minutes: 240,
    remaining_minutes: 90,
    actual_minutes: 0,
    next_deadline_at: null,
  },
};

function task(id: string, title: string, overrides = {}) {
  return {
    id,
    course_id: "c1",
    title,
    description: null,
    task_type: "midterm",
    deadline_at: "2099-12-01T23:59:00Z",
    estimated_minutes: 120,
    remaining_minutes: 90,
    actual_minutes: 0,
    priority: 2,
    status: "todo",
    completed_at: null,
    ...overrides,
  };
}

const TASKS = [task("t1", "Midterm 2", { status: "completed", remaining_minutes: 0 }), task("t2", "Midterm 1")];

function open(path = "/tasks") {
  const mock = stubApi({
    "GET /calendar-feeds": () => jsonResponse(200, []),
    "GET /deadline-suggestions": () => jsonResponse(200, []),
    "GET /tasks": () => jsonResponse(200, { items: TASKS, total: TASKS.length }),
    "GET /courses": () => jsonResponse(200, [COURSE]),
    "GET /courses/c1": () => jsonResponse(200, COURSE),
  });
  renderApp(path);
  return mock;
}

const options = () => within(screen.getByRole("listbox", { name: "Results" })).getAllByRole("option");

describe("search", () => {
  it("matches every typed word, in any order and any case", () => {
    expect(matches("chem mid", "Midterm 1 Organic Chemistry")).toBe(true);
    expect(matches("  ", "anything")).toBe(true);
    expect(matches("physics", "Midterm 1 Organic Chemistry")).toBe(false);
  });

  it("opens with Ctrl+K and closes with Escape, returning focus", async () => {
    open();
    const user = userEvent.setup();
    await screen.findAllByRole("button", { name: "Search" });
    await user.keyboard("{Control>}k{/Control}");
    const input = await screen.findByRole("combobox", { name: "Search pages, tasks and courses" });
    expect(input).toHaveFocus();
    expect(options().map((o) => o.textContent)).toContain("Analytics");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Search" })).not.toBeInTheDocument();
  });

  it("finds tasks by course, open ones first, and opens the chosen one", async () => {
    open();
    const user = userEvent.setup();
    await user.click((await screen.findAllByRole("button", { name: "Search" }))[0]!);
    await user.type(screen.getByRole("combobox", { name: "Search pages, tasks and courses" }), "chem midterm");
    await waitFor(() => expect(options().map((o) => o.textContent?.split("Organic")[0])).toEqual(["Midterm 1", "Midterm 2"]));
    expect(options()[1]).toHaveTextContent("Done");
    expect(options()[0]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("dialog", { name: "Edit task" })).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toHaveValue("Midterm 1");
  });

  it("moves with the arrow keys and goes to the chosen course", async () => {
    const mock = open();
    const user = userEvent.setup();
    await user.click((await screen.findAllByRole("button", { name: "Search" }))[0]!);
    await user.type(screen.getByRole("combobox", { name: "Search pages, tasks and courses" }), "organic");
    await waitFor(() => expect(options().some((o) => o.textContent?.startsWith("Organic Chemistry"))).toBe(true));
    await user.keyboard("{ArrowDown}{ArrowUp}{ArrowUp}");
    const selected = options().find((o) => o.getAttribute("aria-selected") === "true")!;
    expect(selected).toHaveTextContent("Organic Chemistry");
    await user.keyboard("{Enter}");
    // The course page asks for its course once it opens.
    await waitFor(() => expect(mock.mock.calls.some(([url]) => url === "/api/v1/courses/c1")).toBe(true));
    expect(screen.queryByRole("dialog", { name: "Search" })).not.toBeInTheDocument();
  });

  it("says when nothing matches", async () => {
    open();
    const user = userEvent.setup();
    await user.click((await screen.findAllByRole("button", { name: "Search" }))[0]!);
    await user.type(screen.getByRole("combobox", { name: "Search pages, tasks and courses" }), "zzz");
    expect(screen.getByText("Nothing matches “zzz”.")).toBeInTheDocument();
  });
});
