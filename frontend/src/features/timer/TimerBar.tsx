import { Pause, Play, Square } from "lucide-react";
import { useEffect, useState } from "react";

import { ErrorAlert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/Modal";
import { formatElapsed } from "../../lib/datetime";
import { useActiveTimer, useDiscardTimer, useTimerStep, type ActiveTimer } from "./api";
import { FinishDialog } from "./FinishDialog";

/**
 * Counts from the server's figure using only this browser's own elapsed time, so a device whose
 * clock is wrong still shows the right duration. The server remains the record.
 */
function useElapsedSeconds(timer: ActiveTimer, fetchedAt: number): number {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    if (!timer.running) return;
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, [timer.running]);
  if (!timer.running) return timer.elapsed_seconds;
  return timer.elapsed_seconds + Math.max(0, (nowMs - fetchedAt) / 1000);
}

function OpenTimer({ timer, fetchedAt }: { timer: ActiveTimer; fetchedAt: number }) {
  const elapsed = useElapsedSeconds(timer, fetchedAt);
  const step = useTimerStep();
  const discard = useDiscardTimer();
  const [finishing, setFinishing] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const { session, running } = timer;
  const error = step.error ?? discard.error;

  return (
    <section
      aria-label="Study timer"
      className="mb-6 rounded-2xl border border-brand/50 bg-surface shadow-[var(--shadow-card)] px-4 py-3 sm:px-5"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-ink-subtle">{running ? "Studying" : "Paused"}</p>
          <p className="truncate text-sm font-medium">{session.task_title}</p>
        </div>
        <p role="timer" className="text-xl font-semibold tabular-nums">
          {formatElapsed(elapsed)}
        </p>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            compact
            loading={step.isPending}
            onClick={() => step.mutate({ id: session.id, step: running ? "pause" : "resume" })}
          >
            {running ? (
              <Pause aria-hidden="true" className="size-3.5" />
            ) : (
              <Play aria-hidden="true" className="size-3.5" />
            )}
            {running ? "Pause" : "Resume"}
          </Button>
          <Button compact onClick={() => setFinishing(true)}>
            <Square aria-hidden="true" className="size-3.5" />
            Finish
          </Button>
          <Button variant="ghost" compact onClick={() => setDiscarding(true)}>
            Discard
          </Button>
        </div>
      </div>
      {error && (
        <div className="mt-3">
          <ErrorAlert>{error.message}</ErrorAlert>
        </div>
      )}
      {finishing && (
        <FinishDialog
          session={session}
          timedMinutes={Math.round(elapsed / 60)}
          onClose={() => setFinishing(false)}
        />
      )}
      {discarding && (
        <ConfirmDialog
          title="Discard this timer?"
          message="The time won't be recorded, and the session goes back to planned."
          confirmLabel="Discard timer"
          loading={discard.isPending}
          onClose={() => setDiscarding(false)}
          onConfirm={() => discard.mutate(session.id, { onSuccess: () => setDiscarding(false) })}
        />
      )}
    </section>
  );
}

/** Always visible while a session is open, so a timer can't be left running out of sight. */
export function TimerBar() {
  const timer = useActiveTimer();
  if (!timer.data) return null;
  return <OpenTimer timer={timer.data} fetchedAt={timer.dataUpdatedAt} />;
}
