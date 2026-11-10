import { describe, expect, it } from "vitest";

import {
  formatClock,
  formatDuration,
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

  it("moves a time skipped by spring-forward to a real instant", () => {
    // 02:30 did not exist in Toronto on 2026-03-08.
    const iso = localInputToIso("2026-03-08T02:30", "America/Toronto")!;
    expect(isoToLocalInput(iso, "America/Toronto")).toBe("2026-03-08T03:30");
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
