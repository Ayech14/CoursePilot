import { useState, type FormEvent } from "react";

import { FormError } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/Field";
import { DialogActions, Modal } from "../../components/ui/Modal";
import { formatDuration, hoursToMinutes } from "../../lib/datetime";
import { useRecordProgress, type ProgressInput, type Task } from "./api";

export function ProgressDialog({ task, onClose }: { task: Task; onClose: () => void }) {
  const [spent, setSpent] = useState("");
  const [remaining, setRemaining] = useState("");
  const [finished, setFinished] = useState(false);
  const [localError, setLocalError] = useState<string>();
  const record = useRecordProgress(task.id);
  const errors = record.error?.fieldErrors ?? {};

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const input: ProgressInput = {};
    if (spent.trim()) input.minutes_spent = Number(spent);
    if (finished) {
      input.mark_completed = true;
    } else if (remaining.trim()) {
      const minutes = hoursToMinutes(remaining);
      if (minutes === null) {
        setLocalError("Enter the hours as a number above 0, or mark the task finished.");
        return;
      }
      input.remaining_minutes = minutes;
    }
    setLocalError(undefined);
    record.mutate(input, { onSuccess: onClose });
  }

  return (
    <Modal title={`Log progress: ${task.title}`} onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <FormError error={record.error} />
        <p className="text-sm text-ink-muted">
          {formatDuration(task.remaining_minutes)} remaining · {formatDuration(task.actual_minutes)}{" "}
          logged so far
        </p>
        <TextField
          label="Time spent (minutes)"
          type="number"
          inputMode="numeric"
          min="1"
          value={spent}
          onChange={(e) => setSpent(e.target.value)}
          error={errors.minutes_spent}
        />
        <TextField
          label="Time still needed (hours, optional)"
          type="number"
          inputMode="decimal"
          min="0"
          step="0.25"
          value={remaining}
          disabled={finished}
          onChange={(e) => setRemaining(e.target.value)}
          error={localError ?? errors.remaining_minutes}
          hint="Leave blank to subtract the time spent from what remains."
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={finished}
            onChange={(e) => setFinished(e.target.checked)}
            className="accent-brand"
          />
          This task is finished
        </label>
        <DialogActions>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={record.isPending}>
            Save progress
          </Button>
        </DialogActions>
      </form>
    </Modal>
  );
}
