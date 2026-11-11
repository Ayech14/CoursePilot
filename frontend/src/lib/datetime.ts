/**
 * Conversions between what the student sees and what the API stores.
 *
 * Every function takes the zone explicitly and uses the student's profile zone. The browser's zone
 * is deliberately ignored: someone travelling should still see "Friday 23:59" for their course.
 */
import { DateTime } from "luxon";

/** Convert a `datetime-local` value, read in `zone`, to a UTC ISO string. Empty gives null. */
export function localInputToIso(value: string, zone: string): string | null {
  if (!value) return null;
  const parsed = DateTime.fromISO(value, { zone });
  if (!parsed.isValid) return null;
  // When clocks go back an hour repeats. Use its first occurrence, as the scheduler does.
  const earliest = DateTime.min(parsed, ...parsed.getPossibleOffsets())!;
  return firstValidInstant(earliest, value, zone).toUTC().toISO();
}

/** When clocks go forward a time may not exist. Use the moment the clocks changed, as the scheduler does. */
function firstValidInstant(resolved: DateTime, value: string, zone: string): DateTime {
  const asWritten = DateTime.fromISO(value, { zone: "utc" });
  if (resolved.hour === asWritten.hour && resolved.minute === asWritten.minute) return resolved;
  let instant = resolved;
  while (instant.minus({ minutes: 1 }).setZone(zone).offset === resolved.offset) {
    instant = instant.minus({ minutes: 1 });
  }
  return instant;
}

export function isoToLocalInput(iso: string | null, zone: string): string {
  return iso ? DateTime.fromISO(iso, { zone }).toFormat("yyyy-MM-dd'T'HH:mm") : "";
}

export function formatDateTime(iso: string, zone: string): string {
  const value = DateTime.fromISO(iso, { zone });
  const sameYear = value.year === DateTime.now().setZone(zone).year;
  return value.toFormat(sameYear ? "ccc, LLL d, h:mm a" : "ccc, LLL d yyyy, h:mm a");
}

export function formatShortDate(iso: string, zone?: string): string {
  return DateTime.fromISO(iso, zone ? { zone } : undefined).toFormat("LLL d");
}

export function formatDayHeading(iso: string, zone: string): string {
  return DateTime.fromISO(iso, { zone }).toFormat("cccc, LLLL d");
}

export function formatTime(iso: string, zone: string): string {
  return DateTime.fromISO(iso, { zone }).toFormat("h:mm a");
}

export function minutesBetween(startIso: string, endIso: string): number {
  return Math.round(DateTime.fromISO(endIso).diff(DateTime.fromISO(startIso), "minutes").minutes);
}

/** Group items under the local date they fall on, keeping their order. */
export function groupByLocalDay<T>(
  items: T[],
  instantOf: (item: T) => string,
  zone: string,
): { heading: string; items: T[] }[] {
  const groups = new Map<string, { heading: string; items: T[] }>();
  for (const item of items) {
    const iso = instantOf(item);
    const key = DateTime.fromISO(iso, { zone }).toISODate()!;
    const group = groups.get(key) ?? { heading: formatDayHeading(iso, zone), items: [] };
    group.items.push(item);
    groups.set(key, group);
  }
  return [...groups.values()];
}

/** A UTC ISO instant the given number of minutes after another. */
export function addMinutes(iso: string, minutes: number): string {
  return DateTime.fromISO(iso).plus({ minutes }).toUTC().toISO()!;
}

/** Whether a session falls on today, or earlier, on the student's own calendar. */
export function isTodayOrEarlier(iso: string, zone: string): boolean {
  return DateTime.fromISO(iso, { zone }).startOf("day") <= DateTime.now().setZone(zone).startOf("day");
}

export function formatElapsed(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(seconds / 3600);
  const clock = `${pad(Math.floor((seconds % 3600) / 60))}:${pad(seconds % 60)}`;
  return hours > 0 ? `${hours}:${clock}` : clock;
}

export function isPast(iso: string): boolean {
  return DateTime.fromISO(iso) < DateTime.now();
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/** Minutes since midnight to a `time` input value. 1440, the end of the day, shows as 00:00. */
export function minutesToTimeInput(minutes: number): string {
  const wrapped = minutes % 1440;
  return `${pad(Math.floor(wrapped / 60))}:${pad(wrapped % 60)}`;
}

/** A `time` input cannot show 24:00, so an end time of 00:00 means the end of that day. */
export function timeInputToMinutes(value: string, kind: "start" | "end"): number {
  const [hours = NaN, mins = NaN] = value.split(":").map(Number);
  const total = hours * 60 + mins;
  return kind === "end" && total === 0 ? 1440 : total;
}

export function formatClock(minutes: number): string {
  const wrapped = minutes % 1440;
  const hours = Math.floor(wrapped / 60);
  return `${hours % 12 || 12}:${pad(wrapped % 60)} ${hours < 12 ? "AM" : "PM"}`;
}

export function formatDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest}m`;
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`;
}

/** Parse an hours field to whole minutes. Returns null when it is not a positive number. */
export function hoursToMinutes(value: string): number | null {
  const hours = Number(value);
  return value.trim() === "" || !Number.isFinite(hours) || hours <= 0
    ? null
    : Math.round(hours * 60);
}

export function minutesToHours(minutes: number): string {
  return String(Math.round((minutes / 60) * 100) / 100);
}

export type DueTone = "danger" | "accent" | "neutral";

/**
 * How soon a deadline is, counted in calendar days on the student's own calendar, so that
 * 23:59 tonight is "today" and 00:30 tomorrow is "tomorrow" even if they are an hour apart.
 */
export function describeDue(iso: string, zone: string, now: Date = new Date()): { label: string; tone: DueTone } {
  const due = DateTime.fromISO(iso, { zone });
  const current = DateTime.fromJSDate(now, { zone });
  if (due < current) return { label: "Overdue", tone: "danger" };
  const days = Math.round(due.startOf("day").diff(current.startOf("day"), "days").days);
  if (days === 0) return { label: "Due today", tone: "danger" };
  if (days === 1) return { label: "Due tomorrow", tone: "accent" };
  if (days <= 6) return { label: `In ${days} days`, tone: days <= 3 ? "accent" : "neutral" };
  return { label: due.toFormat("LLL d"), tone: "neutral" };
}
