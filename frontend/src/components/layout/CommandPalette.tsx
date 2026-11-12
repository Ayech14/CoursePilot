import { CornerDownLeft, GraduationCap, ListChecks, Play, Plus, Search, type LucideIcon } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useCourses } from "../../features/courses/api";
import { useTasks, type Task } from "../../features/tasks/api";
import { TaskFormDialog } from "../../features/tasks/TaskFormDialog";
import { QuickStartDialog } from "../../features/timer/QuickStartDialog";
import { NAV_ITEMS } from "./navigation";

const ALL_TASKS = { courseId: "", status: "", taskType: "" };
const RESULT_LIMIT = 8;

interface Item {
  id: string;
  group: "Actions" | "Pages" | "Tasks" | "Courses";
  label: string;
  hint?: string;
  icon: LucideIcon;
  color?: string | null;
  /** Extra words the item can be found by, beyond its label. */
  keywords?: string;
  done?: boolean;
  run: () => void;
}

/** Every word typed must appear somewhere in the item, in any order. */
export function matches(query: string, text: string): boolean {
  const haystack = text.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => haystack.includes(word));
}

type Follow = { kind: "task"; task: Task } | { kind: "new-task" } | { kind: "timer" } | null;

/**
 * Ctrl or ⌘ + K: jump to any page, task or course, or start something, from the keyboard.
 * It searches what the app already loaded, so typing never sends anything to the server.
 */
export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [follow, setFollow] = useState<Follow>(null);
  return (
    <>
      {open && <Palette onClose={onClose} onFollow={setFollow} />}
      {follow?.kind === "task" && <TaskFormDialog task={follow.task} onClose={() => setFollow(null)} />}
      {follow?.kind === "new-task" && <TaskFormDialog onClose={() => setFollow(null)} />}
      {follow?.kind === "timer" && <QuickStartDialog onClose={() => setFollow(null)} />}
    </>
  );
}

function Palette({ onClose, onFollow }: { onClose: () => void; onFollow: (follow: Follow) => void }) {
  const navigate = useNavigate();
  const tasks = useTasks(ALL_TASKS);
  const courses = useCourses(true);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    inputRef.current?.focus();
    return () => previous?.focus();
  }, []);

  const items = useMemo<Item[]>(() => {
    const courseById = new Map((courses.data ?? []).map((course) => [course.id, course]));
    const actions: Item[] = [
      { id: "a-timer", group: "Actions", label: "Start a timer", icon: Play, keywords: "study focus session", run: () => onFollow({ kind: "timer" }) },
      { id: "a-task", group: "Actions", label: "Add a task", icon: Plus, keywords: "new create assignment exam", run: () => onFollow({ kind: "new-task" }) },
    ];
    const pages: Item[] = NAV_ITEMS.map((page) => ({
      id: `p-${page.to}`,
      group: "Pages",
      label: page.label,
      icon: page.icon,
      keywords: page.to.slice(1),
      run: () => navigate(page.to),
    }));
    const taskItems: Item[] = (tasks.data?.items ?? []).map((task) => {
      const course = task.course_id ? courseById.get(task.course_id) : undefined;
      return {
        id: `t-${task.id}`,
        group: "Tasks",
        label: task.title,
        hint: [course?.name, task.status === "completed" ? "Done" : null].filter(Boolean).join(" · ") || undefined,
        icon: ListChecks,
        color: course?.color ?? null,
        done: task.status === "completed",
        keywords: `${course?.name ?? ""} ${course?.code ?? ""} ${task.task_type.replace("_", " ")}`,
        run: () => onFollow({ kind: "task", task }),
      };
    });
    const courseItems: Item[] = (courses.data ?? []).map((course) => ({
      id: `c-${course.id}`,
      group: "Courses",
      label: course.name,
      hint: [course.code, course.archived_at ? "Archived" : null].filter(Boolean).join(" · ") || undefined,
      icon: GraduationCap,
      color: course.color,
      keywords: course.code ?? "",
      run: () => navigate(`/courses/${course.id}`),
    }));

    if (!query.trim()) return [...actions, ...pages];
    const found = (list: Item[]) => list.filter((item) => matches(query, `${item.label} ${item.keywords ?? ""}`));
    // Open tasks first: they are what a student is most likely looking for.
    const openFirst = found(taskItems).sort((a, b) => Number(a.done ?? false) - Number(b.done ?? false));
    return [...found(actions), ...found(pages), ...openFirst.slice(0, RESULT_LIMIT), ...found(courseItems).slice(0, RESULT_LIMIT)];
  }, [query, tasks.data, courses.data, navigate, onFollow]);

  const current = Math.min(active, Math.max(items.length - 1, 0));

  function choose(item: Item | undefined) {
    if (!item) return;
    onClose();
    item.run();
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((current + 1) % Math.max(items.length, 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((current - 1 + items.length) % Math.max(items.length, 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(items[current]);
    }
  }

  useEffect(() => {
    document.getElementById(`${listId}-${current}`)?.scrollIntoView?.({ block: "nearest" });
  }, [current, listId]);

  let lastGroup = "";
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[12vh]">
      <div aria-hidden="true" className="fixed inset-0 bg-overlay backdrop-blur-[2px]" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search"
        className="card relative w-full max-w-xl overflow-hidden shadow-[var(--shadow-lift)]"
      >
        <div className="flex items-center gap-3 border-b border-line px-4">
          <Search aria-hidden="true" className="size-4.5 shrink-0 text-ink-subtle" />
          <input
            ref={inputRef}
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={items.length ? `${listId}-${current}` : undefined}
            aria-label="Search pages, tasks and courses"
            placeholder="Search pages, tasks and courses…"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
            className="h-14 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-ink-subtle"
          />
          <kbd className="hidden rounded border border-line px-1.5 py-0.5 text-[0.6875rem] text-ink-subtle sm:block">Esc</kbd>
        </div>
        <ul id={listId} role="listbox" aria-label="Results" className="max-h-[50vh] overflow-y-auto p-2">
          {items.length === 0 && (
            <li role="presentation" className="px-3 py-8 text-center text-sm text-ink-muted">
              Nothing matches “{query.trim()}”.
            </li>
          )}
          {items.map((item, index) => {
            const heading = item.group !== lastGroup ? item.group : null;
            lastGroup = item.group;
            const Icon = item.icon;
            const selected = index === current;
            return (
              <li key={item.id} role="presentation">
                {heading && (
                  <p role="presentation" className="px-3 pt-2 pb-1 text-[0.6875rem] font-medium tracking-wide text-ink-subtle uppercase">
                    {heading}
                  </p>
                )}
                <div
                  id={`${listId}-${index}`}
                  role="option"
                  aria-selected={selected}
                  onMouseMove={() => setActive(index)}
                  onClick={() => choose(item)}
                  className={`flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm ${selected ? "bg-raised text-ink" : "text-ink-muted"}`}
                >
                  {item.color ? (
                    <span aria-hidden="true" className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />
                  ) : (
                    <Icon aria-hidden="true" className="size-4 shrink-0" />
                  )}
                  <span className="min-w-0 flex-1 truncate font-medium">{item.label}</span>
                  {item.hint && <span className="shrink-0 truncate text-xs text-ink-subtle">{item.hint}</span>}
                  {selected && <CornerDownLeft aria-hidden="true" className="size-3.5 shrink-0 text-ink-subtle" />}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
