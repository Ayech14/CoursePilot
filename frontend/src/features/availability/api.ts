import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../../lib/api";

export const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export interface WeeklyTime {
  day_of_week: number;
  start_minute: number;
  end_minute: number;
}

export type Category = "class" | "work" | "social" | "personal" | "other";

export const CATEGORIES: { value: Category; label: string }[] = [
  { value: "class", label: "Class" },
  { value: "work", label: "Work shift" },
  { value: "social", label: "Friends and social" },
  { value: "personal", label: "Personal" },
  { value: "other", label: "Other" },
];

export function categoryLabel(value: Category): string {
  return CATEGORIES.find((option) => option.value === value)?.label ?? "Other";
}

export interface RecurringBlockInput extends WeeklyTime {
  title: string;
  category: Category;
}

export interface RecurringBlock extends RecurringBlockInput {
  id: string;
}

export interface OneOffBlockInput {
  title: string;
  category: Category;
  start_at: string | null;
  end_at: string | null;
}

export interface OneOffBlock {
  id: string;
  title: string;
  category: Category;
  start_at: string;
  end_at: string;
}

export interface Preferences {
  preferred_session_minutes: number;
  min_session_minutes: number;
  break_minutes: number;
  max_daily_minutes: number;
  deadline_buffer_hours: number;
  planning_horizon_days: number;
}

const RECURRING = "/availability/recurring-blocks";
const ONE_OFF = "/availability/one-off-blocks";

function useRefreshing<TInput, TResult>(
  key: string,
  mutationFn: (input: TInput) => Promise<TResult>,
) {
  const client = useQueryClient();
  return useMutation<TResult, ApiError, TInput>({
    mutationFn,
    // Busy times are built from these, and any of them can mean the schedule needs an update.
    onSuccess: () =>
      Promise.all(
        [[key], ["busy"], ["schedule"]].map((queryKey) => client.invalidateQueries({ queryKey })),
      ),
  });
}

export function useWindows() {
  return useQuery<(WeeklyTime & { id: string })[], ApiError>({
    queryKey: ["windows"],
    queryFn: () => api("/availability/windows"),
  });
}

export function useSaveWindows() {
  return useRefreshing("windows", (windows: WeeklyTime[]) =>
    api("/availability/windows", "PUT", { windows }),
  );
}

export function useRecurringBlocks() {
  return useQuery<RecurringBlock[], ApiError>({
    queryKey: ["recurring-blocks"],
    queryFn: () => api(RECURRING),
  });
}

export function useSaveRecurringBlock(id?: string) {
  return useRefreshing("recurring-blocks", (input: RecurringBlockInput) =>
    id ? api(`${RECURRING}/${id}`, "PUT", input) : api(RECURRING, "POST", input),
  );
}

export function useDeleteRecurringBlock() {
  return useRefreshing("recurring-blocks", (id: string) =>
    api<void>(`${RECURRING}/${id}`, "DELETE"),
  );
}

export function useOneOffBlocks(endsAfter: string) {
  return useQuery<OneOffBlock[], ApiError>({
    queryKey: ["one-off-blocks", endsAfter],
    queryFn: () => api(`${ONE_OFF}?ends_after=${encodeURIComponent(endsAfter)}`),
  });
}

export function useSaveOneOffBlock(id?: string) {
  return useRefreshing("one-off-blocks", (input: OneOffBlockInput) =>
    id ? api(`${ONE_OFF}/${id}`, "PUT", input) : api(ONE_OFF, "POST", input),
  );
}

export function useDeleteOneOffBlock() {
  return useRefreshing("one-off-blocks", (id: string) => api<void>(`${ONE_OFF}/${id}`, "DELETE"));
}

export function usePreferences() {
  return useQuery<Preferences, ApiError>({
    queryKey: ["preferences"],
    queryFn: () => api("/preferences"),
  });
}

export function useSavePreferences() {
  return useRefreshing("preferences", (input: Preferences) => api("/preferences", "PUT", input));
}
