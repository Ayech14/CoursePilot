import { useState, type ReactNode } from "react";

import { ErrorAlert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { PageHeader, QueryState } from "../../components/ui/States";
import { formatClock, formatDateTime } from "../../lib/datetime";
import { useAuth } from "../auth/AuthContext";
import { ConnectedCalendars } from "../calendars/ConnectedCalendars";
import {
  categoryLabel,
  DAYS,
  useDeleteOneOffBlock,
  useDeleteRecurringBlock,
  useOneOffBlocks,
  usePreferences,
  useRecurringBlocks,
  useWindows,
  type OneOffBlock,
  type RecurringBlock,
} from "./api";
import { OneOffBlockDialog, RecurringBlockDialog } from "./BlockDialogs";
import { PreferencesForm } from "./PreferencesForm";
import { WeeklyEditor } from "./WeeklyEditor";

function Section({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-line bg-surface p-5 sm:p-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="mt-0.5 text-sm text-ink-muted">{description}</p>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function BlockRow({
  title,
  category,
  when,
  onEdit,
  onDelete,
}: {
  title: string;
  category: string;
  when: string;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2.5">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
          {title}
          <span className="rounded-full bg-raised px-2 py-0.5 text-xs font-normal text-ink-muted">{category}</span>
        </p>
        <p className="text-xs text-ink-muted">{when}</p>
      </div>
      <div className="flex gap-1">
        <Button variant="ghost" compact aria-label={`Edit ${title}`} onClick={onEdit}>
          Edit
        </Button>
        <Button variant="ghost" compact aria-label={`Delete ${title}`} onClick={onDelete}>
          Delete
        </Button>
      </div>
    </li>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="py-4 text-center text-sm text-ink-muted">{children}</p>;
}

type EditState<T> = { block?: T } | null;

function RecurringSection() {
  const blocks = useRecurringBlocks();
  const remove = useDeleteRecurringBlock();
  const [editing, setEditing] = useState<EditState<RecurringBlock>>(null);
  return (
    <Section
      title="Busy every week"
      description="Classes, regular work shifts, practice: anything that repeats weekly."
      action={
        <Button variant="secondary" onClick={() => setEditing({})}>
          Add weekly
        </Button>
      }
    >
      {remove.error && <ErrorAlert>{remove.error.message}</ErrorAlert>}
      <QueryState query={blocks}>
        {(list) =>
          list.length === 0 ? (
            <Empty>Nothing yet. Add your classes and regular shifts so study time avoids them.</Empty>
          ) : (
            <ul className="divide-y divide-line">
              {list.map((block) => (
                <BlockRow
                  key={block.id}
                  title={block.title}
                  category={categoryLabel(block.category)}
                  when={`${DAYS[block.day_of_week]}, ${formatClock(block.start_minute)} to ${formatClock(block.end_minute)}`}
                  onEdit={() => setEditing({ block })}
                  onDelete={() => remove.mutate(block.id)}
                />
              ))}
            </ul>
          )
        }
      </QueryState>
      {editing && <RecurringBlockDialog block={editing.block} onClose={() => setEditing(null)} />}
    </Section>
  );
}

function OneOffSection({ zone }: { zone: string }) {
  // Fixed when the page opens, so that the query key does not change on every render.
  const [now] = useState(() => new Date().toISOString());
  const blocks = useOneOffBlocks(now);
  const remove = useDeleteOneOffBlock();
  const [editing, setEditing] = useState<EditState<OneOffBlock>>(null);
  return (
    <Section
      title="Busy once"
      description="A shift on a particular day, plans with friends, appointments, trips."
      action={
        <Button variant="secondary" onClick={() => setEditing({})}>
          Add one-time
        </Button>
      }
    >
      {remove.error && <ErrorAlert>{remove.error.message}</ErrorAlert>}
      <QueryState query={blocks}>
        {(list) =>
          list.length === 0 ? (
            <Empty>Nothing coming up. You can also drag across the schedule calendar to add one.</Empty>
          ) : (
            <ul className="divide-y divide-line">
              {list.map((block) => (
                <BlockRow
                  key={block.id}
                  title={block.title}
                  category={categoryLabel(block.category)}
                  when={`${formatDateTime(block.start_at, zone)} to ${formatDateTime(block.end_at, zone)}`}
                  onEdit={() => setEditing({ block })}
                  onDelete={() => remove.mutate(block.id)}
                />
              ))}
            </ul>
          )
        }
      </QueryState>
      {editing && (
        <OneOffBlockDialog block={editing.block} zone={zone} onClose={() => setEditing(null)} />
      )}
    </Section>
  );
}

export function AvailabilityPage() {
  const zone = useAuth().user!.timezone;
  const windows = useWindows();
  const preferences = usePreferences();

  return (
    <>
      <PageHeader
        title="Your week"
        subtitle={`When you can study and what you're busy with. Times are in ${zone}.`}
      />
      <div className="space-y-5">
        <Section title="Weekly study hours" description="The times you are generally free to study.">
          <QueryState query={windows}>{(data) => <WeeklyEditor initial={data} />}</QueryState>
        </Section>
        <RecurringSection />
        <OneOffSection zone={zone} />
        <Section
          title="Connected calendars"
          description="Paste a calendar link, like your YorkU eClass calendar, and it stays in sync."
        >
          <ConnectedCalendars />
        </Section>
        <Section title="Study preferences" description="How your schedule should be shaped.">
          <QueryState query={preferences}>{(data) => <PreferencesForm initial={data} />}</QueryState>
        </Section>
      </div>
    </>
  );
}
