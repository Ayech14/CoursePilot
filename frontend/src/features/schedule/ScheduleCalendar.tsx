import type {
  BusinessHoursInput,
  DatesSetArg,
  EventClickArg,
  EventContentArg,
  EventDropArg,
  EventInput,
} from "@fullcalendar/core";
import interactionPlugin, { type EventResizeDoneArg } from "@fullcalendar/interaction";
import luxonPlugin from "@fullcalendar/luxon3";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import { Check, Lock } from "lucide-react";
import { useMemo, useState } from "react";

import { ErrorAlert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import type { ApiError } from "../../lib/api";
import { minutesToTimeInput } from "../../lib/datetime";
import { useWindows } from "../availability/api";
import {
  useMoveSession,
  useSessionsInRange,
  type Placement,
  type StudySession,
} from "./api";
import { movedTimes, resizedTimes } from "./calendarTimes";

const NO_COURSE_COLOR = "#7b8698";
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
    classNames: ["session-event", statusClass(session.status)],
    extendedProps: { session },
  };
}

function EventBody({ event, timeText }: EventContentArg) {
  const session = event.extendedProps.session as StudySession;
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

export function ScheduleCalendar({ zone, onOpen, onRefused }: Props) {
  const [range, setRange] = useState<{ start: string; end: string } | null>(null);
  const sessions = useSessionsInRange(range);
  const windows = useWindows();
  const move = useMoveSession();
  const [narrow] = useState(() => window.matchMedia?.(NARROW_SCREEN).matches ?? false);

  const events = useMemo(() => (sessions.data ?? []).map(toEvent), [sessions.data]);
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
        className={`rounded-xl border border-line bg-surface p-3 transition-opacity sm:p-4 ${sessions.isPlaceholderData ? "opacity-60" : ""}`}
      >
        <FullCalendar
          plugins={[timeGridPlugin, interactionPlugin, luxonPlugin]}
          timeZone={zone}
          initialView={narrow ? "timeGridDay" : "timeGridWeek"}
          headerToolbar={{ left: "prev,next today", center: "title", right: "timeGridWeek,timeGridDay" }}
          buttonText={{ today: "Today", week: "Week", day: "Day" }}
          firstDay={1}
          allDaySlot={false}
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
          eventClick={(info: EventClickArg) => onOpen(info.event.extendedProps.session as StudySession)}
          eventContent={(arg) => <EventBody {...arg} />}
        />
      </div>
      <p className="mt-2 text-xs text-ink-subtle">
        Drag a session to move it, or drag its lower edge to change its length. Shaded times are
        outside your weekly study hours. Select a session for more options.
      </p>
    </div>
  );
}
