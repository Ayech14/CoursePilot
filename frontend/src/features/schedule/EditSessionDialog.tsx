import { useState, type FormEvent } from "react";

import { ErrorAlert, FormError } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/Field";
import { DialogActions, Modal } from "../../components/ui/Modal";
import {
  addMinutes,
  formatDateTime,
  isoToLocalInput,
  localInputToIso,
  minutesBetween,
} from "../../lib/datetime";
import { useMoveSession, type Placement, type StudySession } from "./api";

interface Props {
  session: StudySession;
  zone: string;
  onClose: () => void;
}

export function EditSessionDialog({ session, zone, onClose }: Props) {
  const [start, setStart] = useState(isoToLocalInput(session.start_at, zone));
  const [minutes, setMinutes] = useState(String(minutesBetween(session.start_at, session.end_at)));
  const move = useMoveSession();
  const [localError, setLocalError] = useState<string>();

  // A refused or warned move comes back with the reasons and some better times.
  const placement =
    move.error?.code === "session_conflict" || move.error?.code === "placement_warnings"
      ? (move.error.details as Placement)
      : null;
  const needsConfirmation = move.error?.code === "placement_warnings";

  function submit(acknowledge: boolean) {
    const startIso = localInputToIso(start, zone);
    const duration = Number(minutes);
    if (startIso === null) {
      setLocalError("Choose a date and time.");
      return;
    }
    if (!Number.isFinite(duration) || duration <= 0) {
      setLocalError("Enter the length in minutes.");
      return;
    }
    setLocalError(undefined);
    move.mutate(
      {
        id: session.id,
        start_at: startIso,
        end_at: addMinutes(startIso, duration),
        acknowledge_warnings: acknowledge,
      },
      { onSuccess: onClose },
    );
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    submit(false);
  }

  function chooseAlternative(alternative: { start_at: string; end_at: string }) {
    setStart(isoToLocalInput(alternative.start_at, zone));
    setMinutes(String(minutesBetween(alternative.start_at, alternative.end_at)));
    move.reset();
  }

  const fieldErrors = move.error?.fieldErrors ?? {};

  return (
    <Modal title={`Change session: ${session.task_title}`} onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {!placement && <FormError error={move.error} />}
        <TextField
          label="Starts"
          type="datetime-local"
          value={start}
          onChange={(e) => {
            setStart(e.target.value);
            move.reset();
          }}
          error={localError ?? fieldErrors.start_at}
          hint={`In your time zone, ${zone}.`}
        />
        <TextField
          label="Length (minutes)"
          type="number"
          inputMode="numeric"
          min="5"
          value={minutes}
          onChange={(e) => {
            setMinutes(e.target.value);
            move.reset();
          }}
          error={fieldErrors.end_at}
        />

        {placement && (
          <div className="space-y-3">
            <ErrorAlert>
              {[...placement.conflicts, ...placement.warnings].map((item) => (
                <span key={item.kind} className="block">
                  {item.message}
                </span>
              ))}
            </ErrorAlert>
            {placement.alternatives.length > 0 && (
              <div>
                <p className="mb-1.5 text-sm font-medium">Times that work</p>
                <div className="flex flex-wrap gap-2">
                  {placement.alternatives.map((alternative) => (
                    <Button
                      key={alternative.start_at}
                      variant="secondary"
                      compact
                      onClick={() => chooseAlternative(alternative)}
                    >
                      {formatDateTime(alternative.start_at, zone)}
                    </Button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <p className="text-xs text-ink-subtle">
          After you change a session, automatic updates keep it where you put it whenever possible.
        </p>
        <DialogActions>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          {needsConfirmation ? (
            <Button loading={move.isPending} onClick={() => submit(true)}>
              Keep this time anyway
            </Button>
          ) : (
            <Button type="submit" loading={move.isPending}>
              Save
            </Button>
          )}
        </DialogActions>
      </form>
    </Modal>
  );
}
