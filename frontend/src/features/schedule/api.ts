import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../../lib/api";

export interface AtRisk {
  task_id: string;
  task_title: string;
  deadline_at: string | null;
  shortfall_minutes: number;
  reason: string;
  message: string;
}

export interface ProposalChange {
  id: string;
  action: "create" | "move" | "resize" | "remove";
  session_id: string | null;
  task_id: string;
  task_title: string;
  course_name: string | null;
  course_color: string | null;
  before_start_at: string | null;
  before_end_at: string | null;
  after_start_at: string | null;
  after_end_at: string | null;
  explanation: string | null;
  sticky_released: boolean;
}

export interface Proposal {
  id: string;
  status: string;
  unchanged_sessions: number;
  stability_percent: number;
  at_risk: AtRisk[];
  unplaced: { task_id: string; task_title: string; minutes: number }[];
  changes: ProposalChange[];
}

export interface StudySession {
  id: string;
  task_id: string;
  task_title: string;
  course_name: string | null;
  course_color: string | null;
  start_at: string;
  end_at: string;
  status: string;
  origin: string;
  is_locked: boolean;
  is_user_modified: boolean;
  explanation: string | null;
  actual_minutes: number;
  /** Started on the spot with "Start timer"; discarding removes it. */
  unplanned?: boolean;
}

export interface ScheduleStatus {
  needs_update: boolean;
  added: number;
  moved: number;
  resized: number;
  removed: number;
  missed_sessions: number;
  at_risk: number;
}

export interface Placement {
  ok: boolean;
  conflicts: { kind: string; message: string; session_id: string | null }[];
  warnings: { kind: string; message: string }[];
  alternatives: { start_at: string; end_at: string }[];
}

const PROPOSAL_KEY = ["schedule", "proposal"];
const SESSIONS_KEY = ["schedule", "sessions"];

export function useCurrentProposal() {
  return useQuery<Proposal | null, ApiError>({
    queryKey: PROPOSAL_KEY,
    queryFn: () => api("/schedule/proposals/current"),
  });
}

export function useSessions() {
  return useQuery<StudySession[], ApiError>({
    queryKey: SESSIONS_KEY,
    queryFn: () => api("/sessions"),
  });
}

/** Everything overlapping a date range, including past and finished sessions, for the calendar. */
export function useSessionsInRange(range: { start: string; end: string } | null) {
  return useQuery<StudySession[], ApiError>({
    queryKey: [...SESSIONS_KEY, range],
    queryFn: () => api(`/sessions?start=${range!.start}&end=${range!.end}`),
    enabled: range !== null,
    placeholderData: keepPreviousData,
  });
}

export function useScheduleStatus() {
  return useQuery<ScheduleStatus, ApiError>({
    queryKey: ["schedule", "status"],
    queryFn: () => api("/schedule/status"),
  });
}

export type PreviewMode = "repair" | "regenerate";

export function usePreview() {
  const client = useQueryClient();
  return useMutation<Proposal, ApiError, PreviewMode>({
    mutationFn: (mode) => api("/schedule/preview", "POST", { mode }),
    onSuccess: (proposal) => client.setQueryData(PROPOSAL_KEY, proposal),
  });
}

function useScheduleMutation<TInput, TResult>(mutationFn: (input: TInput) => Promise<TResult>) {
  const client = useQueryClient();
  return useMutation<TResult, ApiError, TInput>({
    mutationFn,
    onSettled: () => client.invalidateQueries({ queryKey: ["schedule"] }),
  });
}

export function useApplyProposal() {
  return useScheduleMutation(({ id, rejected }: { id: string; rejected: string[] }) =>
    api(`/schedule/proposals/${id}/apply`, "POST", { rejected_change_ids: rejected }),
  );
}

export function useRejectProposal() {
  return useScheduleMutation((id: string) => api<void>(`/schedule/proposals/${id}/reject`, "POST"));
}

export function useSetLocked() {
  return useScheduleMutation(({ id, locked }: { id: string; locked: boolean }) =>
    api(`/sessions/${id}/${locked ? "lock" : "unlock"}`, "POST"),
  );
}

export function useDeleteSession() {
  return useScheduleMutation((id: string) => api<void>(`/sessions/${id}`, "DELETE"));
}

export interface SessionTimes {
  id: string;
  start_at: string;
  end_at: string;
  acknowledge_warnings: boolean;
}

export function useMoveSession() {
  return useScheduleMutation(({ id, ...body }: SessionTimes) =>
    api<StudySession>(`/sessions/${id}`, "PATCH", body),
  );
}
