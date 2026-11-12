import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DateTime } from "luxon";

import { bodiesSent, errorResponse, jsonResponse, stubApi } from "../../test/fakeServer";
import { renderApp } from "../../test/renderApp";

const inToronto = () => DateTime.now().setZone("America/Toronto");

function makeSession(overrides = {}) {
  const start = inToronto().startOf("day").plus({ hours: 9 });
  return {
    id: "s1",
    task_id: "t1",
    origin: "auto",
    is_locked: false,
    is_user_modified: false,
    task_title: "Essay",
    course_name: null,
    course_color: null,
    start_at: start.toUTC().toISO(),
    end_at: start.plus({ minutes: 50 }).toUTC().toISO(),
    status: "planned",
    actual_minutes: 0,
    explanation: null,
    ...overrides,
  };
}

const timer = (overrides = {}) => ({
  session: makeSession({ status: "in_progress" }),
  running: true,
  elapsed_seconds: 125,
  ...overrides,
});

const base = {
  "GET /dashboard": () => jsonResponse(200, null),
  "GET /schedule/proposals/current": () => jsonResponse(200, null),
  "GET /schedule/status": () => jsonResponse(200, { needs_update: false }),
  "GET /sessions": () => jsonResponse(200, [makeSession()]),
};

const bar = () => within(screen.getByRole("region", { name: "Study timer" }));

async function openList(extra = {}) {
  localStorage.setItem("coursepilot.schedule.view", "list");
  const mock = stubApi({ ...base, ...extra });
  renderApp("/schedule");
  await screen.findAllByText("Essay");
  return mock;
}

describe("study timer", () => {
  it("shows no timer when nothing is open", async () => {
    await openList();
    expect(screen.queryByRole("region", { name: "Study timer" })).not.toBeInTheDocument();
  });

  it("starts today's session", async () => {
    let open = false;
    await openList({
      "GET /sessions/active": () => jsonResponse(200, open ? timer() : null),
      "POST /sessions/s1/start": () => {
        open = true;
        return jsonResponse(200, timer({ elapsed_seconds: 0 }));
      },
    });
    await userEvent.setup().click(screen.getByRole("button", { name: /Start Essay/ }));
    expect(await screen.findByRole("timer")).toHaveTextContent("02:05");
  });

  it("does not offer Start for a later day", async () => {
    const tomorrow = inToronto().plus({ days: 1 }).startOf("day").plus({ hours: 9 });
    await openList({
      "GET /sessions": () =>
        jsonResponse(200, [
          makeSession({
            start_at: tomorrow.toUTC().toISO(),
            end_at: tomorrow.plus({ minutes: 50 }).toUTC().toISO(),
          }),
        ]),
    });
    expect(screen.queryByRole("button", { name: /Start Essay/ })).not.toBeInTheDocument();
  });

  it("does not allow starting while another session is open", async () => {
    await openList({
      "GET /sessions/active": () => jsonResponse(200, timer({ session: makeSession({ id: "other", status: "paused", task_title: "Other" }), running: false })),
    });
    await bar().findByText("Other");
    expect(screen.getByRole("button", { name: /Start Essay/ })).toBeDisabled();
  });

  it("shows why a start was refused", async () => {
    await openList({
      "POST /sessions/s1/start": () => errorResponse(409, "timer_state", "This session cannot do that right now."),
    });
    await userEvent.setup().click(screen.getByRole("button", { name: /Start Essay/ }));
    expect(await screen.findByText("This session cannot do that right now.")).toBeInTheDocument();
  });

  it("pauses and resumes", async () => {
    let running = true;
    const mock = await openList({
      "GET /sessions/active": () => jsonResponse(200, timer({ running })),
      "POST /sessions/s1/pause": () => {
        running = false;
        return jsonResponse(200, timer({ running }));
      },
      "POST /sessions/s1/resume": () => {
        running = true;
        return jsonResponse(200, timer({ running }));
      },
    });
    const user = userEvent.setup();
    await user.click(await bar().findByRole("button", { name: "Pause" }));
    await user.click(await bar().findByRole("button", { name: "Resume" }));
    expect(await bar().findByRole("button", { name: "Pause" })).toBeInTheDocument();
    expect(mock.mock.calls.filter(([url]) => url.endsWith("/pause"))).toHaveLength(1);
  });

  it("finishes with the timer's own total when left alone", async () => {
    const mock = await openList({
      "GET /sessions/active": () => jsonResponse(200, timer()),
      "POST /sessions/s1/finish": () => jsonResponse(200, makeSession({ status: "completed" })),
    });
    const user = userEvent.setup();
    await user.click(await bar().findByRole("button", { name: "Finish" }));
    await user.click(screen.getByRole("button", { name: "Finish session" }));
    await waitFor(() =>
      expect(bodiesSent(mock, "POST /sessions/s1/finish")).toEqual([{ mark_task_completed: false }]),
    );
  });

  it("sends a correction, hours left and completion only when given", async () => {
    const mock = await openList({
      "GET /sessions/active": () => jsonResponse(200, timer({ elapsed_seconds: 3600 })),
      "POST /sessions/s1/finish": () => jsonResponse(200, makeSession({ status: "completed" })),
    });
    const user = userEvent.setup();
    await user.click(await bar().findByRole("button", { name: "Finish" }));
    const counted = screen.getByLabelText(/Time to count/);
    await user.clear(counted);
    await user.type(counted, "20");
    await user.type(screen.getByLabelText(/Hours of work left/), "1.5");
    await user.click(screen.getByRole("button", { name: "Finish session" }));
    await waitFor(() =>
      expect(bodiesSent(mock, "POST /sessions/s1/finish")).toEqual([
        { mark_task_completed: false, actual_minutes: 20, remaining_minutes: 90 },
      ]),
    );
  });

  it("hides hours left once the task is marked finished", async () => {
    const mock = await openList({
      "GET /sessions/active": () => jsonResponse(200, timer()),
      "POST /sessions/s1/finish": () => jsonResponse(200, makeSession({ status: "completed" })),
    });
    const user = userEvent.setup();
    await user.click(await bar().findByRole("button", { name: "Finish" }));
    await user.click(screen.getByRole("checkbox", { name: "This task is finished" }));
    expect(screen.queryByLabelText(/Hours of work left/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Finish session" }));
    await waitFor(() =>
      expect(bodiesSent(mock, "POST /sessions/s1/finish")).toEqual([{ mark_task_completed: true }]),
    );
  });

  it("explains a correction the server refused", async () => {
    await openList({
      "GET /sessions/active": () => jsonResponse(200, timer()),
      "POST /sessions/s1/finish": () =>
        errorResponse(422, "validation_error", "The submitted data is invalid.", [
          { field: "actual_minutes", message: "The timer recorded 2 minutes. Enter that or less." },
        ]),
    });
    const user = userEvent.setup();
    await user.click(await bar().findByRole("button", { name: "Finish" }));
    await user.click(screen.getByRole("button", { name: "Finish session" }));
    expect(await screen.findByText(/The timer recorded 2 minutes/)).toBeInTheDocument();
  });

  it("discards only after confirming", async () => {
    let open = true;
    const mock = await openList({
      "GET /sessions/active": () => jsonResponse(200, open ? timer() : null),
      "POST /sessions/s1/discard": () => {
        open = false;
        return new Response(null, { status: 204 });
      },
    });
    const user = userEvent.setup();
    await user.click(await bar().findByRole("button", { name: "Discard" }));
    expect(mock.mock.calls.filter(([url]) => url.endsWith("/discard"))).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Discard timer" }));
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Study timer" })).not.toBeInTheDocument(),
    );
  });

  it("warns that discarding an on-the-spot session removes it", async () => {
    await openList({
      "GET /sessions/active": () =>
        jsonResponse(200, timer({ session: makeSession({ status: "in_progress", unplanned: true }) })),
    });
    await userEvent.setup().click(await bar().findByRole("button", { name: "Discard" }));
    expect(screen.getByText("The time won't be recorded, and this session is removed from your schedule.")).toBeInTheDocument();
  });

  describe("counting", () => {
    beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
    afterEach(() => vi.useRealTimers());

    it("counts while running and holds still while paused", async () => {
      await openList({ "GET /sessions/active": () => jsonResponse(200, timer({ elapsed_seconds: 10 })) });
      const clock = await screen.findByRole("timer");
      const before = clock.textContent;
      await act(() => vi.advanceTimersByTimeAsync(5000));
      expect(clock.textContent).not.toBe(before);
    });

    it("does not count while paused", async () => {
      await openList({ "GET /sessions/active": () => jsonResponse(200, timer({ elapsed_seconds: 10, running: false })) });
      const clock = await screen.findByRole("timer");
      await act(() => vi.advanceTimersByTimeAsync(5000));
      expect(clock).toHaveTextContent("00:10");
    });
  });
});
