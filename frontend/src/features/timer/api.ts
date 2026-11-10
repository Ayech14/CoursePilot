import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../../lib/api";
import type { StudySession } from "../schedule/api";

export interface ActiveTimer {
  session: StudySession;
  running: boolean;
  elapsed_seconds: number;
}

export interface FinishOptions {
  actual_minutes?: number;
  remaining_minutes?: number;
  mark_task_completed: boolean;
}

const TIMER_KEY = ["timer"];

export function useActiveTimer() {
  return useQuery<ActiveTimer | null, ApiError>({
    queryKey: TIMER_KEY,
    queryFn: () => api("/sessions/active"),
  });
}

/** Time recorded by the timer changes tasks, the schedule and every figure built from them. */
function useTimerMutation<TInput, TResult>(mutationFn: (input: TInput) => Promise<TResult>) {
  const client = useQueryClient();
  return useMutation<TResult, ApiError, TInput>({
    mutationFn,
    onSettled: () =>
      Promise.all(
        [TIMER_KEY, ["schedule"], ["insights"], ["tasks"], ["courses"]].map((queryKey) =>
          client.invalidateQueries({ queryKey }),
        ),
      ),
  });
}

export function useTimerStep() {
  return useTimerMutation(({ id, step }: { id: string; step: "start" | "pause" | "resume" }) =>
    api<ActiveTimer>(`/sessions/${id}/${step}`, "POST"),
  );
}

export function useFinishTimer() {
  return useTimerMutation(({ id, ...options }: FinishOptions & { id: string }) =>
    api<StudySession>(`/sessions/${id}/finish`, "POST", options),
  );
}

export function useDiscardTimer() {
  return useTimerMutation((id: string) => api<void>(`/sessions/${id}/discard`, "POST"));
}
