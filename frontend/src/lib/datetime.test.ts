import { describe, expect, it } from "vitest";

import {
  describeDue,
  formatClock,
  formatDuration,
  formatElapsed,
  hoursToMinutes,
  isoToLocalInput,
  localInputToIso,
  minutesToHours,
  minutesToTimeInput,
  timeInputToMinutes,
} from "./datetime";

describe("localInputToIso", () => {
  it.each([
    ["Asia/Tokyo", "2026-12-01T23:59", "2026-12-01T14:59:00.000Z"],
    ["America/Toronto", "2026-12-01T23:59", "2026-12-02T04:59:00.000Z"],
    ["America/Toronto", "2026-07-01T23:59", "2026-07-02T03:59:00.000Z"],
    ["Asia/Kolkata", "2026-12-01T12:00", "2026-12-01T06:30:00.000Z"],
  ])("reads the value in %s", (zone, input, expected) => {
    expect(localInputToIso(input, zone)).toBe(expected);
  });

  it("gives null for an empty value", () => {
    expect(localInputToIso("", "UTC")).toBeNull();
  });

  it("moves a time skipped by spring-forward to the moment the clocks changed", () => {
    // 02:30 did not exist in Toronto on 2026-03-08.
    const iso = localInputToIso("2026-03-08T02:30", "America/Toronto")!;
    expect(isoToLocalInput(iso, "America/Toronto")).toBe("2026-03-08T03:00");
  });

  it("uses the first occurrence of a time repeated by fall-back", () => {
    // 01:30 happened twice in Toronto on 2026-11-01; the first was EDT, UTC-4.
    expect(localInputToIso("2026-11-01T01:30", "America/Toronto")).toBe("2026-11-01T05:30:00.000Z");
  });
});

describe("isoToLocalInput", () => {
  it("shows the instant in the requested zone", () => {
    expect(isoToLocalInput("2026-12-01T14:59:00Z", "Asia/Tokyo")).toBe("2026-12-01T23:59");
  });

  it("round-trips", () => {
    const iso = localInputToIso("2026-06-15T08:05", "Europe/Paris")!;
    expect(isoToLocalInput(iso, "Europe/Paris")).toBe("2026-06-15T08:05");
  });

  it("gives an empty string for no value", () => {
    expect(isoToLocalInput(null, "UTC")).toBe("");
  });
});

describe("weekly time conversion", () => {
  it.each([
    [0, "00:00"],
    [545, "09:05"],
    [1439, "23:59"],
    [1440, "00:00"],
  ])("%i minutes shows as %s", (minutes, text) => {
    expect(minutesToTimeInput(minutes)).toBe(text);
  });

  it("treats 00:00 as midnight at the start and end of the day at the end", () => {
    expect(timeInputToMinutes("00:00", "start")).toBe(0);
    expect(timeInputToMinutes("00:00", "end")).toBe(1440);
  });

  it("reads ordinary times", () => {
    expect(timeInputToMinutes("13:45", "end")).toBe(825);
  });

  it.each([
    [0, "12:00 AM"],
    [540, "9:00 AM"],
    [750, "12:30 PM"],
    [1440, "12:00 AM"],
  ])("%i formats as %s", (minutes, text) => {
    expect(formatClock(minutes)).toBe(text);
  });
});

describe("effort conversion", () => {
  it.each([
    [45, "45m"],
    [60, "1h"],
    [150, "2h 30m"],
    [0, "0m"],
  ])("%i minutes formats as %s", (minutes, text) => {
    expect(formatDuration(minutes)).toBe(text);
  });

  it("converts hours to whole minutes", () => {
    expect(hoursToMinutes("1.5")).toBe(90);
    expect(hoursToMinutes("0.33")).toBe(20);
  });

  it.each(["", "  ", "abc", "0", "-1"])("rejects %j", (value) => {
    expect(hoursToMinutes(value)).toBeNull();
  });

  it("formats minutes as hours", () => {
    expect(minutesToHours(90)).toBe("1.5");
    expect(minutesToHours(100)).toBe("1.67");
  });
});

describe("clock changes", () => {
  const TORONTO = "America/Toronto";

  it("reads a time that does not exist as the moment the clocks changed", () => {
    expect(localInputToIso("2027-03-14T02:30", TORONTO)).toBe("2027-03-14T07:00:00.000Z");
    expect(localInputToIso("2027-03-14T02:00", TORONTO)).toBe("2027-03-14T07:00:00.000Z");
  });

  it("leaves the minutes around the gap alone", () => {
    expect(localInputToIso("2027-03-14T01:59", TORONTO)).toBe("2027-03-14T06:59:00.000Z");
    expect(localInputToIso("2027-03-14T03:00", TORONTO)).toBe("2027-03-14T07:00:00.000Z");
  });
});

describe("formatElapsed", () => {
  it.each([
    [0, "00:00"],
    [59.9, "00:59"],
    [600, "10:00"],
    [3661, "1:01:01"],
    [-5, "00:00"],
  ])("shows %s seconds as %s", (seconds, text) => {
    expect(formatElapsed(seconds)).toBe(text);
  });
});

describe("describeDue", () => {
  const zone = "America/Toronto";
  // 8 PM on Tuesday, Nov 10 2026 in Toronto.
  const now = new Date("2026-11-11T01:00:00Z");

  it("counts calendar days in the profile's zone, not hours", () => {
    expect(describeDue("2026-11-11T04:59:00Z", zone, now)).toEqual({ label: "Due today", tone: "danger" });
    expect(describeDue("2026-11-11T05:30:00Z", zone, now)).toEqual({ label: "Due tomorrow", tone: "accent" });
    expect(describeDue("2026-11-13T17:00:00Z", zone, now)).toEqual({ label: "In 3 days", tone: "accent" });
    expect(describeDue("2026-11-15T17:00:00Z", zone, now)).toEqual({ label: "In 5 days", tone: "neutral" });
    expect(describeDue("2026-11-30T17:00:00Z", zone, now)).toEqual({ label: "Nov 30", tone: "neutral" });
  });

  it("flags deadlines that have passed", () => {
    expect(describeDue("2026-11-10T12:00:00Z", zone, now)).toEqual({ label: "Overdue", tone: "danger" });
  });

  it("uses the same instant differently for someone in another zone", () => {
    // 11:30 PM Toronto is already the next day in Tokyo.
    expect(describeDue("2026-11-11T04:30:00Z", "Asia/Tokyo", now).label).toBe("Due today");
    expect(describeDue("2026-11-11T04:30:00Z", zone, now).label).toBe("Due today");
    expect(describeDue("2026-11-11T16:00:00Z", "Asia/Tokyo", now).label).toBe("Due tomorrow");
  });

  it("stays right across a 25-hour day when clocks go back", () => {
    // Clocks went back on Nov 1 2026. Saturday 8 PM to Monday 9 AM is two calendar days.
    const saturday = new Date("2026-11-01T00:00:00Z");
    expect(describeDue("2026-11-02T14:00:00Z", zone, saturday).label).toBe("In 2 days");
  });
});
