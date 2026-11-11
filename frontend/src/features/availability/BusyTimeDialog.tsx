import { DateTime } from "luxon";
import { useState, type FormEvent } from "react";

import { FormError } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/Field";
import { DialogActions, Modal } from "../../components/ui/Modal";
import { formatDateTime, formatTime } from "../../lib/datetime";
import { CATEGORIES, useSaveOneOffBlock, useSaveRecurringBlock, type Category } from "./api";

interface Props {
  start: string;
  end: string;
  zone: string;
  onClose: () => void;
}

/** Added from a time range chosen on the calendar. Once, or every week at the same local time. */
export function BusyTimeDialog({ start, end, zone, onClose }: Props) {
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState<Category>("work");
  const [weekly, setWeekly] = useState(false);
  const once = useSaveOneOffBlock();
  const repeat = useSaveRecurringBlock();
  const active = weekly ? repeat : once;
  const errors = active.error?.fieldErrors ?? {};

  const localStart = DateTime.fromISO(start, { zone });
  const localEnd = DateTime.fromISO(end, { zone });
  const minutesOf = (value: DateTime) => value.hour * 60 + value.minute;
  // A weekly rule lives inside one day, so a range past midnight can only be added once.
  const endsNextMidnight = localEnd.hasSame(localStart.plus({ days: 1 }), "day") && minutesOf(localEnd) === 0;
  const sameDay = localStart.hasSame(localEnd, "day") || endsNextMidnight;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const done = { onSuccess: onClose };
    if (weekly && sameDay) {
      repeat.mutate(
        {
          title,
          category,
          day_of_week: localStart.weekday - 1,
          start_minute: minutesOf(localStart),
          end_minute: endsNextMidnight ? 1440 : minutesOf(localEnd),
        },
        done,
      );
    } else {
      once.mutate({ title, category, start_at: start, end_at: end }, done);
    }
  }

  return (
    <Modal title="Add busy time" onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <FormError error={active.error} />
        <p className="text-sm text-ink-muted">
          {formatDateTime(start, zone)} to {formatTime(end, zone)}
        </p>
        <TextField
          label="Title"
          placeholder="Shift at work, hanging out, appointment"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          error={errors.title}
          autoFocus
        />
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">What is it?</legend>
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={category === option.value}
                onClick={() => setCategory(option.value)}
                className={`h-8 rounded-full border px-3 text-sm transition-colors ${
                  category === option.value
                    ? "border-brand bg-brand-soft text-ink"
                    : "border-line text-ink-muted hover:text-ink"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </fieldset>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={weekly && sameDay}
            disabled={!sameDay}
            onChange={(e) => setWeekly(e.target.checked)}
            className="accent-brand"
          />
          Every {localStart.toFormat("cccc")} at this time
        </label>
        {!sameDay && <p className="text-xs text-ink-subtle">Times that run past midnight can be added once.</p>}
        <DialogActions>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={active.isPending}>
            Add
          </Button>
        </DialogActions>
      </form>
    </Modal>
  );
}
