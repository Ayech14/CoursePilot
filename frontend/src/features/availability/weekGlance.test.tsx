import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { jsonResponse, stubApi } from "../../test/fakeServer";
import { renderApp } from "../../test/renderApp";
import { freeMinutes } from "./WeekGlance";

describe("freeMinutes", () => {
  it("takes busy time out of study hours", () => {
    expect(freeMinutes([{ start: 540, end: 1020 }], [{ start: 600, end: 690 }])).toBe(390);
  });

  it("counts overlapping busy times and windows once", () => {
    expect(
      freeMinutes(
        [
          { start: 540, end: 720 },
          { start: 660, end: 780 },
        ],
        [
          { start: 600, end: 660 },
          { start: 630, end: 690 },
          { start: 1200, end: 1260 },
        ],
      ),
    ).toBe(240 - 90);
  });

  it("is zero when busy covers everything", () => {
    expect(freeMinutes([{ start: 540, end: 600 }], [{ start: 500, end: 700 }])).toBe(0);
  });
});

describe("week at a glance", () => {
  it("shows the free study hours each day once weekly commitments are out", async () => {
    stubApi({
      "GET /availability/windows": () =>
        jsonResponse(200, [
          { id: "w1", day_of_week: 0, start_minute: 540, end_minute: 1020 },
          { id: "w2", day_of_week: 1, start_minute: 540, end_minute: 720 },
        ]),
      "GET /availability/recurring-blocks": () =>
        jsonResponse(200, [
          { id: "b1", day_of_week: 0, start_minute: 600, end_minute: 690, title: "Lecture", category: "class" },
          { id: "b2", day_of_week: 4, start_minute: 1020, end_minute: 1260, title: "Shift", category: "work" },
        ]),
      "GET /availability/one-off-blocks": () => jsonResponse(200, []),
      "GET /calendar-feeds": () => jsonResponse(200, []),
      "GET /preferences": () =>
        jsonResponse(200, {
          preferred_session_minutes: 50,
          min_session_minutes: 25,
          break_minutes: 10,
          max_daily_minutes: 360,
          deadline_buffer_hours: 12,
          planning_horizon_days: 28,
        }),
    });
    renderApp("/availability");

    const glance = within(await screen.findByRole("region", { name: "Week at a glance" }));
    expect(await glance.findByText("9h 30m")).toBeInTheDocument();
    const days = glance.getAllByRole("listitem").map((row) => row.textContent);
    expect(days[0]).toBe("MonLectureMonday, free to study: 6h 30m");
    expect(days[1]).toBe("TueTuesday, free to study: 3h");
    // Busy with no study hours that day still shows the commitment, and no free time.
    expect(days[4]).toBe("FriShiftFriday, free to study: None");
  });
});
