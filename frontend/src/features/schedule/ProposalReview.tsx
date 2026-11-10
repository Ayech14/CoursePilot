import { TriangleAlert } from "lucide-react";

import { Button } from "../../components/ui/Button";
import {
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
  onApply: () => void;
  onDiscard: () => void;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function ChangeRow({ change, zone }: { change: ProposalChange; zone: string }) {
  const removing = change.action === "remove";
  const start = (removing ? change.before_start_at : change.after_start_at)!;
  const end = (removing ? change.before_end_at : change.after_end_at)!;
  return (
    <li className="py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span
          className={`w-16 text-xs font-medium ${removing ? "text-danger" : "text-brand"}`}
        >
          {removing ? "Remove" : "Add"}
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
      {change.explanation && (
        <p className="mt-1 text-xs text-ink-muted sm:pl-[15.25rem]">{change.explanation}</p>
      )}
    </li>
  );
}

export function ProposalReview({ proposal, zone, applying, discarding, onApply, onDiscard }: Props) {
  const added = proposal.changes.filter((change) => change.action !== "remove").length;
  const removed = proposal.changes.length - added;
  const nothingToDo = proposal.changes.length === 0;
  const days = groupByLocalDay(
    proposal.changes,
    (change) => (change.after_start_at ?? change.before_start_at)!,
    zone,
  );

  return (
    <section
      aria-label="Proposed schedule"
      className="mb-8 rounded-xl border border-brand/50 bg-surface p-5 sm:p-6"
    >
      <h2 className="text-base font-semibold">
        {nothingToDo ? "Your schedule is already up to date" : "Review proposed changes"}
      </h2>
      <p className="mt-0.5 text-sm text-ink-muted">
        {nothingToDo
          ? `${plural(proposal.unchanged_sessions, "session")} would stay as planned.`
          : `${plural(added, "session")} to add, ${removed} to remove, ${proposal.unchanged_sessions} unchanged. Nothing changes until you apply.`}
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
              <ChangeRow key={change.id} change={change} zone={zone} />
            ))}
          </ul>
        </div>
      ))}

      <div className="mt-5 flex flex-wrap gap-2">
        {!nothingToDo && (
          <Button loading={applying} disabled={discarding} onClick={onApply}>
            Apply changes
          </Button>
        )}
        <Button variant="secondary" loading={discarding} disabled={applying} onClick={onDiscard}>
          {nothingToDo ? "Close" : "Discard"}
        </Button>
      </div>
    </section>
  );
}
