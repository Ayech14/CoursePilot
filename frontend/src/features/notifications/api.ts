import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../../lib/api";

export type NotificationKind =
  | "deadline_approaching"
  | "task_overdue"
  | "task_unfinished"
  | "schedule_adjusted"
  | "workload_conflict";

export interface AppNotification {
  id: string;
  kind: NotificationKind;
  title: string;
  body: string;
  task_id: string | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationList {
  items: AppNotification[];
  unread: number;
}

const KEY = ["notifications"];
// The server works out new notifications when asked, so asking now and then is what delivers them.
const REFRESH_MS = 5 * 60 * 1000;

export function useNotifications() {
  return useQuery<NotificationList, ApiError>({
    queryKey: KEY,
    queryFn: () => api("/notifications"),
    refetchInterval: REFRESH_MS,
    refetchOnWindowFocus: true,
  });
}

export function useMarkRead() {
  const client = useQueryClient();
  return useMutation<AppNotification, ApiError, string>({
    mutationFn: (id) => api(`/notifications/${id}/read`, "POST"),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  });
}

export function useMarkAllRead() {
  const client = useQueryClient();
  return useMutation<void, ApiError, void>({
    mutationFn: () => api("/notifications/read-all", "POST"),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  });
}
