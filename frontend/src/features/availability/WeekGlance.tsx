import { formatClock, formatDuration } from "../../lib/datetime";
import { categoryLabel, DAYS, type RecurringBlock, type WeeklyTime } from "./api";

interface Range {
  start: number;
  end: number;
}

const toRange = (item: WeeklyTime): Range => ({ start: item.start_minute, end: item.end_minute });

/** Free study minutes on one day of the week. */
function freeOn(day: number, windows: WeeklyTime[], blocks: WeeklyTime[]): number {
  return freeMinutes(
    windows.filter((w) => w.day_of_week === day).map(toRange),
    blocks.filter((b) => b.day_of_week === day).map(toRange),
  );
}

function merge(ranges: Range[]): Range[] {
  const sorted = [...ranges].sort((a, b) => a.start - b.start);
  const merged: Range[] = [];
  for (const range of sorted) {
    const last = merged[merged.length - 1];
    if (last && range.start <= last.end) last.end = Math.max(last.end, range.end);
    else merged.push({ ...range });
  }
  return merged;
}

/** Minutes of study time left in a day once weekly busy times are taken out. */
export function freeMinutes(windows: Range[], busy: Range[]): number {
  const cuts = merge(busy);
  let total = 0;
  for (const window of merge(windows)) {
    let cursor = window.start;
    for (const cut of cuts) {
      if (cut.end <= cursor || cut.start >= window.end) continue;
      if (cut.start > cursor) total += cut.start - cursor;
      cursor = Math.max(cursor, cut.end);
    }
    if (cursor < window.end) total += window.end - cursor;
  }
  return total;
}

/** The hours worth drawing: everything in use, padded to whole hours, never less than 8 to 8. */
function visibleRange(items: Range[]): Range {
  const start = Math.min(8 * 60, ...items.map((item) => item.start));
  const end = Math.max(20 * 60, ...items.map((item) => item.end));
  return { start: Math.floor(start / 60) * 60, end: Math.ceil(end / 60) * 60 };
}

/**
 * The weekly template as a picture: when the student is free to study and which weekly
 * commitments cut into that. The free hours per day are written out, so nothing depends on the bars.
 */
export function WeekGlance({ windows, blocks }: { windows: WeeklyTime[]; blocks: RecurringBlock[] }) {
  const used = visibleRange([...windows, ...blocks].map(toRange));
  const step = 60 * (used.end - used.start > 14 * 60 ? 4 : 2);
  // Stretch the end so that the last label lands exactly on the right edge.
  const length = Math.ceil((used.end - used.start) / step) * step;
  const range =
    used.start + length <= 1440
      ? { start: used.start, end: used.start + length }
      : { start: Math.max(1440 - length, 0), end: 1440 };
  const span = range.end - range.start;
  const position = (item: Range) => ({
    left: `${((Math.max(item.start, range.start) - range.start) / span) * 100}%`,
    width: `${((Math.min(item.end, range.end) - Math.max(item.start, range.start)) / span) * 100}%`,
  });
  const ticks: number[] = [];
  for (let minute = range.start; minute <= range.end; minute += step) ticks.push(minute);
  const weekTotal = DAYS.reduce((total, _, day) => total + freeOn(day, windows, blocks), 0);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm">
          <span className="font-semibold tabular-nums">{formatDuration(weekTotal)}</span>{" "}
          <span className="text-ink-muted">free to study each week</span>
        </p>
        <div aria-hidden="true" className="flex items-center gap-4 text-xs text-ink-muted">
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm border border-brand/60 bg-brand-soft" />
            Study hours
          </span>
          <span className="flex items-center gap-1.5">
            <span className="busy-swatch size-2.5 rounded-sm border border-line" />
            Busy
          </span>
        </div>
      </div>

      <ul className="space-y-1.5">
        {DAYS.map((name, day) => {
          const own = windows.filter((w) => w.day_of_week === day);
          const busy = blocks.filter((b) => b.day_of_week === day);
          const free = freeOn(day, windows, blocks);
          return (
            <li key={name} className="grid grid-cols-[2.75rem_1fr_4.5rem] items-center gap-3 text-xs">
              <span className="font-medium text-ink-muted">{name.slice(0, 3)}</span>
              <div aria-hidden="true" className="relative h-7 overflow-hidden rounded-lg bg-raised">
                {own.map((window) => (
                  <span
                    key={`w-${window.start_minute}`}
                    className="absolute inset-y-0 border-x border-brand/50 bg-brand-soft"
                    style={position({ start: window.start_minute, end: window.end_minute })}
                  />
                ))}
                {busy.map((block) => (
                  <span
                    key={block.id}
                    title={`${block.title} (${categoryLabel(block.category)}), ${formatClock(block.start_minute)} to ${formatClock(block.end_minute)}`}
                    className="busy-swatch absolute inset-y-1 truncate rounded-md border border-line px-1.5 leading-5 text-[0.6875rem] text-ink-muted"
                    style={position({ start: block.start_minute, end: block.end_minute })}
                  >
                    {block.title}
                  </span>
                ))}
              </div>
              <span className="text-right tabular-nums">
                <span className="sr-only">{name}, free to study: </span>
                {free > 0 ? <span className="text-ink">{formatDuration(free)}</span> : <span className="text-ink-subtle">None</span>}
              </span>
            </li>
          );
        })}
      </ul>

      <div aria-hidden="true" className="mt-1.5 grid grid-cols-[2.75rem_1fr_4.5rem] gap-3 text-[0.6875rem] text-ink-subtle">
        <span />
        <div className="relative h-4">
          {ticks.map((minute) => (
            <span
              key={minute}
              className="absolute -translate-x-1/2 whitespace-nowrap tabular-nums first:translate-x-0 last:-translate-x-full"
              style={{ left: `${((minute - range.start) / span) * 100}%` }}
            >
              {formatClock(minute).replace(":00", "")}
            </span>
          ))}
        </div>
        <span />
      </div>
    </div>
  );
}
