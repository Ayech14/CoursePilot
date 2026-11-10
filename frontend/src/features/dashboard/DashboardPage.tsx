import { Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

function greetingFor(timezone: string, now: Date): string {
  const hour = Number(
    new Intl.DateTimeFormat("en-US", { hour: "numeric", hourCycle: "h23", timeZone: timezone }).format(now),
  );
  if (hour < 5) return "Good evening";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;

  const now = new Date();
  const today = new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: user.timezone,
  }).format(now);

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">
        {greetingFor(user.timezone, now)}, {user.display_name}
      </h1>
      <p className="mt-1 text-sm text-ink-muted">
        {today} · {user.timezone}
      </p>

      <section className="mt-8 flex flex-col items-center rounded-xl border border-dashed border-line px-6 py-16 text-center">
        <span className="flex size-11 items-center justify-center rounded-full bg-brand-soft text-brand">
          <Sparkles aria-hidden="true" className="size-5" />
        </span>
        <h2 className="mt-4 text-base font-semibold">Nothing to show yet</h2>
        <p className="mt-1.5 max-w-md text-sm text-ink-muted">
          Your dashboard will summarize deadlines, today's study plan and workload using your own
          data. It arrives in Milestone 5. Until then, you can start entering your semester.
        </p>
        <div className="mt-5 flex flex-wrap justify-center gap-4 text-sm font-medium text-brand">
          <Link to="/courses" className="hover:underline">
            Add courses
          </Link>
          <Link to="/tasks" className="hover:underline">
            Add tasks
          </Link>
          <Link to="/availability" className="hover:underline">
            Set availability
          </Link>
        </div>
      </section>
    </>
  );
}
