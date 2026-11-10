import { Plus, X } from "lucide-react";
import { useRef, useState } from "react";

import { FormError } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { minutesToTimeInput, timeInputToMinutes } from "../../lib/datetime";
import { DAYS, useSaveWindows, type WeeklyTime } from "./api";

interface Row {
  key: number;
  day: number;
  start: string;
  end: string;
}

const TIME_INPUT =
  "h-9 w-32 rounded-lg border border-line bg-canvas px-2 text-sm text-ink aria-invalid:border-danger";

export function WeeklyEditor({ initial }: { initial: WeeklyTime[] }) {
  const nextKey = useRef(initial.length);
  const [rows, setRows] = useState<Row[]>(() =>
    initial.map((window, key) => ({
      key,
      day: window.day_of_week,
      start: minutesToTimeInput(window.start_minute),
      end: minutesToTimeInput(window.end_minute),
    })),
  );
  const save = useSaveWindows();

  function addRow(day: number) {
    const key = nextKey.current++;
    setRows((current) => [...current, { key, day, start: "09:00", end: "17:00" }]);
    save.reset();
  }

  function updateRow(key: number, change: Partial<Row>) {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...change } : row)));
    save.reset();
  }

  function removeRow(key: number) {
    setRows((current) => current.filter((row) => row.key !== key));
    save.reset();
  }

  function submit() {
    save.mutate(
      rows.map((row) => ({
        day_of_week: row.day,
        start_minute: timeInputToMinutes(row.start, "start"),
        end_minute: timeInputToMinutes(row.end, "end"),
      })),
    );
  }

  // The server reports problems by position in the list it received, which is the order of `rows`.
  const fieldErrors = Object.entries(save.error?.fieldErrors ?? {});
  const errorFor = (index: number) =>
    fieldErrors.find(([field]) => field === `windows.${index}` || field.startsWith(`windows.${index}.`))?.[1];

  return (
    <div>
      <FormError error={save.error} />
      <div className="divide-y divide-line">
        {DAYS.map((name, day) => (
          <div key={name} className="flex flex-wrap items-start gap-x-4 gap-y-2 py-3">
            <p className="w-24 pt-2 text-sm font-medium">{name}</p>
            <div className="min-w-0 flex-1 space-y-2">
              {rows.map((row, index) => {
                if (row.day !== day) return null;
                const error = errorFor(index);
                return (
                  <div key={row.key}>
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        type="time"
                        aria-label={`${name} start`}
                        aria-invalid={error ? true : undefined}
                        value={row.start}
                        onChange={(e) => updateRow(row.key, { start: e.target.value })}
                        className={TIME_INPUT}
                      />
                      <span className="text-sm text-ink-subtle">to</span>
                      <input
                        type="time"
                        aria-label={`${name} end`}
                        aria-invalid={error ? true : undefined}
                        value={row.end}
                        onChange={(e) => updateRow(row.key, { end: e.target.value })}
                        className={TIME_INPUT}
                      />
                      <button
                        type="button"
                        aria-label={`Remove ${name} time range`}
                        onClick={() => removeRow(row.key)}
                        className="flex size-8 items-center justify-center rounded-lg text-ink-subtle hover:bg-raised hover:text-ink"
                      >
                        <X aria-hidden="true" className="size-4" />
                      </button>
                    </div>
                    {error && <p className="mt-1 text-xs text-danger">{error}</p>}
                  </div>
                );
              })}
              <Button variant="ghost" compact onClick={() => addRow(day)} aria-label={`Add ${name} time`}>
                <Plus aria-hidden="true" className="size-4" />
                Add time
              </Button>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center gap-3">
        <Button loading={save.isPending} onClick={submit}>
          Save weekly hours
        </Button>
        {save.isSuccess && (
          <p role="status" className="text-sm text-ink-muted">
            Saved
          </p>
        )}
      </div>
      <p className="mt-3 text-xs text-ink-subtle">
        An end time of 12:00 AM means the end of that day. For overnight study, add a range on each day.
      </p>
    </div>
  );
}
