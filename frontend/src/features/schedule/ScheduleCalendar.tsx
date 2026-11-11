import type {
  BusinessHoursInput,
  DateSelectArg,
  DatesSetArg,
  EventClickArg,
  EventContentArg,
  EventDropArg,
  EventInput,
} from "@fullcalendar/core";
import interactionPlugin, { type EventResizeDoneArg } from "@fullcalendar/interaction";
import luxonPlugin from "@fullcalendar/luxon3";
import dayGridPlugin from "@fullcalendar/daygrid";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import { Check, Flag, GraduationCap, Lock } from "lucide-react";
import { DateTime } from "luxon";
import { useMemo, useState } from "react";

import { ErrorAlert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import type { ApiError } from "../../lib/api";
import { formatTime, localInputToIso, minutesToTimeInput } from "../../lib/datetime";
import { categoryLabel, useWindows } from "../availability/api";
import { useBusyTimes, type BusyTime } from "../calendars/api";
import { useCourses, type Course } from "../courses/api";
import { EXAM_TYPES, labelFor, TASK_TYPES, useDeadlinesInRange, type Task } from "../tasks/api";
import {
  useMoveSession,
  useSessionsInRange,
  type Placement,
  type StudySession,
} from "./api";
import { movedTimes, resizedTimes } from "./calendarTimes";

const NO_COURSE_COLOR = "var(--color-ink-subtle)";
const NARROW_SCREEN = "(max-width: 639px)";

export interface RefusedMove {
  session: StudySession;
  start_at: string;
  end_at: string;
  placement: Placement;
}

interface Props {
  zone: string;
  onOpen: (session: StudySession) => void;
  onRefused: (move: RefusedMove) => void;
  onOpenBusy: (busy: BusyTime) => void;
  onSelectRange: (range: { start: string; end: string }) => void;
  onOpenTask: (task: Task) => void;
}

function statusClass(status: string): string {
  if (status === "completed") return "session-done";
  if (status === "missed") return "session-missed";
  if (status === "in_progress" || status === "paused") return "session-running";
  return "";
}

function canDrag(session: StudySession): boolean {
  return session.status === "planned" && !session.is_locked;
}

function toEvent(session: StudySession): EventInput {
  return {
    id: session.id,
    title: session.task_title,
    start: session.start_at,
    end: session.end_at,
    editable: canDrag(session),
    borderColor: session.course_color ?? NO_COURSE_COLOR,
    // A soft wash of the course color. Text stays in the ink color, so any course color reads.
    backgroundColor: `color-mix(in srgb, ${session.course_color ?? NO_COURSE_COLOR} 22%, var(--color-surface))`,
    classNames: ["session-event", statusClass(session.status)],
    extendedProps: { session },
  };
}

function busyEvent(busy: BusyTime): EventInput {
  return {
    id: `busy-${busy.id}-${busy.start_at}`,
    title: busy.title,
    start: busy.start_at,
    end: busy.end_at,
    editable: false,
    classNames: ["busy-event"],
    extendedProps: { busy },
  };
}

/**
 * A deadline sits in the row at the top of its local day, not in the time grid: it is a moment,
 * not a block of time, and a midterm at 2:30 PM should not look like a session at 2:30 PM.
 */
function deadlineEvent(task: Task, course: Course | undefined, zone: string): EventInput {
  const color = course?.color ?? NO_COURSE_COLOR;
  const exam = EXAM_TYPES.has(task.task_type);
  const done = task.status === "completed";
  return {
    id: `due-${task.id}`,
    title: task.title,
    start: DateTime.fromISO(task.deadline_at!, { zone }).toISODate()!,
    allDay: true,
    editable: false,
    borderColor: color,
    backgroundColor: `color-mix(in srgb, ${color} ${exam ? 30 : 14}%, var(--color-surface))`,
    classNames: ["deadline-event", exam ? "deadline-exam" : "", done ? "session-done" : ""],
    extendedProps: { task, exam },
  };
}

function EventBody(arg: EventContentArg & { zone: string }) {
  const { event, timeText, zone } = arg;
  const task = event.extendedProps.task as Task | undefined;
  if (task) {
    const Icon = event.extendedProps.exam ? GraduationCap : Flag;
    return (
      <div className="overflow-hidden px-1 py-0.5 leading-tight">
        <p className="flex items-center gap-1">
          <Icon aria-hidden="true" className="size-3 shrink-0" />
          <span className={`truncate font-medium ${task.status === "completed" ? "line-through" : ""}`}>{event.title}</span>
        </p>
        <p className="truncate text-[0.6875rem] text-ink-muted">
          {labelFor(TASK_TYPES, task.task_type)} · {formatTime(task.deadline_at!, zone)}
        </p>
      </div>
    );
  }
  const busy = event.extendedProps.busy as BusyTime | undefined;
  if (arg.view?.type === "dayGridMonth") {
    // One line per item in a month cell: a dot in the course color (or hatching for busy), time, title.
    return (
      <div className="flex w-full items-center gap-1.5 overflow-hidden px-1 text-[0.75rem] leading-5">
        <span
          aria-hidden="true"
          className={`inline-block size-2 shrink-0 rounded-full ${busy ? "busy-swatch border border-line" : ""}`}
          style={busy ? undefined : { backgroundColor: event.borderColor || NO_COURSE_COLOR }}
        />
        <span className="shrink-0 text-ink-muted tabular-nums">{timeText}</span>
        <span className={`truncate ${busy ? "text-ink-muted" : "font-medium"}`}>{event.title}</span>
      </div>
    );
  }
  if (busy) {
    return (
      <div className="overflow-hidden px-1 py-0.5 leading-tight">
        <p className="truncate font-medium">{event.title}</p>
        <p className="truncate text-[0.6875rem] text-ink-muted">
          {categoryLabel(busy.category)} · {timeText}
        </p>
      </div>
    );
  }
  const session = event.extendedProps.session as StudySession | undefined;
  if (!session) {
    // The preview FullCalendar draws while a range is being selected carries no data of ours.
    return <div className="px-1 py-0.5 text-[0.6875rem] leading-tight">{timeText}</div>;
  }
  return (
    <div className="overflow-hidden px-1 py-0.5 leading-tight">
      <p className="flex items-center gap-1 font-medium">
        {session.is_locked && <Lock aria-label="Locked" className="size-3 shrink-0" />}
        {session.status === "completed" && <Check aria-label="Completed" className="size-3 shrink-0" />}
        <span className="truncate">{event.title}</span>
      </p>
      <p className="truncate text-[0.6875rem] text-ink-muted">
        {session.status === "missed" ? `Missed · ${timeText}` : timeText}
      </p>
    </div>
  );
}

function isPlacementError(error: ApiError): boolean {
  return error.code === "session_conflict" || error.code === "placement_warnings";
}

export function ScheduleCalendar({ zone, onOpen, onRefused, onOpenBusy, onSelectRange, onOpenTask }: Props) {
  const [range, setRange] = useState<{ start: string; end: string } | null>(null);
  const sessions = useSessionsInRange(range);
  const busy = useBusyTimes(range);
  const deadlines = useDeadlinesInRange(range);
  // Includes archived courses, so that their tasks keep the right name and color.
  const courses = useCourses(true);
  const windows = useWindows();
  const move = useMoveSession();
  const [narrow] = useState(() => window.matchMedia?.(NARROW_SCREEN).matches ?? false);

  const events = useMemo(() => {
    const courseById = new Map((courses.data ?? []).map((course) => [course.id, course]));
    const due = (deadlines.data?.items ?? []).map((task) =>
      deadlineEvent(task, task.course_id ? courseById.get(task.course_id) : undefined, zone),
    );
    return [...due, ...(busy.data ?? []).map(busyEvent), ...(sessions.data ?? []).map(toEvent)];
  }, [busy.data, sessions.data, deadlines.data, courses.data, zone]);
  const businessHours = useMemo<BusinessHoursInput>(
    () =>
      (windows.data ?? []).map((window) => ({
        // Ours count from Monday as 0, FullCalendar's from Sunday as 0.
        daysOfWeek: [(window.day_of_week + 1) % 7],
        startTime: minutesToTimeInput(window.start_minute),
        endTime: window.end_minute === 1440 ? "24:00" : minutesToTimeInput(window.end_minute),
      })),
    [windows.data],
  );

  function save(session: StudySession, times: { start_at: string; end_at: string }, revert: () => void) {
    move.mutate(
      { id: session.id, ...times, acknowledge_warnings: false },
      {
        onError: (error) => {
          revert();
          if (isPlacementError(error)) {
            onRefused({ session, ...times, placement: error.details as Placement });
          }
        },
      },
    );
  }

  function handleDrop(info: EventDropArg) {
    const session = info.event.extendedProps.session as StudySession;
    save(session, movedTimes(info.event.startStr, session, zone), info.revert);
  }

  function handleResize(info: EventResizeDoneArg) {
    const session = info.event.extendedProps.session as StudySession;
    save(session, resizedTimes(info.event.endStr, session, zone), info.revert);
  }

  function handleSelect(info: DateSelectArg) {
    info.view.calendar.unselect();
    if (info.allDay) return; // The Due row holds deadlines, not busy time.
    // Read as wall-clock times, for the same reason as drops. See calendarTimes.ts.
    const start = localInputToIso(info.startStr.slice(0, 16), zone);
    const end = localInputToIso(info.endStr.slice(0, 16), zone);
    if (start && end && end > start) onSelectRange({ start, end });
  }

  function handleClick(info: EventClickArg) {
    const busyTime = info.event.extendedProps.busy as BusyTime | undefined;
    const task = info.event.extendedProps.task as Task | undefined;
    if (task) onOpenTask(task);
    else if (busyTime) onOpenBusy(busyTime);
    else onOpen(info.event.extendedProps.session as StudySession);
  }

  function handleDates(info: DatesSetArg) {
    setRange({ start: info.start.toISOString(), end: info.end.toISOString() });
  }

  const moveFailure = move.error && !isPlacementError(move.error) ? move.error : null;

  return (
    <div>
      {moveFailure && (
        <div className="mb-3">
          <ErrorAlert>{moveFailure.message}</ErrorAlert>
        </div>
      )}
      {busy.isError && (
        <div className="mb-3">
          <ErrorAlert>Your busy times could not be loaded, so they are not shown. {busy.error.message}</ErrorAlert>
        </div>
      )}
      {sessions.isError && (
        <div role="alert" className="mb-3 flex items-center justify-between gap-3 rounded-lg bg-danger-soft px-4 py-3 text-sm">
          <span>{sessions.error.message}</span>
          <Button variant="secondary" compact onClick={() => void sessions.refetch()}>
            Try again
          </Button>
        </div>
      )}
      <div
        aria-busy={sessions.isFetching}
        className={`card p-3 transition-opacity sm:p-4 ${sessions.isPlaceholderData ? "opacity-60" : ""}`}
      >
        <FullCalendar
          plugins={[timeGridPlugin, dayGridPlugin, interactionPlugin, luxonPlugin]}
          timeZone={zone}
          initialView={narrow ? "timeGridDay" : "timeGridWeek"}
          headerToolbar={{ left: "prev,next today", center: "title", right: "dayGridMonth,timeGridWeek,timeGridDay" }}
          buttonText={{ today: "Today", month: "Month", week: "Week", day: "Day" }}
          firstDay={1}
          allDayText="Due"
          views={{
            // The month grid has no times to drop onto, so sessions are moved in week or day view.
            dayGridMonth: { editable: false, selectable: false, dayMaxEvents: 4 },
          }}
          nowIndicator
          editable
          eventInteractive
          eventDurationEditable
          eventResizableFromStart={false}
          snapDuration="00:05:00"
          scrollTime="08:00:00"
          height={680}
          events={events}
          businessHours={businessHours}
          datesSet={handleDates}
          eventDrop={handleDrop}
          eventResize={handleResize}
          selectable
          selectMirror
          select={handleSelect}
          eventClick={handleClick}
          eventContent={(arg) => <EventBody {...arg} zone={zone} />}
        />
      </div>
      <p className="mt-2 text-xs text-ink-subtle">
        Deadlines and exams sit in the Due row at the top of their day; click one to edit the task.
        Drag a session to move it, or its lower edge to change its length. Drag across empty time to
        add a shift or plans. Striped blocks are times you are busy; shaded times are outside your
        study hours.
      </p>
    </div>
  );
}
