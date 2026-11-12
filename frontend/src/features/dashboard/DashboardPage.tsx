import { CalendarClock, ListChecks, Sparkles, Timer, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CourseDot, DueBadge, ProgressRing, QuietNote, RankedBars, StatTile } from "../../components/ui/Figures";
import { EmptyState, QueryState } from "../../components/ui/States";
import { formatDateTime, formatDuration, formatTime, minutesBetween } from "../../lib/datetime";
import { useAuth } from "../auth/AuthContext";
import type { StudySession } from "../schedule/api";
import { StartSessionButton } from "../timer/StartSessionButton";
import { StartTimerButton } from "../timer/StartTimerButton";
import {
  useDashboard,
  type AttentionItem,
  type Dashboard,
  type DeadlineItem,
} from "./api";
import { MonthOverview } from "./MonthOverview";
import { RecentActivityCard, TodayProgressCard } from "./Progress";

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
  const faded = session.status === "completed" || session.status === "missed";
  return (
    <li className={`flex items-center gap-3 py-2.5 text-sm ${faded ? "text-ink-muted" : ""}`}>
      <span className="w-16 shrink-0 text-xs font-medium text-ink-muted tabular-nums">
        {formatTime(session.start_at, zone)}
      </span>
      <span
        aria-hidden="true"
        className="w-1 self-stretch rounded-full"
        style={{ backgroundColor: session.course_color ?? "var(--color-ink-subtle)" }}
      />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium">{session.task_title}</span>
        <span className="block text-xs text-ink-muted tabular-nums">
          Until {formatTime(session.end_at, zone)}
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
            <span className="block truncate font-medium">{item.title}</span>
            <span className="block text-xs text-ink-muted">
              {item.course_name ? `${item.course_name} · ` : ""}
              {formatDuration(item.remaining_minutes)} left
            </span>
          </span>
          <DueBadge iso={item.deadline_at} zone={zone} />
        </li>
      ))}
    </ul>
  );
}

function nextDeadline(data: Dashboard): DeadlineItem | null {
  const all = [...data.upcoming_assignments, ...data.upcoming_exams];
  all.sort((a, b) => a.deadline_at.localeCompare(b.deadline_at));
  return all[0] ?? null;
}

/** How much of this week's study is behind the student: timed so far against timed plus still planned. */
function WeekRing({ data }: { data: Dashboard }) {
  const { studied_minutes: studied, planned_minutes: planned } = data.week;
  const total = studied + planned;
  const percent = total === 0 ? 0 : Math.round((studied / total) * 100);
  return (
    <div className="flex items-center gap-4">
      <ProgressRing
        value={studied}
        total={total}
        label={total === 0 ? "No study planned or timed this week" : `${percent}% of this week's study done`}
      >
        <span>
          <span className="block text-lg font-semibold tabular-nums">{total === 0 ? "–" : `${percent}%`}</span>
        </span>
      </ProgressRing>
      <div className="text-sm">
        <p className="font-medium">This week</p>
        <p className="mt-0.5 max-w-40 text-xs text-ink-muted">
          {total === 0
            ? "Nothing planned yet."
            : `${formatDuration(studied)} studied, ${formatDuration(planned)} still planned`}
        </p>
      </div>
    </div>
  );
}

function NextDeadline({ item, zone }: { item: DeadlineItem; zone: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface/70 p-4 backdrop-blur-sm sm:w-64">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-ink-subtle">Next deadline</p>
        <DueBadge iso={item.deadline_at} zone={zone} />
      </div>
      <p className="mt-2 truncate font-semibold">{item.title}</p>
      <p className="mt-0.5 truncate text-xs text-ink-muted">
        {item.course_name ? `${item.course_name} · ` : ""}
        {formatDateTime(item.deadline_at, zone)}
      </p>
    </div>
  );
}

/** One sentence about today, built only from the student's own sessions. */
function todayLine(data: Dashboard, zone: string): string | null {
  if (data.today.length === 0) return null;
  const left = data.today.filter((s) => s.status === "planned" || s.status === "in_progress" || s.status === "paused");
  const planned = left.reduce((total, s) => total + minutesBetween(s.start_at, s.end_at), 0);
  if (left.length === 0) return "Every session for today is behind you. Nice work.";
  const next = left[0]!;
  const count = left.length === 1 ? "1 session" : `${left.length} sessions`;
  return `${count} left today, ${formatDuration(planned)} in all. Next: ${next.task_title} at ${formatTime(next.start_at, zone)}.`;
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
        <StatTile
          icon={Timer}
          label="Studied this week"
          value={formatDuration(data.week.studied_minutes)}
          note="Timed sessions"
        />
        <StatTile icon={CalendarClock} label="Still planned this week" value={formatDuration(data.week.planned_minutes)} />
        <StatTile icon={ListChecks} label="Tasks remaining" value={String(data.tasks.remaining)} />
        <StatTile
          icon={TriangleAlert}
          tone={data.tasks.overdue > 0 ? "danger" : "brand"}
          label="Overdue"
          value={String(data.tasks.overdue)}
          note={data.tasks.overdue > 0 ? "See the list below" : undefined}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4">
          <TodayProgressCard progress={data.progress} />
          <RecentActivityCard items={data.recent} zone={zone} />
        </div>
        <div className="lg:col-span-2">
          <MonthOverview zone={zone} />
        </div>
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

  const line = dashboard.data ? todayLine(dashboard.data, user.timezone) : null;
  const next = dashboard.data ? nextDeadline(dashboard.data) : null;

  return (
    <>
      <section className="relative mb-6 overflow-hidden rounded-2xl border border-line bg-surface px-6 py-7 shadow-[var(--shadow-card)] sm:px-8">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,var(--color-brand-soft),transparent_60%),radial-gradient(ellipse_at_bottom_left,var(--color-accent-soft),transparent_55%)] opacity-80"
        />
        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <p className="text-sm font-medium text-brand">
              {today} · {user.timezone}
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
              {greetingFor(user.timezone, now)}, {user.display_name}
            </h1>
            {line && <p className="mt-2 max-w-xl text-sm text-ink-muted">{line}</p>}
            {dashboard.data && hasAnything(dashboard.data) && (
              <div className="mt-4">
                <StartTimerButton variant="primary" />
              </div>
            )}
          </div>
          {dashboard.data && hasAnything(dashboard.data) && (
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
              <WeekRing data={dashboard.data} />
              {next && <NextDeadline item={next} zone={user.timezone} />}
            </div>
          )}
        </div>
      </section>
      <QueryState query={dashboard}>
        {(data) => (hasAnything(data) ? <Summary data={data} zone={user.timezone} /> : <FirstRun />)}
      </QueryState>
    </>
  );
}
