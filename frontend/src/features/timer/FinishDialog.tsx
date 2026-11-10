import { useState, type FormEvent } from "react";

import { FormError } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/Field";
import { DialogActions, Modal } from "../../components/ui/Modal";
import { formatDuration } from "../../lib/datetime";
import type { StudySession } from "../schedule/api";
import { useFinishTimer, type FinishOptions } from "./api";

interface Props {
  session: StudySession;
  timedMinutes: number;
  onClose: () => void;
}

export function FinishDialog({ session, timedMinutes, onClose }: Props) {
  const finish = useFinishTimer();
  const [counted, setCounted] = useState(String(timedMinutes));
  const [remaining, setRemaining] = useState("");
  const [taskDone, setTaskDone] = useState(false);
  const fieldErrors = finish.error?.fieldErrors ?? {};

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const options: FinishOptions = { mark_task_completed: taskDone };
    // Left alone, the server's own total is used. It is more exact than this rounded display.
    if (counted.trim() !== "" && Number(counted) !== timedMinutes) {
      options.actual_minutes = Number(counted);
    }
    if (!taskDone && remaining.trim() !== "") {
      options.remaining_minutes = Math.round(Number(remaining) * 60);
    }
    finish.mutate({ id: session.id, ...options }, { onSuccess: onClose });
  }

  return (
    <Modal title={`Finish: ${session.task_title}`} onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <FormError error={finish.error} />
        <TextField
          label="Time to count (minutes)"
          type="number"
          inputMode="numeric"
          min="0"
          value={counted}
          onChange={(e) => setCounted(e.target.value)}
          error={fieldErrors.actual_minutes}
          hint={`The timer recorded ${formatDuration(timedMinutes)}. Lower this if you left it running.`}
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={taskDone}
            onChange={(e) => setTaskDone(e.target.checked)}
            className="accent-brand"
          />
          This task is finished
        </label>
        {!taskDone && (
          <TextField
            label="Hours of work left (optional)"
            type="number"
            inputMode="decimal"
            min="0"
            step="0.25"
            value={remaining}
            onChange={(e) => setRemaining(e.target.value)}
            error={fieldErrors.remaining_minutes}
            hint="Leave blank to subtract the time you just studied."
          />
        )}
        <DialogActions>
          <Button variant="secondary" onClick={onClose}>
            Keep going
          </Button>
          <Button type="submit" loading={finish.isPending}>
            Finish session
          </Button>
        </DialogActions>
      </form>
    </Modal>
  );
}
