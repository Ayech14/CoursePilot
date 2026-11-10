import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, ApiError } from "../../lib/api";
import type { CourseWorkload } from "../dashboard/api";

export interface Analytics {
  weekly_minutes: { week_start: string; minutes: number }[];
  minutes_per_course: { course_id: string | null; name: string; color: string | null; minutes: number }[];
  completions: { week_start: string; count: number }[];
  workload: CourseWorkload[];
  estimates: {
    tasks_compared: number;
    estimated_minutes: number;
    actual_minutes: number;
    recent: { task_id: string; title: string; estimated_minutes: number; actual_minutes: number }[];
  };
  upcoming: { date: string; planned_minutes: number; deadlines: number }[];
  consistency: {
    days: { date: string; minutes: number }[];
    active_days: number;
    current_streak: number;
    sessions_completed: number;
    sessions_missed: number;
  };
}

export function useAnalytics(weeks: number) {
  return useQuery<Analytics, ApiError>({
    queryKey: ["insights", "analytics", weeks],
    queryFn: () => api(`/analytics?weeks=${weeks}`),
    placeholderData: keepPreviousData,
  });
}
