import { useMutation } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import { ErrorAlert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { SelectField, TextField } from "../../components/ui/Field";
import { api, ApiError, type User } from "../../lib/api";
import { timeZoneOptions } from "../../lib/timezones";
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

export function SettingsPage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
      <section className="mt-8 max-w-lg rounded-xl border border-line bg-surface p-6">
        <h2 className="mb-5 text-base font-semibold">Profile</h2>
        <ProfileForm user={user} />
      </section>
    </>
  );
}
