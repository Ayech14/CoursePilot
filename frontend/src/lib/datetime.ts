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
  const earliest = DateTime.min(parsed, ...parsed.getPossibleOffsets());
  return earliest!.toUTC().toISO();
}

export function isoToLocalInput(iso: string | null, zone: string): string {
  return iso ? DateTime.fromISO(iso, { zone }).toFormat("yyyy-MM-dd'T'HH:mm") : "";
}

export function formatDateTime(iso: string, zone: string): string {
  const value = DateTime.fromISO(iso, { zone });
  const sameYear = value.year === DateTime.now().setZone(zone).year;
  return value.toFormat(sameYear ? "ccc, LLL d, h:mm a" : "ccc, LLL d yyyy, h:mm a");
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
