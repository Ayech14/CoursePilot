import { CalendarPlus, RefreshCw, TriangleAlert } from "lucide-react";
import { DateTime } from "luxon";
import { useState, type FormEvent } from "react";

import { ErrorAlert, FormError } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/Field";
import { ConfirmDialog } from "../../components/ui/Modal";
import { QueryState } from "../../components/ui/States";
import { useConnectFeed, useDeleteFeed, useFeeds, useSyncFeed, type Feed } from "./api";

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function ConnectForm() {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const connect = useConnectFeed();
  const errors = connect.error?.fieldErrors ?? {};

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    connect.mutate(
      { name: name.trim() || "School calendar", url },
      {
        onSuccess: () => {
          setName("");
          setUrl("");
        },
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-3">
      <FormError error={connect.error} />
      <div className="grid gap-3 sm:grid-cols-[1fr_2fr]">
        <TextField label="Name" placeholder="YorkU eClass" value={name} onChange={(e) => setName(e.target.value)} error={errors.name} />
        <TextField
          label="Calendar link"
          placeholder="https:// or webcal://"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          error={errors.url}
          inputMode="url"
          autoComplete="off"
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <details className="text-xs text-ink-muted">
          <summary className="w-fit cursor-pointer hover:text-ink">Where do I find this link?</summary>
          <ul className="mt-2 max-w-xl list-disc space-y-1 pl-4">
            <li>
              eClass (Moodle): open Calendar, choose Import or export calendars, then Export calendar.
              Pick all courses and the upcoming period, then Get calendar URL.
            </li>
            <li>Google Calendar: Settings, your calendar, then Secret address in iCal format.</li>
            <li>Outlook: Settings, Calendar, Shared calendars, then Publish a calendar and copy the ICS link.</li>
          </ul>
        </details>
        <Button type="submit" loading={connect.isPending} disabled={!url.trim()}>
          <CalendarPlus aria-hidden="true" className="size-4" />
          Connect
        </Button>
      </div>
      <p className="text-xs text-ink-subtle">
        Timed events become busy time. Due dates show up on the Tasks page for you to confirm. All-day
        events are skipped. The link is private, so it is never shown again in full.
      </p>
    </form>
  );
}

function FeedRow({ feed, onRemove }: { feed: Feed; onRemove: () => void }) {
  const sync = useSyncFeed();
  const synced = feed.last_synced_at ? DateTime.fromISO(feed.last_synced_at).toRelative() : "never";
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{feed.name}</p>
          <p className="text-xs text-ink-muted">
            {feed.url_hint} · {plural(feed.busy_count, "busy time")} · {plural(feed.pending_deadlines, "deadline")} to
            review · synced {synced}
          </p>
        </div>
        <Button
          variant="ghost"
          compact
          loading={sync.isPending}
          aria-label={`Sync ${feed.name} now`}
          onClick={() => sync.mutate(feed.id)}
        >
          <RefreshCw aria-hidden="true" className="size-4" />
          Sync
        </Button>
        <Button variant="ghost" compact aria-label={`Disconnect ${feed.name}`} onClick={onRemove}>
          Disconnect
        </Button>
      </div>
      {feed.last_error && (
        <p className="mt-1.5 flex items-center gap-1.5 text-xs text-danger">
          <TriangleAlert aria-hidden="true" className="size-3.5" />
          Last sync failed: {feed.last_error} Showing the events from the last good sync.
        </p>
      )}
      {sync.error && <p className="mt-1.5 text-xs text-danger">{sync.error.message}</p>}
    </li>
  );
}

export function ConnectedCalendars() {
  const feeds = useFeeds();
  const remove = useDeleteFeed();
  const [removing, setRemoving] = useState<Feed | null>(null);
  return (
    <div className="space-y-5">
      <ConnectForm />
      {remove.error && <ErrorAlert>{remove.error.message}</ErrorAlert>}
      <QueryState query={feeds}>
        {(list) =>
          list.length > 0 && (
            <ul aria-label="Connected calendars" className="divide-y divide-line border-t border-line">
              {list.map((feed) => (
                <FeedRow key={feed.id} feed={feed} onRemove={() => setRemoving(feed)} />
              ))}
            </ul>
          )
        }
      </QueryState>
      {removing && (
        <ConfirmDialog
          title={`Disconnect ${removing.name}?`}
          message="Its busy times and unreviewed deadlines are removed. Tasks you already added stay."
          confirmLabel="Disconnect"
          loading={remove.isPending}
          onClose={() => setRemoving(null)}
          onConfirm={() => remove.mutate(removing.id, { onSuccess: () => setRemoving(null) })}
        />
      )}
    </div>
  );
}
