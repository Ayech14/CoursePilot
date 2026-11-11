import type { UseQueryResult } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import type { ApiError } from "../../lib/api";
import { Button } from "./Button";
import { Spinner } from "./Spinner";

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  message,
  action,
}: {
  icon: LucideIcon;
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <section className="flex flex-col items-center rounded-2xl border border-dashed border-line px-6 py-14 text-center">
      <span className="flex size-12 items-center justify-center rounded-2xl bg-brand-soft text-brand">
        <Icon aria-hidden="true" className="size-6" />
      </span>
      <h2 className="mt-4 text-base font-semibold">{title}</h2>
      <p className="mt-1.5 max-w-md text-sm text-ink-muted">{message}</p>
      {action && <div className="mt-5">{action}</div>}
    </section>
  );
}

export function LoadingBlock() {
  return (
    <div role="status" className="flex justify-center py-16 text-ink-muted">
      <Spinner />
      <span className="sr-only">Loading</span>
    </div>
  );
}

/** Standard loading and failure handling for anything that displays fetched data. */
export function QueryState<T>({
  query,
  children,
}: {
  query: UseQueryResult<T, ApiError>;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <LoadingBlock />;
  if (query.isError) {
    return (
      <div role="alert" className="card px-6 py-10 text-center">
        <p className="text-sm text-ink">{query.error.message}</p>
        <Button variant="secondary" className="mt-4" onClick={() => void query.refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  return <>{children(query.data)}</>;
}
