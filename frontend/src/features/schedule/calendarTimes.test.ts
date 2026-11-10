import { Calendar } from "@fullcalendar/core";
import luxonPlugin from "@fullcalendar/luxon3";
import timeGridPlugin from "@fullcalendar/timegrid";
import { describe, expect, it } from "vitest";

import { movedTimes, resizedTimes } from "./calendarTimes";

const ZONE = "America/Toronto";

/** What the real calendar reports after an event moves, in the student's zone. */
function afterMoving(startIso: string, endIso: string, minutes: number) {
  const calendar = new Calendar(document.createElement("div"), {
    plugins: [timeGridPlugin, luxonPlugin],
    timeZone: ZONE,
    events: [],
  });
  const event = calendar.addEvent({ id: "s", start: startIso, end: endIso })!;
  event.moveDates({ minutes });
  return event;
}

describe("movedTimes", () => {
  const original = { start_at: "2026-10-20T14:00:00Z", end_at: "2026-10-20T14:50:00Z" };

  it("converts an ordinary drop and keeps the length", () => {
    expect(movedTimes("2026-10-21T15:30:00-04:00", original, ZONE)).toEqual({
      start_at: "2026-10-21T19:30:00.000Z",
      end_at: "2026-10-21T20:20:00.000Z",
    });
  });

  it("uses the first occurrence of a repeated hour, unlike the calendar", () => {
    const event = afterMoving("2026-11-01T05:00:00Z", "2026-11-01T05:30:00Z", 30);
    // The calendar's own answer is the second 01:30, which is 06:30 UTC.
    expect(event.start!.toISOString()).toBe("2026-11-01T06:30:00.000Z");
    const times = movedTimes(event.startStr, { start_at: "2026-11-01T05:00:00Z", end_at: "2026-11-01T05:30:00Z" }, ZONE);
    expect(times.start_at).toBe("2026-11-01T05:30:00.000Z");
    expect(times.end_at).toBe("2026-11-01T06:00:00.000Z");
  });

  it("moves a drop in the spring gap to when the clocks changed, unlike the calendar", () => {
    // 01:00 EST on the day clocks go forward, moved 90 minutes to a 02:30 that never happens.
    const event = afterMoving("2027-03-14T06:00:00Z", "2027-03-14T06:50:00Z", 90);
    expect(event.startStr.slice(0, 16)).toBe("2027-03-14T02:30");
    const times = movedTimes(event.startStr, { start_at: "2027-03-14T06:00:00Z", end_at: "2027-03-14T06:50:00Z" }, ZONE);
    expect(times).toEqual({ start_at: "2027-03-14T07:00:00.000Z", end_at: "2027-03-14T07:50:00.000Z" });
  });

  it("keeps the real length when a session lands across the repeated hour", () => {
    const times = movedTimes(
      "2026-11-01T01:30:00-04:00",
      { start_at: "2026-10-31T14:00:00Z", end_at: "2026-10-31T15:00:00Z" },
      ZONE,
    );
    expect(times).toEqual({ start_at: "2026-11-01T05:30:00.000Z", end_at: "2026-11-01T06:30:00.000Z" });
  });
});

describe("resizedTimes", () => {
  it("keeps the start and changes the end", () => {
    const original = { start_at: "2026-10-20T14:00:00Z", end_at: "2026-10-20T14:50:00Z" };
    expect(resizedTimes("2026-10-20T11:15:00-04:00", original, ZONE)).toEqual({
      start_at: original.start_at,
      end_at: "2026-10-20T15:15:00.000Z",
    });
  });

  it("uses the first end after the start in a repeated hour", () => {
    // Starts in the second 01:10. The first 01:30 would be before it.
    const original = { start_at: "2026-11-01T06:10:00Z", end_at: "2026-11-01T06:20:00Z" };
    expect(resizedTimes("2026-11-01T01:30:00-05:00", original, ZONE).end_at).toBe("2026-11-01T06:30:00.000Z");
  });

  it("uses the first occurrence when that is after the start", () => {
    const original = { start_at: "2026-11-01T05:10:00Z", end_at: "2026-11-01T05:20:00Z" };
    expect(resizedTimes("2026-11-01T01:30:00-04:00", original, ZONE).end_at).toBe("2026-11-01T05:30:00.000Z");
  });
});
