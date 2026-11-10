import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "../../lib/api";
import type { StudySession } from "../schedule/api";

export interface DeadlineItem {
  task_id: string;
  title: string;
  task_type: string;
  deadline_at: string;
  course_name: string | null;
  course_color: string | null;
  remaining_minutes: number;
}

export interface AttentionItem {
  task_id: string;
  title: string;
  course_color: string | null;
  deadline_at: string;
  reason: "overdue" | "not_fully_planned" | "due_soon";
  unplanned_minutes: number;
}

export interface CourseWorkload {
  course_id: string | null;
  name: string;
  code: string | null;
  color: string | null;
  open_tasks: number;
  completed_tasks: number;
  remaining_minutes: number;
}

export interface Dashboard {
  today: StudySession[];
  upcoming_assignments: DeadlineItem[];
  upcoming_exams: DeadlineItem[];
  attention: AttentionItem[];
  attention_total: number;
  week: { week_start: string; studied_minutes: number; planned_minutes: number };
  tasks: { completed: number; remaining: number; overdue: number };
  workload: CourseWorkload[];
}

export function useDashboard() {
  return useQuery<Dashboard, ApiError>({
    queryKey: ["insights", "dashboard"],
    queryFn: () => api("/dashboard"),
  });
}
