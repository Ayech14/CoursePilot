import { Button } from "../../components/ui/Button";
import { DialogActions, Modal } from "../../components/ui/Modal";
import { formatDateTime, formatDuration, formatTime, minutesBetween } from "../../lib/datetime";
import { StartSessionButton } from "../timer/StartSessionButton";
import { useSetLocked, type StudySession } from "./api";

interface Props {
  session: StudySession;
  zone: string;
  onClose: () => void;
  onChange: () => void;
  onRemove: () => void;
}

const STATUS_LABELS: Record<string, string> = {
  planned: "Planned",
  in_progress: "Running now",
  paused: "Paused",
  completed: "Completed",
  missed: "Missed",
};

export function SessionDetails({ session, zone, onClose, onChange, onRemove }: Props) {
  const setLocked = useSetLocked();
  const planned = session.status === "planned";
  return (
    <Modal title={session.task_title} onClose={onClose}>
      <dl className="space-y-3 text-sm">
        <div>
          <dt className="text-xs text-ink-subtle">When</dt>
          <dd>
            {formatDateTime(session.start_at, zone)} to {formatTime(session.end_at, zone)} (
            {formatDuration(minutesBetween(session.start_at, session.end_at))})
          </dd>
        </div>
        {session.course_name && (
          <div>
            <dt className="text-xs text-ink-subtle">Course</dt>
            <dd>{session.course_name}</dd>
          </div>
        )}
        <div>
          <dt className="text-xs text-ink-subtle">Status</dt>
          <dd>
            {STATUS_LABELS[session.status] ?? session.status}
            {session.is_locked && ", locked"}
            {session.status === "completed" && `, ${formatDuration(session.actual_minutes)} studied`}
          </dd>
        </div>
        {session.explanation && (
          <div>
            <dt className="text-xs text-ink-subtle">Why here</dt>
            <dd className="text-ink-muted">{session.explanation}</dd>
          </div>
        )}
      </dl>
      {setLocked.error && <p className="mt-3 text-sm text-danger">{setLocked.error.message}</p>}
      <DialogActions>
        {planned && (
          <>
            <Button variant="secondary" onClick={onRemove}>
              Remove
            </Button>
            <Button
              variant="secondary"
              loading={setLocked.isPending}
              onClick={() =>
                setLocked.mutate({ id: session.id, locked: !session.is_locked }, { onSuccess: onClose })
              }
            >
              {session.is_locked ? "Unlock" : "Lock"}
            </Button>
            <Button variant="secondary" onClick={onChange}>
              Change
            </Button>
            <StartSessionButton session={session} zone={zone} onStarted={onClose} />
          </>
        )}
        {!planned && (
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        )}
      </DialogActions>
    </Modal>
  );
}
