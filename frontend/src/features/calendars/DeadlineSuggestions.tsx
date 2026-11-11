import { CalendarCheck } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ErrorAlert, FormError } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { SelectField, TextField } from "../../components/ui/Field";
import { DialogActions, Modal } from "../../components/ui/Modal";
import { formatDateTime, hoursToMinutes } from "../../lib/datetime";
import { useCourses } from "../courses/api";
import { PRIORITIES, TASK_TYPES } from "../tasks/api";
import { useAcceptSuggestion, useDismissSuggestion, useSuggestions, type Suggestion } from "./api";

function AcceptDialog({ suggestion, zone, onClose }: { suggestion: Suggestion; zone: string; onClose: () => void }) {
  const courses = useCourses();
  const accept = useAcceptSuggestion();
  const [title, setTitle] = useState(suggestion.title.replace(/\s+is due$/i, ""));
  const [taskType, setTaskType] = useState("assignment");
  const [courseId, setCourseId] = useState(suggestion.course_id ?? "");
  const [hours, setHours] = useState("2");
  const [priority, setPriority] = useState("2");
  const [hoursError, setHoursError] = useState<string>();
  const errors = accept.error?.fieldErrors ?? {};

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const minutes = hoursToMinutes(hours);
    if (minutes === null) {
      setHoursError("Enter how many hours this will take.");
      return;
    }
    setHoursError(undefined);
    accept.mutate(
      {
        id: suggestion.id,
        title,
        task_type: taskType,
        course_id: courseId || null,
        estimated_minutes: minutes,
        priority: Number(priority),
      },
      { onSuccess: onClose },
    );
  }

  return (
    <Modal title="Add as a task" onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <FormError error={accept.error} />
        <p className="text-sm text-ink-muted">
          Due {formatDateTime(suggestion.due_at, zone)}, from {suggestion.feed_name}.
        </p>
        <TextField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} error={errors.title} />
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField label="Type" options={TASK_TYPES} value={taskType} onChange={(e) => setTaskType(e.target.value)} error={errors.task_type} />
          <SelectField
            label="Course"
            options={[{ value: "", label: "No course" }, ...(courses.data ?? []).map((c) => ({ value: c.id, label: c.name }))]}
            value={courseId}
            onChange={(e) => setCourseId(e.target.value)}
            error={errors.course_id}
          />
          <TextField
            label="Hours of work"
            type="number"
            inputMode="decimal"
            min="0"
            step="0.5"
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            error={hoursError ?? errors.estimated_minutes}
            hint="Your best guess. You can change it later."
          />
          <SelectField label="Priority" options={PRIORITIES} value={priority} onChange={(e) => setPriority(e.target.value)} />
        </div>
        <DialogActions>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={accept.isPending}>
            Add task
          </Button>
        </DialogActions>
      </form>
    </Modal>
  );
}

/** Due dates found in connected calendars. Nothing is planned until the student confirms one. */
export function DeadlineSuggestions({ zone }: { zone: string }) {
  const suggestions = useSuggestions();
  const dismiss = useDismissSuggestion();
  const [accepting, setAccepting] = useState<Suggestion | null>(null);
  const list = suggestions.data ?? [];
  if (list.length === 0) return null;

  return (
    <section aria-label="Deadlines from your calendars" className="mb-6 rounded-xl border border-brand/50 bg-surface p-5">
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <CalendarCheck aria-hidden="true" className="size-4 text-brand" />
        {list.length === 1 ? "1 deadline" : `${list.length} deadlines`} from your calendars
      </h2>
      <p className="mt-0.5 text-xs text-ink-muted">Add the ones you need to plan for. Dismissed ones won't come back.</p>
      {dismiss.error && (
        <div className="mt-3">
          <ErrorAlert>{dismiss.error.message}</ErrorAlert>
        </div>
      )}
      <ul className="mt-3 divide-y divide-line">
        {list.map((suggestion) => (
          <li key={suggestion.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5 text-sm">
            <span className="min-w-0 flex-1">
              <span className="block font-medium">{suggestion.title}</span>
              <span className="block text-xs text-ink-muted">
                Due {formatDateTime(suggestion.due_at, zone)}
                {suggestion.course_name ? ` · ${suggestion.course_name}` : ""} · {suggestion.feed_name}
              </span>
            </span>
            <Button compact onClick={() => setAccepting(suggestion)} aria-label={`Add ${suggestion.title} as a task`}>
              Add task
            </Button>
            <Button
              variant="ghost"
              compact
              aria-label={`Dismiss ${suggestion.title}`}
              onClick={() => dismiss.mutate(suggestion.id)}
            >
              Dismiss
            </Button>
          </li>
        ))}
      </ul>
      {accepting && <AcceptDialog suggestion={accepting} zone={zone} onClose={() => setAccepting(null)} />}
    </section>
  );
}
