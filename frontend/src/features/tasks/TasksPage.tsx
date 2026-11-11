import { Circle, CircleCheck, ListChecks, Plus } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ErrorAlert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { SelectField } from "../../components/ui/Field";
import { ConfirmDialog } from "../../components/ui/Modal";
import { EmptyState, PageHeader, QueryState } from "../../components/ui/States";
import { formatDateTime, formatDuration, isPast } from "../../lib/datetime";
import { useAuth } from "../auth/AuthContext";
import { DeadlineSuggestions } from "../calendars/DeadlineSuggestions";
import { useCourses, type Course } from "../courses/api";
import {
  labelFor,
  PRIORITIES,
  TASK_TYPES,
  useDeleteTask,
  useSetTaskStatus,
  useTasks,
  type Task,
} from "./api";
import { ProgressDialog } from "./ProgressDialog";
import { TaskFormDialog } from "./TaskFormDialog";

const STATUS_FILTERS = [
  { value: "open", label: "Open" },
  { value: "todo", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "", label: "All" },
];

type Dialog = { kind: "create" } | { kind: "edit" | "progress" | "delete"; task: Task } | null;

interface RowProps {
  task: Task;
  course: Course | undefined;
  zone: string;
  onDialog: (dialog: Dialog) => void;
}

function TaskRow({ task, course, zone, onDialog }: RowProps) {
  const setStatus = useSetTaskStatus();
  const done = task.status === "completed";
  const overdue = !done && task.deadline_at !== null && isPast(task.deadline_at);

  return (
    <li className="flex items-start gap-3 px-4 py-3.5">
      <button
        type="button"
        role="checkbox"
        aria-checked={done}
        aria-label={`Mark ${task.title} ${done ? "not finished" : "finished"}`}
        disabled={setStatus.isPending}
        onClick={() => setStatus.mutate({ id: task.id, status: done ? "todo" : "completed" })}
        className={`mt-0.5 shrink-0 ${done ? "text-brand" : "text-ink-subtle hover:text-ink"}`}
      >
        {done ? <CircleCheck className="size-5" /> : <Circle className="size-5" />}
      </button>

      <div className="min-w-0 flex-1">
        <p className={`font-medium ${done ? "text-ink-muted line-through" : ""}`}>{task.title}</p>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
          {course && (
            <span className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="size-2 rounded-full"
                style={{ backgroundColor: course.color }}
              />
              {course.name}
            </span>
          )}
          <span>{labelFor(TASK_TYPES, task.task_type)}</span>
          <span>{labelFor(PRIORITIES, String(task.priority))} priority</span>
          {task.deadline_at ? (
            <span className={overdue ? "font-medium text-danger" : ""}>
              {overdue && "Overdue · "}
              {formatDateTime(task.deadline_at, zone)}
            </span>
          ) : (
            <span>No deadline</span>
          )}
          <span>
            {done
              ? `${formatDuration(task.actual_minutes)} logged`
              : `${formatDuration(task.remaining_minutes)} left of ${formatDuration(task.estimated_minutes)}`}
          </span>
        </p>
        {setStatus.error && <p className="mt-1 text-xs text-danger">{setStatus.error.message}</p>}
      </div>

      <div className="flex shrink-0 flex-wrap justify-end gap-1">
        {!done && (
          <Button variant="ghost" compact onClick={() => onDialog({ kind: "progress", task })}>
            Log
          </Button>
        )}
        <Button variant="ghost" compact onClick={() => onDialog({ kind: "edit", task })}>
          Edit
        </Button>
        <Button
          variant="ghost"
          compact
          aria-label={`Delete ${task.title}`}
          onClick={() => onDialog({ kind: "delete", task })}
        >
          Delete
        </Button>
      </div>
    </li>
  );
}

export function TasksPage() {
  const zone = useAuth().user!.timezone;
  const [searchParams, setSearchParams] = useSearchParams();
  const [dialog, setDialog] = useState<Dialog>(null);
  const courseId = searchParams.get("course") ?? "";
  const [status, setStatus] = useState("open");
  const [taskType, setTaskType] = useState("");

  // Includes archived courses so that their tasks still show the right name and color.
  const courses = useCourses(true);
  const tasks = useTasks({ courseId, status, taskType });
  const remove = useDeleteTask();
  const courseById = new Map((courses.data ?? []).map((course) => [course.id, course]));
  const close = () => setDialog(null);

  return (
    <>
      <PageHeader
        title="Tasks"
        subtitle="Assignments, exams, readings and study work."
        action={
          <Button onClick={() => setDialog({ kind: "create" })}>
            <Plus aria-hidden="true" className="size-4" />
            New task
          </Button>
        }
      />

      <DeadlineSuggestions zone={zone} />

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <SelectField
          label="Course"
          options={[
            { value: "", label: "All courses" },
            ...(courses.data ?? []).map((course) => ({ value: course.id, label: course.name })),
          ]}
          value={courseId}
          onChange={(e) => setSearchParams(e.target.value ? { course: e.target.value } : {})}
        />
        <SelectField
          label="Status"
          options={STATUS_FILTERS}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        />
        <SelectField
          label="Type"
          options={[{ value: "", label: "All types" }, ...TASK_TYPES]}
          value={taskType}
          onChange={(e) => setTaskType(e.target.value)}
        />
      </div>

      <QueryState query={tasks}>
        {({ items, total }) =>
          items.length === 0 ? (
            <EmptyState
              icon={ListChecks}
              title="No tasks here"
              message="Add an assignment or exam, or change the filters above."
            />
          ) : (
            <>
              <ul className="divide-y divide-line card">
                {items.map((task) => (
                  <TaskRow
                    key={task.id}
                    task={task}
                    course={task.course_id ? courseById.get(task.course_id) : undefined}
                    zone={zone}
                    onDialog={setDialog}
                  />
                ))}
              </ul>
              {total > items.length && (
                <p className="mt-3 text-xs text-ink-subtle">
                  Showing the first {items.length} of {total} tasks. Use the filters to narrow them.
                </p>
              )}
            </>
          )
        }
      </QueryState>

      {dialog?.kind === "create" && <TaskFormDialog defaultCourseId={courseId} onClose={close} />}
      {dialog?.kind === "edit" && <TaskFormDialog task={dialog.task} onClose={close} />}
      {dialog?.kind === "progress" && <ProgressDialog task={dialog.task} onClose={close} />}
      {dialog?.kind === "delete" && (
        <ConfirmDialog
          title="Delete this task?"
          message={`This permanently deletes "${dialog.task.title}" and any logged time.`}
          confirmLabel="Delete task"
          loading={remove.isPending}
          onClose={close}
          onConfirm={() => remove.mutate(dialog.task.id, { onSuccess: close })}
        />
      )}
      {remove.error && (
        <div className="mt-4">
          <ErrorAlert>{remove.error.message}</ErrorAlert>
        </div>
      )}
    </>
  );
}
