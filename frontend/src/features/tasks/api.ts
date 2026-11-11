import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, ApiError } from "../../lib/api";
import { useAcademicMutation } from "../courses/api";

export type TaskStatus = "todo" | "in_progress" | "completed";

export const TASK_TYPES = [
  { value: "assignment", label: "Assignment" },
  { value: "project", label: "Project" },
  { value: "midterm", label: "Midterm" },
  { value: "final_exam", label: "Final exam" },
  { value: "quiz", label: "Quiz" },
  { value: "reading", label: "Reading" },
  { value: "revision", label: "Revision" },
  { value: "study", label: "General study" },
];

export const EXAM_TYPES = new Set(["midterm", "final_exam", "quiz"]);

export const PRIORITIES = [
  { value: "1", label: "Low" },
  { value: "2", label: "Medium" },
  { value: "3", label: "High" },
  { value: "4", label: "Critical" },
];

export function labelFor(options: { value: string; label: string }[], value: string): string {
  return options.find((option) => option.value === value)?.label ?? value;
}

export interface Task {
  id: string;
  course_id: string | null;
  title: string;
  description: string | null;
  task_type: string;
  deadline_at: string | null;
  estimated_minutes: number;
  remaining_minutes: number;
  actual_minutes: number;
  priority: number;
  status: TaskStatus;
  completed_at: string | null;
}

export interface TaskInput {
  title: string;
  description: string | null;
  course_id: string | null;
  task_type: string;
  deadline_at: string | null;
  estimated_minutes: number;
  priority: number;
  remaining_minutes?: number;
}

export interface ProgressInput {
  minutes_spent?: number;
  remaining_minutes?: number;
  mark_completed?: boolean;
}

export interface TaskListFilters {
  courseId: string;
  status: string;
  taskType: string;
}

const PAGE_SIZE = 500;

function toQuery({ courseId, status, taskType }: TaskListFilters): string {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (courseId) params.set("course_id", courseId);
  if (taskType) params.set("task_type", taskType);
  if (status === "open") {
    params.append("status", "todo");
    params.append("status", "in_progress");
  } else if (status) {
    params.set("status", status);
  }
  return params.toString();
}

export function useTasks(filters: TaskListFilters) {
  return useQuery<{ items: Task[]; total: number }, ApiError>({
    queryKey: ["tasks", "list", filters],
    queryFn: () => api(`/tasks?${toQuery(filters)}`),
  });
}

/** Every task due inside a range, whatever its status, for drawing deadlines on the calendar. */
export function useDeadlinesInRange(range: { start: string; end: string } | null) {
  return useQuery<{ items: Task[]; total: number }, ApiError>({
    queryKey: ["tasks", "due", range],
    queryFn: () =>
      api(`/tasks?${new URLSearchParams({ due_after: range!.start, due_before: range!.end, limit: String(PAGE_SIZE) })}`),
    enabled: range !== null,
    placeholderData: keepPreviousData,
  });
}

export function useSaveTask(taskId?: string) {
  return useAcademicMutation((input: TaskInput) =>
    taskId ? api<Task>(`/tasks/${taskId}`, "PATCH", input) : api<Task>("/tasks", "POST", input),
  );
}

export function useSetTaskStatus() {
  return useAcademicMutation(({ id, status }: { id: string; status: TaskStatus }) =>
    api<Task>(`/tasks/${id}`, "PATCH", { status }),
  );
}

export function useRecordProgress(taskId: string) {
  return useAcademicMutation((input: ProgressInput) =>
    api<Task>(`/tasks/${taskId}/progress`, "POST", input),
  );
}

export function useDeleteTask() {
  return useAcademicMutation((id: string) => api<void>(`/tasks/${id}`, "DELETE"));
}
