import { Flame } from "lucide-react";

import { Card, CourseDot, ProgressRing, QuietNote } from "../../components/ui/Figures";
import { formatAgo, formatDuration } from "../../lib/datetime";
import { useSetDailyGoal, type RecentSession, type TodayProgress } from "./api";

const GOAL_CHOICES = [60, 120, 180, 240];

function goalLine(studied: number, goal: number | null): string {
  if (goal === null) return "Pick a daily goal to track today against it.";
  if (studied >= goal) return `Goal reached: ${formatDuration(goal)} done.`;
  const percent = Math.round((studied / goal) * 100);
  return `${percent}% of your ${formatDuration(goal)} goal, ${formatDuration(goal - studied)} to go.`;
}

function streakLine({ streak_days: days, studied_today: today }: TodayProgress): string {
  if (days === 0) return "Time any study today to start a streak.";
  const run = days === 1 ? "1 day" : `${days} days`;
  return today ? `${run} in a row` : `${run} in a row. Study today to keep it going.`;
}

/** Today's timed study against the student's own goal, plus their run of study days. */
export function TodayProgressCard({ progress }: { progress: TodayProgress }) {
  const setGoal = useSetDailyGoal();
  const { studied_minutes: studied, goal_minutes: goal } = progress;
  return (
    <Card title="Today's progress" subtitle="Timed study today">
      <div className="flex items-center gap-5">
        <ProgressRing
          value={studied}
          total={goal ?? 0}
          size={104}
          label={
            goal === null
              ? `${formatDuration(studied)} studied today, no daily goal set`
              : `${formatDuration(studied)} of a ${formatDuration(goal)} daily goal`
          }
        >
          <span className="text-center">
            <span className="block text-lg font-semibold tabular-nums">{studied > 0 ? formatDuration(studied) : "0m"}</span>
            <span className="block text-[0.6875rem] text-ink-subtle">today</span>
          </span>
        </ProgressRing>
        <div className="min-w-0 space-y-3">
          <p className="text-sm text-ink-muted">{goalLine(studied, goal)}</p>
          <div role="group" aria-label="Daily goal" className="flex flex-wrap gap-1.5">
            {GOAL_CHOICES.map((minutes) => (
              <GoalChip
                key={minutes}
                label={formatDuration(minutes)}
                pressed={goal === minutes}
                disabled={setGoal.isPending}
                onClick={() => setGoal.mutate(goal === minutes ? null : minutes)}
              />
            ))}
          </div>
          {setGoal.error && <p className="text-xs text-danger">{setGoal.error.message}</p>}
        </div>
      </div>
      <p className="mt-4 flex items-center gap-2 border-t border-line pt-4 text-sm">
        <Flame
          aria-hidden="true"
          className={`size-4 shrink-0 ${progress.streak_days > 0 ? "text-accent" : "text-ink-subtle"}`}
        />
        <span>
          <span className="sr-only">Study streak: </span>
          {streakLine(progress)}
        </span>
      </p>
    </Card>
  );
}

function GoalChip({
  label,
  pressed,
  disabled,
  onClick,
}: {
  label: string;
  pressed: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      title={pressed ? "Click again to turn the goal off" : undefined}
      className={`rounded-lg border px-2.5 py-1 text-xs font-medium tabular-nums transition-colors ${
        pressed
          ? "border-brand bg-brand text-brand-ink"
          : "border-line bg-raised text-ink-muted hover:border-brand/60 hover:text-ink"
      }`}
    >
      {label}
    </button>
  );
}

/** The last sessions the student finished, with the time they actually put in. */
export function RecentActivityCard({ items, zone }: { items: RecentSession[]; zone: string }) {
  return (
    <Card title="Recent activity" subtitle="Finished study sessions">
      {items.length === 0 ? (
        <QuietNote>Sessions you finish with the timer will show up here.</QuietNote>
      ) : (
        <ul className="divide-y divide-line">
          {items.map((item) => (
            <li key={item.session_id} className="flex items-center gap-3 py-2.5 text-sm">
              <CourseDot color={item.course_color} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{item.task_title}</span>
                <span className="block text-xs text-ink-subtle">
                  {item.course_name ? `${item.course_name} · ` : ""}
                  {formatAgo(item.ended_at, zone)}
                </span>
              </span>
              <span className="shrink-0 font-medium tabular-nums">{formatDuration(item.minutes)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
