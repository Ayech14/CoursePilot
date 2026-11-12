import { ChevronLeft, ChevronRight, CircleCheck, Flag, GraduationCap } from "lucide-react";
import { DateTime } from "luxon";
import { useState } from "react";

import { Card, CourseDot, QuietNote } from "../../components/ui/Figures";
import { formatDuration, formatTime } from "../../lib/datetime";
import { fillFor, LEVELS } from "../analytics/ConsistencyGrid";
import { labelFor, TASK_TYPES } from "../tasks/api";
import { useMonth, type MonthDay } from "./api";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const EXAMS = new Set(["midterm", "final_exam", "quiz"]);

function dayLabel(day: MonthDay): string {
  const parts = [DateTime.fromISO(day.date).toFormat("cccc, LLLL d")];
  parts.push(day.studied_minutes > 0 ? `${formatDuration(day.studied_minutes)} studied` : "no study");
  if (day.deadlines.length > 0) {
    parts.push(day.deadlines.length === 1 ? "1 deadline" : `${day.deadlines.length} deadlines`);
  }
  return parts.join(", ");
}

/**
 * A month at a glance: each day shaded by time studied (the same steps as Analytics, so a shade
 * always means the same amount), with a mark on days that have a deadline. Picking a day shows
 * what was studied, finished and due.
 */
export function MonthOverview({ zone }: { zone: string }) {
  const today = DateTime.now().setZone(zone).toISODate()!;
  const [month, setMonth] = useState(today.slice(0, 7));
  const [selected, setSelected] = useState(today);
  const query = useMonth(month);

  const first = DateTime.fromISO(`${month}-01`);
  function go(offset: number) {
    const next = first.plus({ months: offset });
    const key = next.toFormat("yyyy-LL");
    setMonth(key);
    setSelected(key === today.slice(0, 7) ? today : next.toISODate()!);
  }

  const days = query.data?.days ?? [];
  const chosen = days.find((day) => day.date === selected) ?? null;
  const leading = first.weekday - 1;
  const total = days.reduce((sum, day) => sum + day.studied_minutes, 0);

  return (
    <Card
      title="Monthly overview"
      subtitle={query.data ? `${formatDuration(total)} studied in ${first.toFormat("LLLL")}` : undefined}
      action={
        <div className="flex items-center gap-1">
          {month !== today.slice(0, 7) && (
            <button
              type="button"
              onClick={() => {
                setMonth(today.slice(0, 7));
                setSelected(today);
              }}
              className="rounded-lg px-2 py-1 text-xs font-medium text-ink-muted hover:bg-raised hover:text-ink"
            >
              Today
            </button>
          )}
          <MonthButton label="Previous month" onClick={() => go(-1)} icon={ChevronLeft} />
          <span className="min-w-28 text-center text-sm font-medium" aria-live="polite">
            {first.toFormat("LLLL yyyy")}
          </span>
          <MonthButton label="Next month" onClick={() => go(1)} icon={ChevronRight} />
        </div>
      }
    >
      {query.isError ? (
        <QuietNote>We couldn't load this month. Try again in a moment.</QuietNote>
      ) : (
        <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_15rem]">
          <div>
            <div className="grid grid-cols-7 gap-1.5 text-center">
              {WEEKDAYS.map((name) => (
                <span key={name} aria-hidden="true" className="pb-1 text-[0.6875rem] font-medium text-ink-subtle">
                  {name}
                </span>
              ))}
              {Array.from({ length: leading }, (_, index) => (
                <span key={`blank-${index}`} />
              ))}
              {days.map((day) => (
                <DayCell
                  key={day.date}
                  day={day}
                  isToday={day.date === today}
                  isSelected={day.date === selected}
                  onSelect={() => setSelected(day.date)}
                />
              ))}
            </div>
            <div aria-hidden="true" className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.6875rem] text-ink-muted">
              <span className="flex items-center gap-1">
                Less
                {LEVELS.map((level) => (
                  <span key={level.label} title={level.label} className="size-2.5 rounded-sm" style={{ backgroundColor: level.fill }} />
                ))}
                More
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-accent" />
                Deadline
              </span>
            </div>
          </div>
          {chosen && <DayDetails day={chosen} zone={zone} />}
        </div>
      )}
    </Card>
  );
}

function MonthButton({ label, onClick, icon: Icon }: { label: string; onClick: () => void; icon: typeof ChevronLeft }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="flex size-7 items-center justify-center rounded-lg text-ink-muted hover:bg-raised hover:text-ink"
    >
      <Icon aria-hidden="true" className="size-4" />
    </button>
  );
}

function DayCell({
  day,
  isToday,
  isSelected,
  onSelect,
}: {
  day: MonthDay;
  isToday: boolean;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const open = day.deadlines.some((deadline) => !deadline.completed);
  return (
    <button
      type="button"
      aria-label={dayLabel(day)}
      aria-pressed={isSelected}
      aria-current={isToday ? "date" : undefined}
      onClick={onSelect}
      className={`relative flex aspect-square min-h-9 items-center justify-center rounded-lg outline-offset-2 transition-shadow ${
        isSelected ? "ring-2 ring-ink" : isToday ? "ring-2 ring-brand" : "hover:ring-1 hover:ring-line"
      }`}
      style={{ backgroundColor: fillFor(day.studied_minutes) }}
    >
      {/* The number sits on its own chip so it reads clearly on every shade, in both themes. */}
      <span
        aria-hidden="true"
        className={`grid size-6 place-items-center rounded-full bg-surface/90 text-xs tabular-nums ${
          isToday ? "font-semibold text-brand" : "text-ink"
        }`}
      >
        {Number(day.date.slice(8))}
      </span>
      {day.deadlines.length > 0 && (
        <span
          aria-hidden="true"
          className={`absolute top-1 right-1 size-2 rounded-full border border-surface ${open ? "bg-accent" : "bg-ink-subtle"}`}
        />
      )}
    </button>
  );
}

function DayDetails({ day, zone }: { day: MonthDay; zone: string }) {
  const empty = day.studied.length === 0 && day.completed.length === 0 && day.deadlines.length === 0;
  return (
    <section aria-label="Selected day" className="rounded-xl border border-line bg-raised/40 p-4">
      <p className="text-[0.6875rem] font-medium tracking-wide text-ink-subtle uppercase">Selected day</p>
      <h3 className="mt-0.5 font-semibold">{DateTime.fromISO(day.date).toFormat("cccc, LLL d")}</h3>
      <p className="mt-2 text-sm">
        <span className="font-semibold tabular-nums">{formatDuration(day.studied_minutes)}</span>{" "}
        <span className="text-ink-muted">studied</span>
      </p>
      {empty ? (
        <p className="mt-3 text-xs text-ink-subtle">Nothing studied, finished or due on this day.</p>
      ) : (
        <div className="mt-3 space-y-3 text-sm">
          {day.studied.length > 0 && (
            <ul aria-label="Studied" className="space-y-1.5">
              {day.studied.map((item) => (
                <li key={item.task_id} className="flex items-center gap-2">
                  <CourseDot color={item.course_color} />
                  <span className="min-w-0 flex-1 truncate">{item.title}</span>
                  <span className="shrink-0 text-xs text-ink-muted tabular-nums">{formatDuration(item.minutes)}</span>
                </li>
              ))}
            </ul>
          )}
          {day.completed.length > 0 && (
            <ul aria-label="Finished" className="space-y-1.5">
              {day.completed.map((item) => (
                <li key={item.task_id} className="flex items-center gap-2 text-ink-muted">
                  <CircleCheck aria-hidden="true" className="size-3.5 shrink-0 text-brand" />
                  <span className="min-w-0 flex-1 truncate">
                    <span className="sr-only">Finished: </span>
                    {item.title}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {day.deadlines.length > 0 && (
            <ul aria-label="Due" className="space-y-1.5">
              {day.deadlines.map((item) => {
                const Icon = EXAMS.has(item.task_type) ? GraduationCap : Flag;
                return (
                  <li key={item.task_id} className="flex items-start gap-2">
                    <Icon aria-hidden="true" className={`mt-0.5 size-3.5 shrink-0 ${item.completed ? "text-ink-subtle" : "text-accent"}`} />
                    <span className="min-w-0 flex-1">
                      <span className={`block truncate ${item.completed ? "text-ink-muted line-through" : ""}`}>{item.title}</span>
                      <span className="block text-xs text-ink-subtle">
                        {labelFor(TASK_TYPES, item.task_type)} · due {formatTime(item.deadline_at, zone)}
                        {item.completed ? " · done" : ""}
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
