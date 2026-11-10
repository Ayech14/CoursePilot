import { useState, type FormEvent } from "react";

import { FormError } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/Field";
import { hoursToMinutes, minutesToHours } from "../../lib/datetime";
import { useSavePreferences, type Preferences } from "./api";

const WHOLE_NUMBER_FIELDS = [
  { name: "preferred_session_minutes", label: "Preferred session (minutes)" },
  { name: "min_session_minutes", label: "Shortest useful session (minutes)" },
  { name: "break_minutes", label: "Break between sessions (minutes)" },
  { name: "deadline_buffer_hours", label: "Finish before deadlines by (hours)" },
  { name: "planning_horizon_days", label: "Plan ahead (days)" },
] as const;

export function PreferencesForm({ initial }: { initial: Preferences }) {
  const [values, setValues] = useState(() =>
    Object.fromEntries(WHOLE_NUMBER_FIELDS.map(({ name }) => [name, String(initial[name])])),
  );
  const [dailyHours, setDailyHours] = useState(minutesToHours(initial.max_daily_minutes));
  const [dailyError, setDailyError] = useState<string>();
  const save = useSavePreferences();
  const errors = save.error?.fieldErrors ?? {};

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const maxDaily = hoursToMinutes(dailyHours);
    if (maxDaily === null) {
      setDailyError("Enter the hours as a number above 0.");
      return;
    }
    setDailyError(undefined);
    const numbers = Object.fromEntries(
      Object.entries(values).map(([name, value]) => [name, value.trim() === "" ? null : Number(value)]),
    );
    save.mutate({ ...numbers, max_daily_minutes: maxDaily } as unknown as Preferences);
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      <FormError error={save.error} />
      <div className="grid gap-4 sm:grid-cols-2">
        {WHOLE_NUMBER_FIELDS.map(({ name, label }) => (
          <TextField
            key={name}
            label={label}
            type="number"
            inputMode="numeric"
            value={values[name]}
            onChange={(e) => setValues((current) => ({ ...current, [name]: e.target.value }))}
            error={errors[name]}
          />
        ))}
        <TextField
          label="Most study in one day (hours)"
          type="number"
          inputMode="decimal"
          step="0.25"
          value={dailyHours}
          onChange={(e) => setDailyHours(e.target.value)}
          error={dailyError ?? errors.max_daily_minutes}
        />
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" loading={save.isPending}>
          Save preferences
        </Button>
        {save.isSuccess && (
          <p role="status" className="text-sm text-ink-muted">
            Saved
          </p>
        )}
      </div>
    </form>
  );
}
