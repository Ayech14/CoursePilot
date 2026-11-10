import type { ReactNode } from "react";

export function ErrorAlert({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2.5 text-sm text-danger">
      {children}
    </p>
  );
}
