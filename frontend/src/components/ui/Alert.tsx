import type { ReactNode } from "react";

import type { ApiError } from "../../lib/api";

export function ErrorAlert({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2.5 text-sm text-danger">
      {children}
    </p>
  );
}

/** Shows errors that do not belong to a field. Field errors are displayed beside their inputs. */
export function FormError({ error }: { error: ApiError | null }) {
  if (!error || Object.keys(error.fieldErrors).length > 0) return null;
  return <ErrorAlert>{error.message}</ErrorAlert>;
}
