import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../../lib/api";
import type { Task } from "../tasks/api";

export interface CourseProgress {
  total_tasks: number;
  completed_tasks: number;
  estimated_minutes: number;
  remaining_minutes: number;
  actual_minutes: number;
  next_deadline_at: string | null;
}

export interface Course {
  id: string;
  name: string;
  code: string | null;
  description: string | null;
  color: string;
  archived_at: string | null;
  created_at: string;
  progress: CourseProgress;
}

export interface CourseDetail extends Course {
  upcoming_tasks: Task[];
}

export interface CourseInput {
  name: string;
  code: string | null;
  description: string | null;
  color: string;
}

/** Courses and tasks feed each other's numbers, so a change to either refreshes both. */
export function useAcademicMutation<TInput, TResult = unknown>(
  mutationFn: (input: TInput) => Promise<TResult>,
) {
  const client = useQueryClient();
  return useMutation<TResult, ApiError, TInput>({
    mutationFn,
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["courses"] }),
        client.invalidateQueries({ queryKey: ["tasks"] }),
      ]);
    },
  });
}

export function useCourses(includeArchived = false) {
  return useQuery<Course[], ApiError>({
    queryKey: ["courses", "list", includeArchived],
    queryFn: () => api<Course[]>(`/courses?include_archived=${includeArchived}`),
  });
}

export function useCourse(courseId: string) {
  return useQuery<CourseDetail, ApiError>({
    queryKey: ["courses", "detail", courseId],
    queryFn: () => api<CourseDetail>(`/courses/${courseId}`),
  });
}

export function useSaveCourse(courseId?: string) {
  return useAcademicMutation((input: CourseInput) =>
    courseId
      ? api<Course>(`/courses/${courseId}`, "PATCH", input)
      : api<Course>("/courses", "POST", input),
  );
}

export function useSetArchived() {
  return useAcademicMutation(({ id, archived }: { id: string; archived: boolean }) =>
    api<Course>(`/courses/${id}`, "PATCH", { archived }),
  );
}

export function useDeleteCourse() {
  return useAcademicMutation((id: string) => api<void>(`/courses/${id}`, "DELETE"));
}
