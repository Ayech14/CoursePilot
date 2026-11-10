/**
 * Turns what FullCalendar reports after a drag into the instants we send to the API.
 *
 * The calendar's own conversion disagrees with our rules at daylight saving changes: it picks the
 * second occurrence of a repeated hour and an hour too early for a time that does not exist. So
 * we read only the wall-clock time the student dropped on, which is the first 16 characters of
 * its ISO string, and convert that ourselves. See the spike in docs/ARCHITECTURE.md.
 */
import { DateTime } from "luxon";

import { addMinutes, localInputToIso, minutesBetween } from "../../lib/datetime";

interface Times {
  start_at: string;
  end_at: string;
}

function wallClock(calendarIso: string): string {
  return calendarIso.slice(0, 16);
}

/** A move keeps the session's real length, even when it lands across a clock change. */
export function movedTimes(startStr: string, original: Times, zone: string): Times {
  const start = localInputToIso(wallClock(startStr), zone)!;
  return { start_at: start, end_at: addMinutes(start, minutesBetween(original.start_at, original.end_at)) };
}

/** A resize keeps the start. A repeated hour has two instants, so use the first one after it. */
export function resizedTimes(endStr: string, original: Times, zone: string): Times {
  const first = localInputToIso(wallClock(endStr), zone)!;
  const candidates = [DateTime.fromISO(first), ...DateTime.fromISO(first, { zone }).getPossibleOffsets()];
  const start = DateTime.fromISO(original.start_at);
  const end = candidates.filter((c) => c > start).sort((a, b) => a.toMillis() - b.toMillis())[0];
  return { start_at: original.start_at, end_at: (end ?? candidates[0]!).toUTC().toISO()! };
}
