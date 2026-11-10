import { Play } from "lucide-react";

import { Button } from "../../components/ui/Button";
import { formatTime, isTodayOrEarlier } from "../../lib/datetime";
import type { StudySession } from "../schedule/api";
import { useActiveTimer, useTimerStep } from "./api";

interface Props {
  session: StudySession;
  zone: string;
  compact?: boolean;
  onStarted?: () => void;
}

/** Offered only for sessions the server would let start: planned, and today or earlier. */
export function StartSessionButton({ session, zone, compact, onStarted }: Props) {
  const timer = useActiveTimer();
  const step = useTimerStep();
  if (session.status !== "planned" || !isTodayOrEarlier(session.start_at, zone)) return null;
  return (
    <span className="inline-flex flex-col items-end">
      <Button
        compact={compact}
        loading={step.isPending}
        disabled={Boolean(timer.data)}
        title={timer.data ? "Finish the open session first" : undefined}
        aria-label={`Start ${session.task_title} at ${formatTime(session.start_at, zone)}`}
        onClick={() => step.mutate({ id: session.id, step: "start" }, { onSuccess: onStarted })}
      >
        <Play aria-hidden="true" className="size-3.5" />
        Start
      </Button>
      {step.error && <span className="mt-1 text-xs text-danger">{step.error.message}</span>}
    </span>
  );
}
