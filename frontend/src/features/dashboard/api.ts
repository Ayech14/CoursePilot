import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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
  progress: TodayProgress;
  recent: RecentSession[];
}

export interface TodayProgress {
  studied_minutes: number;
  goal_minutes: number | null;
  streak_days: number;
  studied_today: boolean;
}

export interface RecentSession {
  session_id: string;
  task_id: string;
  task_title: string;
  course_name: string | null;
  course_color: string | null;
  ended_at: string;
  minutes: number;
}

export interface MonthDay {
  date: string;
  studied_minutes: number;
  studied: { task_id: string; title: string; course_color: string | null; minutes: number }[];
  completed: { task_id: string; title: string; course_color: string | null }[];
  deadlines: {
    task_id: string;
    title: string;
    task_type: string;
    deadline_at: string;
    course_color: string | null;
    completed: boolean;
  }[];
}

export interface MonthOverview {
  month: string;
  goal_minutes: number | null;
  days: MonthDay[];
}

export function useDashboard() {
  return useQuery<Dashboard, ApiError>({
    queryKey: ["insights", "dashboard"],
    queryFn: () => api("/dashboard"),
  });
}

/** One local month, as "YYYY-MM". */
export function useMonth(month: string) {
  return useQuery<MonthOverview, ApiError>({
    queryKey: ["insights", "month", month],
    queryFn: () => api(`/month?month=${month}`),
    placeholderData: keepPreviousData,
  });
}

/** The daily goal is the student's own target; changing it never touches the schedule. */
export function useSetDailyGoal() {
  const client = useQueryClient();
  return useMutation<unknown, ApiError, number | null>({
    mutationFn: (minutes) => api("/preferences/daily-goal", "PUT", { minutes }),
    onSettled: () =>
      Promise.all([["insights"], ["preferences"]].map((queryKey) => client.invalidateQueries({ queryKey }))),
  });
}
