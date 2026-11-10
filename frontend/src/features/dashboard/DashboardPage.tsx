import { Sparkles, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CourseDot, QuietNote, RankedBars, StatTile } from "../../components/ui/Figures";
import { EmptyState, QueryState } from "../../components/ui/States";
import { formatDateTime, formatDuration, formatTime } from "../../lib/datetime";
import { useAuth } from "../auth/AuthContext";
import type { StudySession } from "../schedule/api";
import { StartSessionButton } from "../timer/StartSessionButton";
import {
  useDashboard,
  type AttentionItem,
  type Dashboard,
  type DeadlineItem,
} from "./api";

function greetingFor(timezone: string, now: Date): string {
  const hour = Number(
    new Intl.DateTimeFormat("en-US", { hour: "numeric", hourCycle: "h23", timeZone: timezone }).format(now),
  );
  if (hour < 5) return "Good evening";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function TodayRow({ session, zone }: { session: StudySession; zone: string }) {
  const note: Record<string, string> = {
    completed: `Completed, ${formatDuration(session.actual_minutes)} studied`,
    missed: "Missed",
    in_progress: "Running now",
    paused: "Paused",
  };
  return (
    <li className="flex items-center gap-3 py-2.5 text-sm">
      <span className="mt-0.5 self-start pt-1">
        <CourseDot color={session.course_color} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-medium">{session.task_title}</span>
        <span className="block text-xs text-ink-muted tabular-nums">
          {formatTime(session.start_at, zone)} to {formatTime(session.end_at, zone)}
          {note[session.status] ? `, ${note[session.status]!.toLowerCase()}` : ""}
        </span>
      </span>
      <StartSessionButton session={session} zone={zone} compact />
    </li>
  );
}

function attentionText(item: AttentionItem, zone: string): string {
  const due = formatDateTime(item.deadline_at, zone);
  if (item.reason === "overdue") return `Overdue since ${due}`;
  if (item.reason === "not_fully_planned") {
    return `${formatDuration(item.unplanned_minutes)} not yet scheduled, due ${due}`;
  }
  return `Due ${due}`;
}

function AttentionList({ data, zone }: { data: Dashboard; zone: string }) {
  if (data.attention.length === 0) return <QuietNote>Nothing needs attention right now.</QuietNote>;
  return (
    <>
      <ul className="divide-y divide-line">
        {data.attention.map((item) => (
          <li key={item.task_id} className="flex items-start gap-3 py-2.5 text-sm">
            {item.reason === "overdue" ? (
              <TriangleAlert aria-label="Overdue" className="mt-0.5 size-4 shrink-0 text-danger" />
            ) : (
              <span className="mt-1.5">
                <CourseDot color={item.course_color} />
              </span>
            )}
            <span className="min-w-0">
              <span className="block font-medium">{item.title}</span>
              <span className="block text-xs text-ink-muted">{attentionText(item, zone)}</span>
            </span>
          </li>
        ))}
      </ul>
      {data.attention_total > data.attention.length && (
        <p className="mt-2 text-xs text-ink-subtle">
          And {data.attention_total - data.attention.length} more.{" "}
          <Link to="/tasks" className="font-medium text-brand hover:underline">
            See all tasks
          </Link>
        </p>
      )}
    </>
  );
}

function Deadlines({ items, zone, empty }: { items: DeadlineItem[]; zone: string; empty: string }) {
  if (items.length === 0) return <QuietNote>{empty}</QuietNote>;
  return (
    <ul className="divide-y divide-line">
      {items.map((item) => (
        <li key={item.task_id} className="flex items-start gap-3 py-2.5 text-sm">
          <span className="mt-1.5">
            <CourseDot color={item.course_color} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block font-medium">{item.title}</span>
            <span className="block text-xs text-ink-muted">
              {item.course_name ? `${item.course_name}, ` : ""}
              {formatDateTime(item.deadline_at, zone)}
            </span>
          </span>
          <span className="shrink-0 text-xs text-ink-subtle">
            {formatDuration(item.remaining_minutes)} left
          </span>
        </li>
      ))}
    </ul>
  );
}

function hasAnything(data: Dashboard): boolean {
  return data.workload.length > 0 || data.today.length > 0;
}

function FirstRun() {
  return (
    <EmptyState
      icon={Sparkles}
      title="Nothing to show yet"
      message="Add your courses, tasks and weekly hours, and this page will summarize deadlines, today's plan and your workload."
      action={
        <div className="flex flex-wrap justify-center gap-4 text-sm font-medium text-brand">
          <Link to="/courses" className="hover:underline">
            Add courses
          </Link>
          <Link to="/tasks" className="hover:underline">
            Add tasks
          </Link>
          <Link to="/availability" className="hover:underline">
            Set availability
          </Link>
        </div>
      }
    />
  );
}

function Summary({ data, zone }: { data: Dashboard; zone: string }) {
  const totalTasks = data.tasks.completed + data.tasks.remaining;
  const percentDone = totalTasks === 0 ? 0 : (data.tasks.completed / totalTasks) * 100;
  const loads = data.workload.filter((course) => course.remaining_minutes > 0);
  const load = [...loads].sort((a, b) => b.remaining_minutes - a.remaining_minutes);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Studied this week" value={formatDuration(data.week.studied_minutes)} note="Timed sessions" />
        <StatTile label="Still planned this week" value={formatDuration(data.week.planned_minutes)} />
        <StatTile label="Tasks remaining" value={String(data.tasks.remaining)} />
        <StatTile
          label="Overdue"
          value={String(data.tasks.overdue)}
          note={data.tasks.overdue > 0 ? "See the list below" : undefined}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Today">
          {data.today.length === 0 ? (
            <QuietNote>
              No sessions today.{" "}
              <Link to="/schedule" className="font-medium text-brand hover:underline">
                Open your schedule
              </Link>
            </QuietNote>
          ) : (
            <ul className="divide-y divide-line">
              {data.today.map((session) => (
                <TodayRow key={session.id} session={session} zone={zone} />
              ))}
            </ul>
          )}
        </Card>
        <Card title="Needs attention">
          <AttentionList data={data} zone={zone} />
        </Card>
        <Card title="Upcoming assignments">
          <Deadlines items={data.upcoming_assignments} zone={zone} empty="No assignments coming up." />
        </Card>
        <Card title="Upcoming exams">
          <Deadlines items={data.upcoming_exams} zone={zone} empty="No exams coming up." />
        </Card>
        <Card title="Task progress">
          <p className="text-sm">
            <span className="font-semibold">{data.tasks.completed}</span> of {totalTasks} tasks completed
          </p>
          <div className="mt-2 h-2 rounded-full bg-raised">
            <div className="h-2 rounded-full bg-brand" style={{ width: `${percentDone}%` }} />
          </div>
          <h3 className="mt-5 mb-2 text-xs font-medium text-ink-subtle">Current courses</h3>
          <ul className="space-y-1.5 text-sm">
            {data.workload
              .filter((course) => course.course_id !== null)
              .map((course) => (
                <li key={course.course_id} className="flex items-center gap-2">
                  <CourseDot color={course.color} />
                  <Link to={`/courses/${course.course_id}`} className="min-w-0 flex-1 truncate hover:underline">
                    {course.name}
                  </Link>
                  <span className="shrink-0 text-xs text-ink-subtle">{course.open_tasks} open</span>
                </li>
              ))}
          </ul>
        </Card>
        <Card title="Workload by course" subtitle="Work still to do">
          {load.length === 0 ? (
            <QuietNote>No work remaining.</QuietNote>
          ) : (
            <RankedBars
              label="Work remaining by course"
              rows={load.map((course) => ({
                key: course.course_id ?? "none",
                label: course.name,
                color: course.color,
                value: course.remaining_minutes,
                display: formatDuration(course.remaining_minutes),
              }))}
            />
          )}
        </Card>
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { user } = useAuth();
  const dashboard = useDashboard();
  if (!user) return null;

  const now = new Date();
  const today = new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: user.timezone,
  }).format(now);

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">
        {greetingFor(user.timezone, now)}, {user.display_name}
      </h1>
      <p className="mt-1 mb-8 text-sm text-ink-muted">
        {today} · {user.timezone}
      </p>
      <QueryState query={dashboard}>
        {(data) => (hasAnything(data) ? <Summary data={data} zone={user.timezone} /> : <FirstRun />)}
      </QueryState>
    </>
  );
}
