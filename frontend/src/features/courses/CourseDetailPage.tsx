import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorAlert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { ConfirmDialog } from "../../components/ui/Modal";
import { PageHeader, QueryState } from "../../components/ui/States";
import { formatDateTime, formatDuration, isPast } from "../../lib/datetime";
import { useAuth } from "../auth/AuthContext";
import { TaskFormDialog } from "../tasks/TaskFormDialog";
import { useCourse, useDeleteCourse, useSetArchived, type CourseDetail } from "./api";
import { CourseFormDialog } from "./CourseFormDialog";
import { ProgressBar } from "./CoursesPage";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function CourseView({ course, zone }: { course: CourseDetail; zone: string }) {
  const navigate = useNavigate();
  const [dialog, setDialog] = useState<"edit" | "delete" | "task" | null>(null);
  const setArchived = useSetArchived();
  const remove = useDeleteCourse();
  const { progress } = course;
  const close = () => setDialog(null);

  return (
    <>
      <PageHeader
        title={course.name}
        subtitle={[course.code, course.archived_at && "Archived"].filter(Boolean).join(" · ")}
        action={
          <div className="flex flex-wrap gap-2">
            {!course.archived_at && <Button onClick={() => setDialog("task")}>Add task</Button>}
            <Button variant="secondary" onClick={() => setDialog("edit")}>
              Edit
            </Button>
            <Button
              variant="secondary"
              loading={setArchived.isPending}
              onClick={() => setArchived.mutate({ id: course.id, archived: !course.archived_at })}
            >
              {course.archived_at ? "Restore" : "Archive"}
            </Button>
            <Button variant="ghost" onClick={() => setDialog("delete")}>
              Delete
            </Button>
          </div>
        }
      />
      {setArchived.error && <ErrorAlert>{setArchived.error.message}</ErrorAlert>}
      {course.description && <p className="mb-6 text-sm text-ink-muted">{course.description}</p>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Tasks done" value={`${progress.completed_tasks} / ${progress.total_tasks}`} />
        <Stat label="Work remaining" value={formatDuration(progress.remaining_minutes)} />
        <Stat label="Estimated" value={formatDuration(progress.estimated_minutes)} />
        <Stat label="Time spent" value={formatDuration(progress.actual_minutes)} />
      </div>
      <div className="mt-4">
        <ProgressBar done={progress.completed_tasks} total={progress.total_tasks} color={course.color} />
      </div>

      <section className="mt-10">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">Upcoming deadlines</h2>
          <Link
            to={`/tasks?course=${course.id}`}
            className="text-sm font-medium text-brand hover:underline"
          >
            All tasks
          </Link>
        </div>
        {course.upcoming_tasks.length === 0 ? (
          <p className="rounded-xl border border-dashed border-line px-4 py-8 text-center text-sm text-ink-muted">
            No open tasks with a deadline.
          </p>
        ) : (
          <ul className="divide-y divide-line card">
            {course.upcoming_tasks.map((task) => (
              <li key={task.id} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
                <span className="min-w-0 truncate font-medium">{task.title}</span>
                <span
                  className={`shrink-0 text-xs ${isPast(task.deadline_at!) ? "text-danger" : "text-ink-muted"}`}
                >
                  {isPast(task.deadline_at!) && "Overdue · "}
                  {formatDateTime(task.deadline_at!, zone)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {dialog === "edit" && <CourseFormDialog course={course} onClose={close} />}
      {dialog === "task" && <TaskFormDialog defaultCourseId={course.id} onClose={close} />}
      {dialog === "delete" && (
        <ConfirmDialog
          title="Delete this course?"
          message={
            progress.total_tasks > 0
              ? `This permanently deletes ${course.name} and its ${progress.total_tasks} task(s). To keep the history, archive it instead.`
              : `This permanently deletes ${course.name}.`
          }
          confirmLabel="Delete course"
          loading={remove.isPending}
          onClose={close}
          onConfirm={() =>
            remove.mutate(course.id, { onSuccess: () => navigate("/courses", { replace: true }) })
          }
        />
      )}
    </>
  );
}

export function CourseDetailPage() {
  const { courseId } = useParams();
  const { user } = useAuth();
  const course = useCourse(courseId!);
  return (
    <>
      <Link
        to="/courses"
        className="mb-5 inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft aria-hidden="true" className="size-4" />
        Courses
      </Link>
      <QueryState query={course}>{(data) => <CourseView course={data} zone={user!.timezone} />}</QueryState>
    </>
  );
}
