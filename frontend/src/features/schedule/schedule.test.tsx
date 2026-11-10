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
} from "../../test/fakeServer";
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
  session_id: null,
  sticky_released: false,
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
  stability_percent: 75,
  at_risk: [],
  unplaced: [],
  changes: [CREATE, REMOVE],
};

const SESSION = {
  id: "s1",
  task_id: "t1",
  origin: "auto",
  is_locked: false,
  is_user_modified: false,
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
    expect(review().getByText(/1 to add, 1 to remove, 3 unchanged \(75% of your plan\)/)).toBeInTheDocument();
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

  it("applies only the changes left ticked", async () => {
    const mock = stubApi({
      "GET /schedule/proposals/current": () => jsonResponse(200, PROPOSAL),
      "GET /sessions": noSessions,
      "POST /schedule/proposals/p1/apply": () =>
        jsonResponse(200, { created: 1, moved: 0, resized: 0, removed: 0, skipped: 1 }),
    });
    renderApp("/schedule");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("checkbox", { name: /Accept: Remove Old reading/ }));
    await user.click(screen.getByRole("button", { name: "Apply selected" }));

    await waitFor(() =>
      expect(bodiesSent(mock, "POST /schedule/proposals/p1/apply")).toEqual([
        { rejected_change_ids: ["c2"] },
      ]),
    );
  });

  it("cannot apply when every change is unticked", async () => {
    stubApi({
      "GET /schedule/proposals/current": () => jsonResponse(200, { ...PROPOSAL, changes: [CREATE] }),
      "GET /sessions": noSessions,
    });
    renderApp("/schedule");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("checkbox", { name: /Accept/ }));

    expect(screen.getByRole("button", { name: "Apply selected" })).toBeDisabled();
  });

  it("shows where a session moves from and flags overridden edits", async () => {
    const MOVE = {
      ...CREATE,
      id: "c3",
      action: "move",
      session_id: "s9",
      before_start_at: "2026-11-15T15:00:00Z",
      before_end_at: "2026-11-15T15:50:00Z",
      sticky_released: true,
      explanation: "This time is no longer in your weekly study hours.",
    };
    stubApi({
      "GET /schedule/proposals/current": () => jsonResponse(200, { ...PROPOSAL, changes: [MOVE] }),
      "GET /sessions": noSessions,
    });
    renderApp("/schedule");

    await screen.findByRole("region", { name: "Proposed schedule" });
    expect(review().getByText(/^From /)).toBeInTheDocument();
    expect(review().getByText(/placed this session yourself/)).toBeInTheDocument();
  });

  it("offers an update when events call for one", async () => {
    const mock = stubApi({
      "GET /schedule/proposals/current": none,
      "GET /sessions": () => jsonResponse(200, [SESSION]),
      "GET /schedule/status": () =>
        jsonResponse(200, {
          needs_update: true,
          added: 1,
          moved: 0,
          resized: 0,
          removed: 0,
          missed_sessions: 1,
          at_risk: 0,
        }),
      "POST /schedule/preview": () => jsonResponse(201, PROPOSAL),
    });
    renderApp("/schedule");
    const user = userEvent.setup();

    const banner = await screen.findByRole("region", { name: "Schedule needs an update" });
    expect(banner).toHaveTextContent("1 missed session and 1 suggested change");
    await user.click(within(banner).getByRole("button", { name: "Review changes" }));

    await waitFor(() =>
      expect(bodiesSent(mock, "POST /schedule/preview")).toEqual([{ mode: "repair" }]),
    );
  });

  it("offers a full rebuild once a schedule exists", async () => {
    const mock = stubApi({
      "GET /schedule/proposals/current": none,
      "GET /sessions": () => jsonResponse(200, [SESSION]),
      "POST /schedule/preview": () => jsonResponse(201, PROPOSAL),
    });
    renderApp("/schedule");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Rebuild from scratch" }));

    await waitFor(() =>
      expect(bodiesSent(mock, "POST /schedule/preview")).toEqual([{ mode: "regenerate" }]),
    );
  });

  it("locks a session", async () => {
    const mock = stubApi({
      "GET /schedule/proposals/current": none,
      "GET /sessions": () => jsonResponse(200, [SESSION]),
      "POST /sessions/s1/lock": () => jsonResponse(200, { ...SESSION, is_locked: true }),
    });
    renderApp("/schedule");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /^Lock Essay/ }));

    await waitFor(() =>
      expect(mock.mock.calls.some(([url]) => url.endsWith("/s1/lock"))).toBe(true),
    );
  });

  it("marks locked and edited sessions", async () => {
    stubApi({
      "GET /schedule/proposals/current": none,
      "GET /sessions": () =>
        jsonResponse(200, [
          { ...SESSION, is_locked: true },
          { ...SESSION, id: "s2", is_user_modified: true, start_at: "2026-11-16T16:00:00Z", end_at: "2026-11-16T16:30:00Z" },
        ]),
    });
    renderApp("/schedule");

    expect(await screen.findByText("Locked")).toBeInTheDocument();
    expect(screen.getByText("Edited by you")).toBeInTheDocument();
  });

  it("removes a session after confirmation", async () => {
    const mock = stubApi({
      "GET /schedule/proposals/current": none,
      "GET /sessions": () => jsonResponse(200, [SESSION]),
      "DELETE /sessions/s1": () => new Response(null, { status: 204 }),
    });
    renderApp("/schedule");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /^Remove Essay/ }));
    await user.click(screen.getByRole("button", { name: "Remove session" }));

    await waitFor(() =>
      expect(mock.mock.calls.some(([, init]) => init.method === "DELETE")).toBe(true),
    );
  });

  describe("changing a session", () => {
    const ALTERNATIVE = { start_at: "2026-11-16T18:00:00Z", end_at: "2026-11-16T18:50:00Z" };
    const inTokyo = () => jsonResponse(200, session("t", { ...ADA, timezone: "Asia/Tokyo" }));

    async function open(routes: Parameters<typeof stubApi>[0]) {
      const mock = stubApi({
        "POST /auth/refresh": inTokyo,
        "GET /schedule/proposals/current": none,
        "GET /sessions": () => jsonResponse(200, [SESSION]),
        ...routes,
      });
      renderApp("/schedule");
      const user = userEvent.setup();
      await user.click(await screen.findByRole("button", { name: /^Change Essay/ }));
      return { mock, user, dialog: within(screen.getByRole("dialog")) };
    }

    it("saves a new time and length in the profile's zone", async () => {
      const { mock, user, dialog } = await open({
        "PATCH /sessions/s1": () => jsonResponse(200, SESSION),
      });

      fireEvent.change(dialog.getByLabelText("Starts"), { target: { value: "2026-11-20T09:00" } });
      await user.clear(dialog.getByLabelText("Length (minutes)"));
      await user.type(dialog.getByLabelText("Length (minutes)"), "30");
      await user.click(dialog.getByRole("button", { name: "Save" }));

      await waitFor(() =>
        expect(bodiesSent(mock, "PATCH /sessions/s1")).toEqual([
          {
            start_at: "2026-11-20T00:00:00.000Z",
            end_at: "2026-11-20T00:30:00.000Z",
            acknowledge_warnings: false,
          },
        ]),
      );
    });

    it("shows a conflict and lets you pick a suggested time", async () => {
      const { user, dialog } = await open({
        "PATCH /sessions/s1": () =>
          errorResponse(409, "session_conflict", "That time is not available.", {
            ok: false,
            conflicts: [{ kind: "overlap", message: "This overlaps another study session.", session_id: "s2" }],
            warnings: [],
            alternatives: [ALTERNATIVE],
          }),
      });

      await user.click(dialog.getByRole("button", { name: "Save" }));

      expect(await dialog.findByText("This overlaps another study session.")).toBeInTheDocument();
      expect(dialog.queryByRole("button", { name: "Keep this time anyway" })).toBeNull();
      await user.click(dialog.getByRole("button", { name: /3:00 AM/ }));
      expect(dialog.getByLabelText("Starts")).toHaveValue("2026-11-17T03:00");
    });

    it("asks before keeping a time that bends the student's own rules", async () => {
      let calls = 0;
      const { mock, user, dialog } = await open({
        "PATCH /sessions/s1": () =>
          ++calls === 1
            ? errorResponse(409, "placement_warnings", "Confirm.", {
                ok: false,
                conflicts: [],
                warnings: [{ kind: "daily_limit", message: "This puts the day over your daily study limit." }],
                alternatives: [],
              })
            : jsonResponse(200, SESSION),
      });

      await user.click(dialog.getByRole("button", { name: "Save" }));
      await user.click(await dialog.findByRole("button", { name: "Keep this time anyway" }));

      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      expect(bodiesSent(mock, "PATCH /sessions/s1").map((b) => b.acknowledge_warnings)).toEqual([false, true]);
    });
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
