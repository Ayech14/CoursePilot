import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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
  task_id: string;
  task_title: string;
  course_name: string | null;
  course_color: string | null;
  before_start_at: string | null;
  before_end_at: string | null;
  after_start_at: string | null;
  after_end_at: string | null;
  explanation: string | null;
}

export interface Proposal {
  id: string;
  status: string;
  unchanged_sessions: number;
  at_risk: AtRisk[];
  unplaced: { task_id: string; task_title: string; minutes: number }[];
  changes: ProposalChange[];
}

export interface StudySession {
  id: string;
  task_title: string;
  course_name: string | null;
  course_color: string | null;
  start_at: string;
  end_at: string;
  status: string;
  explanation: string | null;
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

export function usePreview() {
  const client = useQueryClient();
  return useMutation<Proposal, ApiError>({
    mutationFn: () => api("/schedule/preview", "POST"),
    onSuccess: (proposal) => client.setQueryData(PROPOSAL_KEY, proposal),
  });
}

function useCloseProposal<T>(action: "apply" | "reject") {
  const client = useQueryClient();
  return useMutation<T, ApiError, string>({
    mutationFn: (id) => api(`/schedule/proposals/${id}/${action}`, "POST"),
    onSettled: () => client.invalidateQueries({ queryKey: ["schedule"] }),
  });
}

export const useApplyProposal = () => useCloseProposal<{ created: number; removed: number }>("apply");
export const useRejectProposal = () => useCloseProposal<void>("reject");
