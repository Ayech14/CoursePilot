import { ChevronRight, GraduationCap, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "../../components/ui/Button";
import { DueBadge } from "../../components/ui/Figures";
import { EmptyState, PageHeader, QueryState } from "../../components/ui/States";
import { formatDateTime, formatDuration } from "../../lib/datetime";
import { useAuth } from "../auth/AuthContext";
import { useCourses, type Course } from "./api";
import { CourseFormDialog } from "./CourseFormDialog";

export function ProgressBar({ done, total, color }: { done: number; total: number; color: string }) {
  const percent = total === 0 ? 0 : Math.round((done / total) * 100);
  return (
    <div
      role="progressbar"
      aria-label="Tasks completed"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
      className="h-1.5 overflow-hidden rounded-full bg-raised"
    >
      <div className="h-full rounded-full" style={{ width: `${percent}%`, backgroundColor: color }} />
    </div>
  );
}

/** Up to two letters from the course name, e.g. "Data Structures" gives "DS". */
export function monogram(name: string): string {
  const words = name.split(/\s+/).filter((word) => /[\p{L}\p{N}]/u.test(word));
  const letters = words.length > 1 ? [words[0]![0], words[1]![0]] : [...(words[0] ?? "?")].slice(0, 2);
  return letters.join("").toUpperCase();
}

export function CourseMark({ name, color, size = "md" }: { name: string; color: string; size?: "md" | "lg" }) {
  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center rounded-xl font-semibold text-ink ${
        size === "lg" ? "size-12 text-base" : "size-10 text-sm"
      }`}
      style={{ backgroundColor: `color-mix(in srgb, ${color} 24%, transparent)`, boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${color} 40%, transparent)` }}
    >
      {monogram(name)}
    </span>
  );
}

function CourseCard({ course, zone }: { course: Course; zone: string }) {
  const { progress } = course;
  return (
    <Link
      to={`/courses/${course.id}`}
      className="group relative block overflow-hidden card p-5 pt-6 transition duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow-lift)]"
    >
      <span aria-hidden="true" className="absolute inset-x-0 top-0 h-1" style={{ backgroundColor: course.color }} />
      <div className="flex items-start gap-3">
        <CourseMark name={course.name} color={course.color} />
        <div className="min-w-0 flex-1">
          <h2 className="truncate font-semibold">{course.name}</h2>
          <p className="mt-0.5 truncate text-xs text-ink-subtle">
            {course.code ?? "No course code"}
            {course.archived_at && " · Archived"}
          </p>
        </div>
        <ChevronRight
          aria-hidden="true"
          className="mt-1 size-4 shrink-0 text-ink-subtle transition-transform group-hover:translate-x-0.5"
        />
      </div>

      <div className="mt-5 mb-2 flex justify-between text-xs text-ink-muted">
        <span>
          {progress.completed_tasks} of {progress.total_tasks} tasks done
        </span>
        <span className="tabular-nums">{formatDuration(progress.remaining_minutes)} left</span>
      </div>
      <ProgressBar done={progress.completed_tasks} total={progress.total_tasks} color={course.color} />

      <div className="mt-4 flex min-h-6 items-center justify-between gap-2 text-xs text-ink-subtle">
        {progress.next_deadline_at ? (
          <>
            <span className="truncate">Next {formatDateTime(progress.next_deadline_at, zone)}</span>
            <DueBadge iso={progress.next_deadline_at} zone={zone} />
          </>
        ) : (
          <span>No upcoming deadlines</span>
        )}
      </div>
    </Link>
  );
}

export function CoursesPage() {
  const { user } = useAuth();
  const [showArchived, setShowArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const courses = useCourses(showArchived);

  return (
    <>
      <PageHeader
        title="Courses"
        subtitle="Everything you are taking this term."
        action={
          <Button onClick={() => setCreating(true)}>
            <Plus aria-hidden="true" className="size-4" />
            New course
          </Button>
        }
      />
      <label className="mb-5 flex w-fit items-center gap-2 text-sm text-ink-muted">
        <input
          type="checkbox"
          checked={showArchived}
          onChange={(e) => setShowArchived(e.target.checked)}
          className="accent-brand"
        />
        Show archived courses
      </label>

      <QueryState query={courses}>
        {(list) =>
          list.length === 0 ? (
            <EmptyState
              icon={GraduationCap}
              title="No courses yet"
              message="Add your first course, then give it assignments and exams."
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {list.map((course) => (
                <CourseCard key={course.id} course={course} zone={user!.timezone} />
              ))}
            </div>
          )
        }
      </QueryState>

      {creating && <CourseFormDialog onClose={() => setCreating(false)} />}
    </>
  );
}
