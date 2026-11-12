import { DateTime } from "luxon";

import { formatDuration } from "../../lib/datetime";

const WEEKDAYS = ["M", "T", "W", "T", "F", "S", "S"];

// One hue, more study is stronger. Fixed steps mean a cell means the same thing every month.
export const LEVELS = [
  { below: 1, fill: "var(--color-raised)", label: "None" },
  { below: 30, fill: "color-mix(in srgb, var(--color-brand) 30%, var(--color-raised))", label: "Under 30m" },
  { below: 60, fill: "color-mix(in srgb, var(--color-brand) 55%, var(--color-raised))", label: "Under 1h" },
  { below: 120, fill: "color-mix(in srgb, var(--color-brand) 78%, var(--color-raised))", label: "Under 2h" },
  { below: Infinity, fill: "var(--color-brand)", label: "2h or more" },
];

export function fillFor(minutes: number): string {
  return LEVELS.find((level) => minutes < level.below)!.fill;
}

export function ConsistencyGrid({ days }: { days: { date: string; minutes: number }[] }) {
  const leadingBlanks = DateTime.fromISO(days[0]!.date).weekday - 1;
  return (
    <div>
      <div className="grid w-fit grid-cols-7 gap-1 text-center text-[0.6875rem] text-ink-subtle">
        {WEEKDAYS.map((day, index) => (
          <span key={index} aria-hidden="true">
            {day}
          </span>
        ))}
        {Array.from({ length: leadingBlanks }, (_, index) => (
          <span key={`blank-${index}`} />
        ))}
        {days.map((day) => {
          const text = `${DateTime.fromISO(day.date).toFormat("ccc, LLL d")}: ${
            day.minutes > 0 ? formatDuration(day.minutes) : "no study"
          }`;
          return (
            <span
              key={day.date}
              role="img"
              aria-label={text}
              title={text}
              className="size-6 rounded-sm"
              style={{ backgroundColor: fillFor(day.minutes) }}
            />
          );
        })}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[0.6875rem] text-ink-muted">
        {LEVELS.map((level) => (
          <li key={level.label} className="flex items-center gap-1">
            <span aria-hidden="true" className="size-2.5 rounded-sm" style={{ backgroundColor: level.fill }} />
            {level.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
