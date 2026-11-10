import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ErrorAlert } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { SelectField, TextField } from "../../components/ui/Field";
import { ApiError } from "../../lib/api";
import { detectTimeZone, timeZoneOptions } from "../../lib/timezones";
import { AuthCard } from "./AuthCard";
import { useAuth } from "./AuthContext";

export function RegisterPage() {
  const { register } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [timezone, setTimezone] = useState(detectTimeZone);
  const [error, setError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const zones = useMemo(() => timeZoneOptions(timezone), [timezone]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await register({ email, password, display_name: displayName, timezone });
    } catch (err) {
      setError(err as ApiError);
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Create your account"
      subtitle="Turn your workload into a realistic plan."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-brand hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {error && !Object.keys(error.fieldErrors).length && <ErrorAlert>{error.message}</ErrorAlert>}
        <TextField
          label="Name"
          autoComplete="name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          error={error?.fieldErrors.display_name}
        />
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={error?.fieldErrors.email}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={error?.fieldErrors.password}
          hint="At least 10 characters."
        />
        <SelectField
          label="Time zone"
          options={zones}
          value={timezone}
          onChange={(e) => setTimezone(e.target.value)}
          error={error?.fieldErrors.timezone}
          hint="Detected from your browser. Your schedule is built in this zone."
        />
        <Button type="submit" loading={submitting} className="w-full">
          Create account
        </Button>
      </form>
    </AuthCard>
  );
}
