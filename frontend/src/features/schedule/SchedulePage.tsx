import { CalendarDays, Lock, LockOpen } from "lucide-react";
import { lazy, Suspense, useState } from "react";
import { Link } from "react-router-dom";

import { ErrorAlert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/Modal";
import { EmptyState, LoadingBlock, PageHeader, QueryState } from "../../components/ui/States";
import {
  formatDuration,
  formatTime,
  groupByLocalDay,
  minutesBetween,
} from "../../lib/datetime";
import { useAuth } from "../auth/AuthContext";
import { StartSessionButton } from "../timer/StartSessionButton";
import {
  useApplyProposal,
  useCurrentProposal,
  useDeleteSession,
  usePreview,
  useRejectProposal,
  useScheduleStatus,
  useSessions,
  useSetLocked,
  type ScheduleStatus,
  type StudySession,
} from "./api";
import { EditSessionDialog } from "./EditSessionDialog";
import { ProposalReview } from "./ProposalReview";
import type { RefusedMove } from "./ScheduleCalendar";
import { SessionDetails } from "./SessionDetails";

// FullCalendar is large, so it loads only when the calendar is shown.
const ScheduleCalendar = lazy(() =>
  import("./ScheduleCalendar").then((module) => ({ default: module.ScheduleCalendar })),
);

type View = "calendar" | "list";
const VIEW_STORAGE_KEY = "coursepilot.schedule.view";

function storedView(): View {
  return localStorage.getItem(VIEW_STORAGE_KEY) === "list" ? "list" : "calendar";
}

interface RowProps {
  session: StudySession;
  zone: string;
  onEdit: () => void;
  onRemove: () => void;
}

function SessionRow({ session, zone, onEdit, onRemove }: RowProps) {
  const setLocked = useSetLocked();
  const editable = session.status === "planned";
  const LockIcon = session.is_locked ? Lock : LockOpen;
  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span className="w-40 shrink-0 text-ink-muted tabular-nums">
          {formatTime(session.start_at, zone)} to {formatTime(session.end_at, zone)}
        </span>
        {session.course_color && (
          <span
            aria-hidden="true"
            className="size-2 rounded-full"
            style={{ backgroundColor: session.course_color }}
          />
        )}
        <span className="min-w-0 font-medium">{session.task_title}</span>
        <span className="text-xs text-ink-subtle">
          {formatDuration(minutesBetween(session.start_at, session.end_at))}
        </span>
        {session.is_locked && <span className="text-xs font-medium text-brand">Locked</span>}
        {session.is_user_modified && !session.is_locked && (
          <span className="text-xs text-ink-subtle">Edited by you</span>
        )}
        {session.status === "completed" && (
          <span className="text-xs text-ink-subtle">
            Completed, {formatDuration(session.actual_minutes)} studied
          </span>
        )}
        {session.status === "missed" && <span className="text-xs text-danger">Missed</span>}
        {editable && (
          <span className="ml-auto flex gap-1">
            <StartSessionButton session={session} zone={zone} compact />
            <Button
              variant="ghost"
              compact
              loading={setLocked.isPending}
              aria-label={`${session.is_locked ? "Unlock" : "Lock"} ${session.task_title} at ${formatTime(session.start_at, zone)}`}
              aria-pressed={session.is_locked}
              onClick={() => setLocked.mutate({ id: session.id, locked: !session.is_locked })}
            >
              <LockIcon aria-hidden="true" className="size-4" />
            </Button>
            <Button
              variant="ghost"
              compact
              aria-label={`Change ${session.task_title} at ${formatTime(session.start_at, zone)}`}
              onClick={onEdit}
            >
              Change
            </Button>
            <Button
              variant="ghost"
              compact
              aria-label={`Remove ${session.task_title} at ${formatTime(session.start_at, zone)}`}
              onClick={onRemove}
            >
              Remove
            </Button>
          </span>
        )}
      </div>
      {session.explanation && (
        <details className="mt-1 text-xs text-ink-muted sm:pl-[10.75rem]">
          <summary className="w-fit cursor-pointer hover:text-ink">Why here?</summary>
          <p className="mt-1">{session.explanation}</p>
        </details>
      )}
      {setLocked.error && <p className="mt-1 text-xs text-danger">{setLocked.error.message}</p>}
    </li>
  );
}

function describeStatus(status: ScheduleStatus): string {
  const parts: string[] = [];
  if (status.missed_sessions > 0) {
    parts.push(`${status.missed_sessions} missed session${status.missed_sessions === 1 ? "" : "s"}`);
  }
  const changes = status.added + status.moved + status.resized + status.removed;
  parts.push(`${changes} suggested change${changes === 1 ? "" : "s"}`);
  return parts.join(" and ");
}

export function SchedulePage() {
  const zone = useAuth().user!.timezone;
  const proposal = useCurrentProposal();
  const sessions = useSessions();
  const status = useScheduleStatus();
  const preview = usePreview();
  const apply = useApplyProposal();
  const reject = useRejectProposal();
  const remove = useDeleteSession();
  const [view, setView] = useState<View>(storedView);
  const [opened, setOpened] = useState<StudySession | null>(null);
  const [editing, setEditing] = useState<StudySession | null>(null);
  const [refused, setRefused] = useState<RefusedMove | null>(null);
  const [removing, setRemoving] = useState<StudySession | null>(null);

  const actionError = preview.error ?? apply.error ?? reject.error ?? remove.error;
  const hasSessions = (sessions.data?.length ?? 0) > 0;

  function chooseView(next: View) {
    setView(next);
    localStorage.setItem(VIEW_STORAGE_KEY, next);
  }

  function closeEditor() {
    setEditing(null);
    setRefused(null);
  }

  const showBanner = hasSessions && !proposal.data && status.data?.needs_update === true;

  return (
    <>
      <PageHeader
        title="Schedule"
        subtitle={`Your study plan, in ${zone}.`}
        action={
          <div className="flex flex-wrap gap-2">
            {hasSessions && (
              <Button
                variant="secondary"
                disabled={preview.isPending}
                onClick={() => preview.mutate("regenerate")}
              >
                Rebuild from scratch
              </Button>
            )}
            <Button loading={preview.isPending} onClick={() => preview.mutate("repair")}>
              {hasSessions ? "Update schedule" : "Generate schedule"}
            </Button>
          </div>
        }
      />

      {actionError && (
        <div className="mb-4">
          <ErrorAlert>{actionError.message}</ErrorAlert>
        </div>
      )}

      {showBanner && status.data && (
        <section
          aria-label="Schedule needs an update"
          className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface px-5 py-4"
        >
          <div>
            <h2 className="text-sm font-semibold">Your schedule needs an update</h2>
            <p className="mt-0.5 text-sm text-ink-muted">{describeStatus(status.data)}.</p>
          </div>
          <Button variant="secondary" onClick={() => preview.mutate("repair")}>
            Review changes
          </Button>
        </section>
      )}

      <QueryState query={proposal}>
        {(current) =>
          current && (
            <ProposalReview
              key={current.id}
              proposal={current}
              zone={zone}
              applying={apply.isPending}
              discarding={reject.isPending}
              onApply={(rejected) => {
                preview.reset();
                apply.mutate({ id: current.id, rejected });
              }}
              onDiscard={() => reject.mutate(current.id)}
            />
          )
        }
      </QueryState>

      <div role="group" aria-label="Schedule view" className="mb-4 inline-flex rounded-lg border border-line p-0.5">
        {(["calendar", "list"] as const).map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={view === option}
            onClick={() => chooseView(option)}
            className={`h-8 rounded-md px-3 text-sm font-medium capitalize transition-colors ${
              view === option ? "bg-raised text-ink" : "text-ink-muted hover:text-ink"
            }`}
          >
            {option}
          </button>
        ))}
      </div>

      {view === "calendar" ? (
        <>
          {sessions.data?.length === 0 && (
            <p className="mb-3 text-sm text-ink-muted">
              Nothing is planned yet. Add <Link to="/tasks" className="font-medium text-brand hover:underline">tasks</Link> and{" "}
              <Link to="/availability" className="font-medium text-brand hover:underline">weekly hours</Link>, then generate a schedule.
            </p>
          )}
          <Suspense fallback={<LoadingBlock />}>
            <ScheduleCalendar zone={zone} onOpen={setOpened} onRefused={setRefused} />
          </Suspense>
        </>
      ) : (
        <QueryState query={sessions}>
          {(list) =>
            list.length === 0 ? (
              <EmptyState
                icon={CalendarDays}
                title="No study sessions planned"
                message="Add tasks and set your weekly hours, then generate a schedule."
                action={
                  <div className="flex justify-center gap-4 text-sm font-medium text-brand">
                    <Link to="/tasks" className="hover:underline">
                      Tasks
                    </Link>
                    <Link to="/availability" className="hover:underline">
                      Availability
                    </Link>
                  </div>
                }
              />
            ) : (
              <div className="space-y-6">
                {groupByLocalDay(list, (session) => session.start_at, zone).map((day) => (
                  <section key={day.heading}>
                    <h2 className="mb-2 text-sm font-semibold">{day.heading}</h2>
                    <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
                      {day.items.map((session) => (
                        <SessionRow
                          key={session.id}
                          session={session}
                          zone={zone}
                          onEdit={() => setEditing(session)}
                          onRemove={() => setRemoving(session)}
                        />
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            )
          }
        </QueryState>
      )}

      {opened && (
        <SessionDetails
          session={opened}
          zone={zone}
          onClose={() => setOpened(null)}
          onChange={() => {
            setEditing(opened);
            setOpened(null);
          }}
          onRemove={() => {
            setRemoving(opened);
            setOpened(null);
          }}
        />
      )}
      {(editing ?? refused) && (
        <EditSessionDialog
          session={editing ?? refused!.session}
          zone={zone}
          onClose={closeEditor}
          attempt={refused ?? undefined}
        />
      )}
      {removing && (
        <ConfirmDialog
          title="Remove this session?"
          message={`Its time goes back to "${removing.task_title}" as work still to be planned.`}
          confirmLabel="Remove session"
          loading={remove.isPending}
          onClose={() => setRemoving(null)}
          onConfirm={() => remove.mutate(removing.id, { onSuccess: () => setRemoving(null) })}
        />
      )}
    </>
  );
}
