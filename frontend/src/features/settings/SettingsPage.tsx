import { useMutation } from "@tanstack/react-query";
import { Monitor, Moon, Sun, type LucideIcon } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";

import { ErrorAlert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { SelectField, TextField } from "../../components/ui/Field";
import { api, ApiError, type User } from "../../lib/api";
import { timeZoneOptions } from "../../lib/timezones";
import type { ThemeChoice } from "../../lib/theme";
import { useTheme } from "../../lib/useTheme";
import { useAuth } from "../auth/AuthContext";

function ProfileForm({ user }: { user: User }) {
  const { setUser } = useAuth();
  const [displayName, setDisplayName] = useState(user.display_name);
  const [timezone, setTimezone] = useState(user.timezone);
  const zones = useMemo(() => timeZoneOptions(timezone), [timezone]);

  const save = useMutation<User, ApiError>({
    mutationFn: () => api<User>("/users/me", "PATCH", { display_name: displayName, timezone }),
    onSuccess: setUser,
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  const fieldErrors = save.error?.fieldErrors ?? {};

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      {save.error && !Object.keys(fieldErrors).length && <ErrorAlert>{save.error.message}</ErrorAlert>}
      <TextField label="Email" value={user.email} disabled readOnly />
      <TextField
        label="Name"
        value={displayName}
        onChange={(e) => setDisplayName(e.target.value)}
        error={fieldErrors.display_name}
      />
      <SelectField
        label="Time zone"
        options={zones}
        value={timezone}
        onChange={(e) => setTimezone(e.target.value)}
        error={fieldErrors.timezone}
        hint="Weekly availability is interpreted in this zone."
      />
      <div className="flex items-center gap-3">
        <Button type="submit" loading={save.isPending}>
          Save changes
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

const THEME_OPTIONS: { value: ThemeChoice; label: string; icon: LucideIcon }[] = [
  { value: "system", label: "Match device", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

function ThemePicker() {
  const [choice, setChoice] = useTheme();
  return (
    <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-2">
      {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={choice === value}
          onClick={() => setChoice(value)}
          className={`flex flex-col items-center gap-1.5 rounded-xl border px-3 py-3 text-sm transition-colors ${
            choice === value
              ? "border-brand bg-brand-soft text-ink"
              : "border-line text-ink-muted hover:bg-raised hover:text-ink"
          }`}
        >
          <Icon aria-hidden="true" className="size-5" />
          {label}
        </button>
      ))}
    </div>
  );
}

export function SettingsPage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
      <section className="mt-8 max-w-lg card p-6">
        <h2 className="mb-5 text-base font-semibold">Profile</h2>
        <ProfileForm user={user} />
      </section>
      <section className="mt-5 max-w-lg card p-6">
        <h2 className="text-base font-semibold">Appearance</h2>
        <p className="mt-0.5 mb-4 text-sm text-ink-muted">Saved on this device.</p>
        <ThemePicker />
      </section>
    </>
  );
}
