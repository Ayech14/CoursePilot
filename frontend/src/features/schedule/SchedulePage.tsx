import { CalendarDays } from "lucide-react";
import { Link } from "react-router-dom";

import { ErrorAlert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { EmptyState, PageHeader, QueryState } from "../../components/ui/States";
import {
  formatDuration,
  formatTime,
  groupByLocalDay,
  minutesBetween,
} from "../../lib/datetime";
import { useAuth } from "../auth/AuthContext";
import {
  useApplyProposal,
  useCurrentProposal,
  usePreview,
  useRejectProposal,
  useSessions,
  type StudySession,
} from "./api";
import { ProposalReview } from "./ProposalReview";

function SessionRow({ session, zone }: { session: StudySession; zone: string }) {
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
      </div>
      {session.explanation && (
        <details className="mt-1 text-xs text-ink-muted sm:pl-[10.75rem]">
          <summary className="w-fit cursor-pointer hover:text-ink">Why here?</summary>
          <p className="mt-1">{session.explanation}</p>
        </details>
      )}
    </li>
  );
}

export function SchedulePage() {
  const zone = useAuth().user!.timezone;
  const proposal = useCurrentProposal();
  const sessions = useSessions();
  const preview = usePreview();
  const apply = useApplyProposal();
  const reject = useRejectProposal();
  const actionError = preview.error ?? apply.error ?? reject.error;
  const hasSessions = (sessions.data?.length ?? 0) > 0;

  return (
    <>
      <PageHeader
        title="Schedule"
        subtitle={`Your study plan, in ${zone}.`}
        action={
          <Button loading={preview.isPending} onClick={() => preview.mutate()}>
            {hasSessions ? "Update schedule" : "Generate schedule"}
          </Button>
        }
      />

      {actionError && (
        <div className="mb-4">
          <ErrorAlert>{actionError.message}</ErrorAlert>
        </div>
      )}

      <QueryState query={proposal}>
        {(current) =>
          current && (
            <ProposalReview
              proposal={current}
              zone={zone}
              applying={apply.isPending}
              discarding={reject.isPending}
              onApply={() => {
                preview.reset();
                apply.mutate(current.id);
              }}
              onDiscard={() => reject.mutate(current.id)}
            />
          )
        }
      </QueryState>

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
                      <SessionRow key={session.id} session={session} zone={zone} />
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )
        }
      </QueryState>
    </>
  );
}
