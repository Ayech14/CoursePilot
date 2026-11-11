import { ChartColumn } from "lucide-react";
import { DateTime } from "luxon";
import { useState } from "react";

import { Card, QuietNote, RankedBars, StatTile } from "../../components/ui/Figures";
import { EmptyState, PageHeader, QueryState } from "../../components/ui/States";
import { formatDuration, formatShortDate } from "../../lib/datetime";
import { useAnalytics, type Analytics } from "./api";
import { ColumnChart } from "./ColumnChart";
import { ConsistencyGrid } from "./ConsistencyGrid";

const RANGES = [
  { weeks: 4, label: "4 weeks" },
  { weeks: 12, label: "12 weeks" },
  { weeks: 26, label: "26 weeks" },
];

function hours(minutes: number): number {
  return Math.round((minutes / 60) * 10) / 10;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function isEmpty(data: Analytics): boolean {
  return (
    data.weekly_minutes.every((week) => week.minutes === 0) &&
    data.completions.every((week) => week.count === 0) &&
    data.workload.length === 0 &&
    data.upcoming.every((day) => day.planned_minutes === 0 && day.deadlines === 0) &&
    data.consistency.sessions_missed === 0
  );
}

function Estimates({ data }: { data: Analytics["estimates"] }) {
  if (data.tasks_compared === 0) {
    return <QuietNote>Finish a task you timed to compare it with your estimate.</QuietNote>;
  }
  const ratio = Math.round((data.actual_minutes / data.estimated_minutes) * 100);
  const largest = Math.max(...data.recent.flatMap((t) => [t.estimated_minutes, t.actual_minutes]), 1);
  return (
    <>
      <p className="text-sm">
        Across {plural(data.tasks_compared, "task")} you estimated{" "}
        <span className="font-semibold">{formatDuration(data.estimated_minutes)}</span> and took{" "}
        <span className="font-semibold">{formatDuration(data.actual_minutes)}</span>, or {ratio}% of the estimate.
      </p>
      <ul className="mt-3 flex gap-4 text-xs text-ink-muted" aria-hidden="true">
        <li className="flex items-center gap-1.5">
          <span className="h-2 w-3 rounded-sm bg-chart-neutral" /> Estimated
        </li>
        <li className="flex items-center gap-1.5">
          <span className="h-2 w-3 rounded-sm bg-brand" /> Actual
        </li>
      </ul>
      <ul aria-label="Estimated and actual time by task" className="mt-3 space-y-3">
        {data.recent.map((task) => (
          <li key={task.task_id} className="text-sm">
            <div className="mb-1 flex items-baseline justify-between gap-3">
              <span className="min-w-0 truncate">{task.title}</span>
              <span className="shrink-0 text-xs text-ink-muted tabular-nums">
                {formatDuration(task.estimated_minutes)} estimated, {formatDuration(task.actual_minutes)} actual
              </span>
            </div>
            <div className="space-y-0.5">
              <div className="h-1.5 rounded-full bg-chart-neutral" style={{ width: `${(task.estimated_minutes / largest) * 100}%` }} />
              <div className="h-1.5 rounded-full bg-brand" style={{ width: `${(task.actual_minutes / largest) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

function Charts({ data }: { data: Analytics }) {
  const { consistency } = data;
  const finishedOrMissed = consistency.sessions_completed + consistency.sessions_missed;
  const attended =
    finishedOrMissed === 0 ? "None yet" : `${Math.round((consistency.sessions_completed / finishedOrMissed) * 100)}%`;
  const studied = data.weekly_minutes.reduce((total, week) => total + week.minutes, 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Studied in this range" value={formatDuration(studied)} note="Timed sessions" />
        <StatTile label="Current streak" value={plural(consistency.current_streak, "day")} />
        <StatTile label="Days studied" value={`${consistency.active_days} of 28`} note="Last 28 days" />
        <StatTile
          label="Sessions attended"
          value={attended}
          note={`${consistency.sessions_completed} completed, ${consistency.sessions_missed} missed`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Weekly study hours" subtitle="Timed sessions, by the week they happened">
          {studied === 0 ? (
            <QuietNote>Time a study session to see your weekly hours.</QuietNote>
          ) : (
            <ColumnChart
              label="Hours studied each week"
              valueHeading="Studied"
              data={data.weekly_minutes.map((week) => ({
                key: week.week_start,
                label: formatShortDate(week.week_start),
                value: hours(week.minutes),
                display: formatDuration(week.minutes),
              }))}
            />
          )}
        </Card>

        <Card title="Hours per course">
          {data.minutes_per_course.length === 0 ? (
            <QuietNote>No timed sessions in this range.</QuietNote>
          ) : (
            <RankedBars
              label="Hours studied per course"
              rows={data.minutes_per_course.map((course) => ({
                key: course.course_id ?? "none",
                label: course.name,
                color: course.color,
                value: course.minutes,
                display: formatDuration(course.minutes),
              }))}
            />
          )}
        </Card>

        <Card title="Tasks completed" subtitle="By the week they were finished">
          {data.completions.every((week) => week.count === 0) ? (
            <QuietNote>No tasks completed in this range.</QuietNote>
          ) : (
            <ColumnChart
              label="Tasks completed each week"
              valueHeading="Completed"
              data={data.completions.map((week) => ({
                key: week.week_start,
                label: formatShortDate(week.week_start),
                value: week.count,
                display: plural(week.count, "task"),
              }))}
            />
          )}
        </Card>

        <Card title="Workload distribution" subtitle="Work still to do, by course">
          {data.workload.length === 0 ? (
            <QuietNote>No work remaining.</QuietNote>
          ) : (
            <RankedBars
              label="Work remaining by course"
              rows={[...data.workload]
                .sort((a, b) => b.remaining_minutes - a.remaining_minutes)
                .map((course) => ({
                  key: course.course_id ?? "none",
                  label: course.name,
                  color: course.color,
                  value: course.remaining_minutes,
                  display: `${formatDuration(course.remaining_minutes)}, ${plural(course.open_tasks, "task")}`,
                }))}
            />
          )}
        </Card>

        <Card title="Upcoming workload" subtitle="Scheduled study over the next 14 days">
          {data.upcoming.every((day) => day.planned_minutes === 0) ? (
            <QuietNote>Nothing is scheduled in the next 14 days.</QuietNote>
          ) : (
            <ColumnChart
              label="Hours scheduled each day for the next 14 days"
              valueHeading="Scheduled"
              data={data.upcoming.map((day) => ({
                key: day.date,
                label: DateTime.fromISO(day.date).toFormat("LLL d"),
                value: hours(day.planned_minutes),
                display: formatDuration(day.planned_minutes),
                detail: day.deadlines > 0 ? plural(day.deadlines, "deadline") : undefined,
              }))}
            />
          )}
        </Card>

        <Card title="Consistency" subtitle="Time studied each day, last 28 days">
          <ConsistencyGrid days={consistency.days} />
        </Card>

        <div className="lg:col-span-2">
          <Card title="Estimated vs actual time" subtitle="Completed tasks in this range, most recent first">
            <Estimates data={data.estimates} />
          </Card>
        </div>
      </div>
    </div>
  );
}

export function AnalyticsPage() {
  const [weeks, setWeeks] = useState(12);
  const analytics = useAnalytics(weeks);

  return (
    <>
      <PageHeader
        title="Analytics"
        subtitle="Built only from the sessions you timed and the tasks you entered."
        action={
          <label className="flex items-center gap-2 text-sm text-ink-muted">
            Range
            <select
              value={weeks}
              onChange={(event) => setWeeks(Number(event.target.value))}
              className="h-9 rounded-lg border border-line bg-surface px-2 text-sm text-ink"
            >
              {RANGES.map((range) => (
                <option key={range.weeks} value={range.weeks}>
                  {range.label}
                </option>
              ))}
            </select>
          </label>
        }
      />
      <QueryState query={analytics}>
        {(data) =>
          isEmpty(data) ? (
            <EmptyState
              icon={ChartColumn}
              title="No data to chart yet"
              message="Plan some work and time a study session. Your charts will build from what you actually do."
            />
          ) : (
            <div className={`transition-opacity ${analytics.isPlaceholderData ? "opacity-60" : ""}`}>
              <Charts data={data} />
            </div>
          )
        }
      </QueryState>
    </>
  );
}
