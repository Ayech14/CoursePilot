import { TriangleAlert } from "lucide-react";
import { useState } from "react";

import { Button } from "../../components/ui/Button";
import {
  formatDateTime,
  formatDuration,
  formatTime,
  groupByLocalDay,
  minutesBetween,
} from "../../lib/datetime";
import type { Proposal, ProposalChange } from "./api";

interface Props {
  proposal: Proposal;
  zone: string;
  applying: boolean;
  discarding: boolean;
  onApply: (rejected: string[]) => void;
  onDiscard: () => void;
}

const LABELS: Record<ProposalChange["action"], string> = {
  create: "Add",
  move: "Move",
  resize: "Shorten",
  remove: "Remove",
};

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function summarize(proposal: Proposal): string {
  const count = (action: ProposalChange["action"]) =>
    proposal.changes.filter((change) => change.action === action).length;
  const parts = [
    [count("create"), "to add"],
    [count("move"), "to move"],
    [count("resize"), "to shorten"],
    [count("remove"), "to remove"],
  ]
    .filter(([value]) => value)
    .map(([value, label]) => `${value} ${label}`);
  const stability =
    proposal.unchanged_sessions > 0
      ? `, ${proposal.unchanged_sessions} unchanged (${proposal.stability_percent}% of your plan)`
      : "";
  return `${parts.join(", ")}${stability}. Nothing changes until you apply.`;
}

interface RowProps {
  change: ProposalChange;
  zone: string;
  accepted: boolean;
  onToggle: () => void;
}

function ChangeRow({ change, zone, accepted, onToggle }: RowProps) {
  const removing = change.action === "remove";
  const start = (change.after_start_at ?? change.before_start_at)!;
  const end = (change.after_end_at ?? change.before_end_at)!;
  return (
    <li className={`py-2.5 ${accepted ? "" : "opacity-50"}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <input
          type="checkbox"
          checked={accepted}
          onChange={onToggle}
          aria-label={`Accept: ${LABELS[change.action]} ${change.task_title} at ${formatTime(start, zone)}`}
          className="accent-brand"
        />
        <span className={`w-14 text-xs font-medium ${removing ? "text-danger" : "text-brand"}`}>
          {LABELS[change.action]}
        </span>
        <span className="w-40 shrink-0 text-ink-muted tabular-nums">
          {formatTime(start, zone)} to {formatTime(end, zone)}
        </span>
        {change.course_color && (
          <span
            aria-hidden="true"
            className="size-2 rounded-full"
            style={{ backgroundColor: change.course_color }}
          />
        )}
        <span className={`font-medium ${removing ? "text-ink-muted line-through" : ""}`}>
          {change.task_title}
        </span>
        <span className="text-xs text-ink-subtle">{formatDuration(minutesBetween(start, end))}</span>
      </div>
      <div className="mt-1 space-y-0.5 text-xs text-ink-muted sm:pl-[17rem]">
        {change.action === "move" && (
          <p>From {formatDateTime(change.before_start_at!, zone)}</p>
        )}
        {change.explanation && <p>{change.explanation}</p>}
        {change.sticky_released && (
          <p className="font-medium text-danger">
            You placed this session yourself. It only moves if you accept this change.
          </p>
        )}
      </div>
    </li>
  );
}

export function ProposalReview({ proposal, zone, applying, discarding, onApply, onDiscard }: Props) {
  const [rejected, setRejected] = useState<Set<string>>(new Set());
  const nothingToDo = proposal.changes.length === 0;
  const allRejected = !nothingToDo && rejected.size === proposal.changes.length;
  const days = groupByLocalDay(
    proposal.changes,
    (change) => (change.after_start_at ?? change.before_start_at)!,
    zone,
  );

  function toggle(id: string) {
    setRejected((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }

  return (
    <section
      aria-label="Proposed schedule"
      className="mb-8 rounded-2xl border border-brand/50 bg-surface shadow-[var(--shadow-card)] p-5 sm:p-6"
    >
      <h2 className="text-base font-semibold">
        {nothingToDo ? "Your schedule is already up to date" : "Review proposed changes"}
      </h2>
      <p className="mt-0.5 text-sm text-ink-muted">
        {nothingToDo
          ? `${plural(proposal.unchanged_sessions, "session")} would stay as planned.`
          : summarize(proposal)}
      </p>

      {proposal.at_risk.length > 0 && (
        <div role="alert" className="mt-4 rounded-lg bg-danger-soft px-4 py-3">
          <p className="flex items-center gap-2 text-sm font-semibold text-danger">
            <TriangleAlert aria-hidden="true" className="size-4" />
            {plural(proposal.at_risk.length, "task")} at risk
          </p>
          <ul className="mt-2 space-y-1.5 text-sm">
            {proposal.at_risk.map((item) => (
              <li key={item.task_id}>
                <span className="font-medium">{item.task_title}</span>
                <span className="text-ink-muted">
                  {" "}
                  is short by {formatDuration(item.shortfall_minutes)}. {item.message}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {proposal.unplaced.length > 0 && (
        <p className="mt-3 text-xs text-ink-subtle">
          Some work with later or no deadlines was left for a future plan:{" "}
          {proposal.unplaced
            .map((item) => `${item.task_title} (${formatDuration(item.minutes)})`)
            .join(", ")}
          .
        </p>
      )}

      {days.map((day) => (
        <div key={day.heading} className="mt-4">
          <h3 className="text-sm font-semibold">{day.heading}</h3>
          <ul className="divide-y divide-line">
            {day.items.map((change) => (
              <ChangeRow
                key={change.id}
                change={change}
                zone={zone}
                accepted={!rejected.has(change.id)}
                onToggle={() => toggle(change.id)}
              />
            ))}
          </ul>
        </div>
      ))}

      <div className="mt-5 flex flex-wrap gap-2">
        {!nothingToDo && (
          <Button
            loading={applying}
            disabled={discarding || allRejected}
            onClick={() => onApply([...rejected])}
          >
            {rejected.size > 0 ? "Apply selected" : "Apply changes"}
          </Button>
        )}
        <Button variant="secondary" loading={discarding} disabled={applying} onClick={onDiscard}>
          {nothingToDo ? "Close" : "Discard"}
        </Button>
      </div>
    </section>
  );
}
