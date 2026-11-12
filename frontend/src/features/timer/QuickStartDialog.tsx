import { Play } from "lucide-react";
import { useState, type FormEvent } from "react";

import { FormError } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { SelectField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { useCourses } from "../courses/api";
import { useTasks } from "../tasks/api";
import { useQuickStart } from "./api";

const OPEN = { courseId: "", status: "open", taskType: "" };

interface Props {
  onClose: () => void;
  /** Start straight on this task instead of asking. */
  taskId?: string;
}

/**
 * Start timing any open task now. The server books a slot from now until the next planned
 * session, at most one preferred session long, and shrinks it to the real time at the end.
 */
export function QuickStartDialog({ onClose, taskId }: Props) {
  const tasks = useTasks(OPEN);
  const courses = useCourses();
  const start = useQuickStart();
  const [chosen, setChosen] = useState(taskId ?? "");

  const courseName = new Map((courses.data ?? []).map((course) => [course.id, course.name]));
  const options = (tasks.data?.items ?? []).map((task) => ({
    value: task.id,
    label: task.course_id && courseName.get(task.course_id) ? `${task.title} (${courseName.get(task.course_id)})` : task.title,
  }));
  const selected = chosen || options[0]?.value || "";

  function submit(event: FormEvent) {
    event.preventDefault();
    if (selected) start.mutate(selected, { onSuccess: onClose });
  }

  return (
    <Modal title="Start a timer" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {tasks.isPending ? (
          <p className="text-sm text-ink-muted">Loading your tasks…</p>
        ) : options.length === 0 ? (
          <p className="text-sm text-ink-muted">You have no open tasks to time. Add a task first.</p>
        ) : (
          <SelectField
            label="What are you working on?"
            options={options}
            value={selected}
            onChange={(event) => setChosen(event.target.value)}
            hint="The time counts toward this task and shows up on your schedule."
          />
        )}
        <FormError error={start.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={start.isPending} disabled={!selected}>
            <Play aria-hidden="true" className="size-3.5" />
            Start timer
          </Button>
        </div>
      </form>
    </Modal>
  );
}
