import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ADA, errorResponse, jsonResponse, session, stubApi } from "../../test/fakeServer";
import { renderApp } from "../../test/renderApp";

const CREATE = {
  id: "c1",
  action: "create",
  task_id: "t1",
  task_title: "Problem set",
  course_name: "Algorithms",
  course_color: "#45bfae",
  before_start_at: null,
  before_end_at: null,
  after_start_at: "2026-11-16T14:00:00Z",
  after_end_at: "2026-11-16T14:50:00Z",
  explanation: "Scheduled now because this needs about 40% of your time before it is due.",
};

const REMOVE = {
  ...CREATE,
  id: "c2",
  action: "remove",
  task_title: "Old reading",
  before_start_at: "2026-11-17T14:00:00Z",
  before_end_at: "2026-11-17T14:30:00Z",
  after_start_at: null,
  after_end_at: null,
  explanation: null,
};

const PROPOSAL = {
  id: "p1",
  status: "pending",
  unchanged_sessions: 3,
  at_risk: [],
  unplaced: [],
  changes: [CREATE, REMOVE],
};

const SESSION = {
  id: "s1",
  task_title: "Essay",
  course_name: null,
  course_color: null,
  start_at: "2026-11-16T14:00:00Z",
  end_at: "2026-11-16T14:50:00Z",
  status: "planned",
  explanation: "You marked this as important, so it goes ahead of less important work.",
};

const none = () => jsonResponse(200, null);
const noSessions = () => jsonResponse(200, []);
const review = () => within(screen.getByRole("region", { name: "Proposed schedule" }));

describe("schedule", () => {
  it("explains what to do when nothing is planned", async () => {
    stubApi({ "GET /schedule/proposals/current": none, "GET /sessions": noSessions });
    renderApp("/schedule");
    expect(await screen.findByText("No study sessions planned")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate schedule" })).toBeInTheDocument();
  });

  it("groups sessions by day in the profile's time zone, with reasons", async () => {
    stubApi({
      "POST /auth/refresh": () =>
        jsonResponse(200, session("t", { ...ADA, timezone: "Asia/Tokyo" })),
      "GET /schedule/proposals/current": none,
      "GET /sessions": () =>
        jsonResponse(200, [{ ...SESSION, start_at: "2026-11-16T16:00:00Z", end_at: "2026-11-16T16:50:00Z" }]),
    });
    renderApp("/schedule");

    // 16:00 UTC on the 16th is already 01:00 on the 17th in Tokyo.
    expect(await screen.findByRole("heading", { name: "Tuesday, November 17" })).toBeInTheDocument();
    expect(screen.getByText("1:00 AM to 1:50 AM")).toBeInTheDocument();
    expect(screen.getByText(/marked this as important/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update schedule" })).toBeInTheDocument();
  });

  it("shows a preview without changing the schedule until applied", async () => {
    stubApi({
      "GET /schedule/proposals/current": none,
      "GET /sessions": noSessions,
      "POST /schedule/preview": () => jsonResponse(201, PROPOSAL),
    });
    renderApp("/schedule");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Generate schedule" }));

    expect(await review().findByText("Problem set")).toBeInTheDocument();
    expect(review().getByText(/1 session to add, 1 to remove, 3 unchanged/)).toBeInTheDocument();
    expect(review().getByText(CREATE.explanation)).toBeInTheDocument();
    expect(review().getByText("Remove")).toBeInTheDocument();
    expect(screen.getByText("No study sessions planned")).toBeInTheDocument();
  });

  it("restores a preview left open earlier", async () => {
    stubApi({
      "GET /schedule/proposals/current": () => jsonResponse(200, PROPOSAL),
      "GET /sessions": noSessions,
    });
    renderApp("/schedule");
    expect(await screen.findByRole("button", { name: "Apply changes" })).toBeInTheDocument();
  });

  it("applies and refreshes the schedule", async () => {
    let applied = false;
    const mock = stubApi({
      "GET /schedule/proposals/current": () => jsonResponse(200, applied ? null : PROPOSAL),
      "GET /sessions": () => jsonResponse(200, applied ? [SESSION] : []),
      "POST /schedule/proposals/p1/apply": () => {
        applied = true;
        return jsonResponse(200, { created: 1, removed: 1 });
      },
    });
    renderApp("/schedule");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Apply changes" }));

    expect(await screen.findByText("Essay")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Proposed schedule" })).not.toBeInTheDocument(),
    );
    expect(mock.mock.calls.some(([url]) => url.endsWith("/p1/apply"))).toBe(true);
  });

  it("discards a preview", async () => {
    let discarded = false;
    stubApi({
      "GET /schedule/proposals/current": () => jsonResponse(200, discarded ? null : PROPOSAL),
      "GET /sessions": noSessions,
      "POST /schedule/proposals/p1/reject": () => {
        discarded = true;
        return new Response(null, { status: 204 });
      },
    });
    renderApp("/schedule");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Discard" }));

    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Proposed schedule" })).not.toBeInTheDocument(),
    );
  });

  it("explains a stale preview and removes it", async () => {
    let stale = false;
    stubApi({
      "GET /schedule/proposals/current": () => jsonResponse(200, stale ? null : PROPOSAL),
      "GET /sessions": noSessions,
      "POST /schedule/proposals/p1/apply": () => {
        stale = true;
        return errorResponse(409, "proposal_stale", "Your schedule or tasks changed after this preview.");
      },
    });
    renderApp("/schedule");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Apply changes" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("changed after this preview");
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Proposed schedule" })).not.toBeInTheDocument(),
    );
  });

  it("reports tasks at risk with their shortfall", async () => {
    stubApi({
      "GET /schedule/proposals/current": () =>
        jsonResponse(200, {
          ...PROPOSAL,
          at_risk: [
            {
              task_id: "t2",
              task_title: "Big essay",
              deadline_at: "2026-11-20T00:00:00Z",
              shortfall_minutes: 150,
              reason: "insufficient_time",
              message: "There is not enough available study time before the deadline.",
            },
          ],
        }),
      "GET /sessions": noSessions,
    });
    renderApp("/schedule");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("1 task at risk");
    expect(alert).toHaveTextContent("Big essay");
    expect(alert).toHaveTextContent("short by 2h 30m");
  });

  it("offers no apply when nothing would change", async () => {
    stubApi({
      "GET /schedule/proposals/current": () => jsonResponse(200, { ...PROPOSAL, changes: [] }),
      "GET /sessions": noSessions,
    });
    renderApp("/schedule");

    expect(await screen.findByText("Your schedule is already up to date")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply changes" })).not.toBeInTheDocument();
  });

  it("shows when generating fails", async () => {
    stubApi({
      "GET /schedule/proposals/current": none,
      "GET /sessions": noSessions,
      "POST /schedule/preview": () => errorResponse(500, "internal_error", "Something went wrong."),
    });
    renderApp("/schedule");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Generate schedule" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong.");
  });
});
