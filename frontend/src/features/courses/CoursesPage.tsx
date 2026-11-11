import { GraduationCap, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "../../components/ui/Button";
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

function CourseCard({ course, zone }: { course: Course; zone: string }) {
  const { progress } = course;
  return (
    <Link
      to={`/courses/${course.id}`}
      className="block card p-5 transition-colors hover:border-ink-subtle"
    >
      <div className="flex items-center gap-2.5">
        <span
          aria-hidden="true"
          className="size-2.5 shrink-0 rounded-full"
          style={{ backgroundColor: course.color }}
        />
        <h2 className="truncate font-semibold">{course.name}</h2>
        {course.archived_at && <span className="text-xs text-ink-subtle">Archived</span>}
      </div>
      {course.code && <p className="mt-1 text-xs text-ink-subtle">{course.code}</p>}

      <div className="mt-5 mb-2 flex justify-between text-xs text-ink-muted">
        <span>
          {progress.completed_tasks} of {progress.total_tasks} tasks done
        </span>
        <span>{formatDuration(progress.remaining_minutes)} left</span>
      </div>
      <ProgressBar done={progress.completed_tasks} total={progress.total_tasks} color={course.color} />

      <p className="mt-4 truncate text-xs text-ink-subtle">
        {progress.next_deadline_at
          ? `Next: ${formatDateTime(progress.next_deadline_at, zone)}`
          : "No upcoming deadlines"}
      </p>
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
