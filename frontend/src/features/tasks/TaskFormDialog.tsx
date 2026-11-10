import { useState, type FormEvent } from "react";

import { FormError } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { SelectField, TextAreaField, TextField } from "../../components/ui/Field";
import { DialogActions, Modal } from "../../components/ui/Modal";
import {
  hoursToMinutes,
  isoToLocalInput,
  localInputToIso,
  minutesToHours,
} from "../../lib/datetime";
import { useAuth } from "../auth/AuthContext";
import { useCourses } from "../courses/api";
import { EXAM_TYPES, PRIORITIES, TASK_TYPES, useSaveTask, type Task, type TaskInput } from "./api";

interface Props {
  task?: Task;
  defaultCourseId?: string;
  onClose: () => void;
}

export function TaskFormDialog({ task, defaultCourseId, onClose }: Props) {
  const zone = useAuth().user!.timezone;
  const courses = useCourses(true);
  const save = useSaveTask(task?.id);

  const [title, setTitle] = useState(task?.title ?? "");
  const [courseId, setCourseId] = useState(task?.course_id ?? defaultCourseId ?? "");
  const [taskType, setTaskType] = useState(task?.task_type ?? "assignment");
  const [deadline, setDeadline] = useState(isoToLocalInput(task?.deadline_at ?? null, zone));
  const [estimated, setEstimated] = useState(task ? minutesToHours(task.estimated_minutes) : "");
  const initialRemaining = task ? minutesToHours(task.remaining_minutes) : "";
  const [remaining, setRemaining] = useState(initialRemaining);
  const [priority, setPriority] = useState(String(task?.priority ?? 2));
  const [description, setDescription] = useState(task?.description ?? "");
  const [localErrors, setLocalErrors] = useState<Record<string, string>>({});

  const errors = { ...save.error?.fieldErrors, ...localErrors };
  const isExam = EXAM_TYPES.has(taskType);
  const canEditRemaining = task !== undefined && task.status !== "completed";

  // New work cannot go into an archived course, but a task already in one must keep it.
  const courseOptions = [
    { value: "", label: "No course" },
    ...(courses.data ?? [])
      .filter((course) => !course.archived_at || course.id === task?.course_id)
      .map((course) => ({ value: course.id, label: course.name })),
  ];

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const estimatedMinutes = hoursToMinutes(estimated);
    const problems: Record<string, string> = {};
    if (estimatedMinutes === null) problems.estimated_minutes = "Enter the hours as a number above 0.";

    const input: Partial<TaskInput> = {
      title,
      description: description.trim() || null,
      course_id: courseId || null,
      task_type: taskType,
      deadline_at: localInputToIso(deadline, zone),
      priority: Number(priority),
    };
    if (estimatedMinutes !== null) input.estimated_minutes = estimatedMinutes;

    // Sent only when edited, so saving a title change cannot alter tracked progress.
    if (canEditRemaining && remaining !== initialRemaining) {
      const remainingMinutes = remaining.trim() === "0" ? 0 : hoursToMinutes(remaining);
      if (remainingMinutes === null) problems.remaining_minutes = "Enter the hours as a number.";
      else input.remaining_minutes = remainingMinutes;
    }

    setLocalErrors(problems);
    if (Object.keys(problems).length === 0) {
      save.mutate(input as TaskInput, { onSuccess: onClose });
    }
  }

  return (
    <Modal title={task ? "Edit task" : "New task"} onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <FormError error={save.error} />
        <TextField
          label="Title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          error={errors.title}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField
            label="Course"
            options={courseOptions}
            value={courseId}
            onChange={(e) => setCourseId(e.target.value)}
            error={errors.course_id}
          />
          <SelectField
            label="Type"
            options={TASK_TYPES}
            value={taskType}
            onChange={(e) => setTaskType(e.target.value)}
            error={errors.task_type}
          />
        </div>
        <TextField
          label={isExam ? "Exam date and time" : "Deadline (optional)"}
          type="datetime-local"
          value={deadline}
          onChange={(e) => setDeadline(e.target.value)}
          error={errors.deadline_at}
          hint={`In your time zone, ${zone}.`}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label={isExam ? "Study time needed (hours)" : "Estimated effort (hours)"}
            type="number"
            inputMode="decimal"
            min="0"
            step="0.25"
            value={estimated}
            onChange={(e) => setEstimated(e.target.value)}
            error={errors.estimated_minutes}
          />
          <SelectField
            label="Priority"
            options={PRIORITIES}
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            error={errors.priority}
          />
        </div>
        {canEditRemaining && (
          <TextField
            label="Remaining effort (hours)"
            type="number"
            inputMode="decimal"
            min="0"
            step="0.25"
            value={remaining}
            onChange={(e) => setRemaining(e.target.value)}
            error={errors.remaining_minutes}
            hint="Raise this if the task is taking longer than expected."
          />
        )}
        <TextAreaField
          label="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          error={errors.description}
        />
        <DialogActions>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            {task ? "Save changes" : "Create task"}
          </Button>
        </DialogActions>
      </form>
    </Modal>
  );
}
