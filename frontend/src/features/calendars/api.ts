import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../../lib/api";
import type { Category } from "../availability/api";

export interface Feed {
  id: string;
  name: string;
  url_hint: string;
  last_synced_at: string | null;
  last_error: string | null;
  busy_count: number;
  pending_deadlines: number;
}

export interface Suggestion {
  id: string;
  title: string;
  due_at: string;
  feed_name: string;
  course_id: string | null;
  course_name: string | null;
}

export interface BusyTime {
  source: "weekly" | "once" | "calendar";
  id: string;
  title: string;
  category: Category;
  start_at: string;
  end_at: string;
  feed_name: string | null;
}

export interface AcceptInput {
  id: string;
  title: string;
  task_type: string;
  course_id: string | null;
  estimated_minutes: number;
  priority: number;
}

const FEEDS_KEY = ["feeds"];
const SUGGESTIONS_KEY = ["suggestions"];

export function useFeeds() {
  return useQuery<Feed[], ApiError>({ queryKey: FEEDS_KEY, queryFn: () => api("/calendar-feeds") });
}

export function useSuggestions() {
  return useQuery<Suggestion[], ApiError>({
    queryKey: SUGGESTIONS_KEY,
    queryFn: () => api("/deadline-suggestions"),
  });
}

export function useBusyTimes(range: { start: string; end: string } | null) {
  return useQuery<BusyTime[], ApiError>({
    queryKey: ["busy", range],
    queryFn: () => api(`/busy-times?start=${range!.start}&end=${range!.end}`),
    enabled: range !== null,
    placeholderData: keepPreviousData,
  });
}

/** A calendar's contents reach busy times, suggestions, tasks and the schedule's "needs update". */
function useCalendarMutation<TInput, TResult>(mutationFn: (input: TInput) => Promise<TResult>) {
  const client = useQueryClient();
  return useMutation<TResult, ApiError, TInput>({
    mutationFn,
    onSuccess: () =>
      Promise.all(
        [FEEDS_KEY, SUGGESTIONS_KEY, ["busy"], ["tasks"], ["courses"], ["schedule"], ["insights"]].map(
          (queryKey) => client.invalidateQueries({ queryKey }),
        ),
      ),
  });
}

export function useConnectFeed() {
  return useCalendarMutation((input: { name: string; url: string }) =>
    api<Feed>("/calendar-feeds", "POST", input),
  );
}

export function useSyncFeed() {
  return useCalendarMutation((id: string) => api<Feed>(`/calendar-feeds/${id}/sync`, "POST"));
}

export function useSyncStaleFeeds() {
  return useCalendarMutation(() => api<Feed[]>("/calendar-feeds/sync-stale", "POST"));
}

export function useDeleteFeed() {
  return useCalendarMutation((id: string) => api<void>(`/calendar-feeds/${id}`, "DELETE"));
}

export function useAcceptSuggestion() {
  return useCalendarMutation(({ id, ...body }: AcceptInput) =>
    api(`/deadline-suggestions/${id}/accept`, "POST", body),
  );
}

export function useDismissSuggestion() {
  return useCalendarMutation((id: string) => api<void>(`/deadline-suggestions/${id}/dismiss`, "POST"));
}
