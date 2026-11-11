import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function Card({
  title,
  subtitle,
  children,
  action,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section aria-label={title} className="card p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-ink-subtle">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function StatTile({
  label,
  value,
  note,
  icon: Icon,
  tone = "brand",
}: {
  label: string;
  value: string;
  note?: string;
  icon?: LucideIcon;
  tone?: "brand" | "accent" | "danger";
}) {
  const chip = { brand: "bg-brand-soft text-brand", accent: "bg-accent-soft text-accent", danger: "bg-danger-soft text-danger" }[tone];
  return (
    <div className="card p-5">
      <p className="flex items-center gap-2 text-xs text-ink-subtle">
        {Icon && (
          <span className={`flex size-6 items-center justify-center rounded-lg ${chip}`}>
            <Icon aria-hidden="true" className="size-3.5" />
          </span>
        )}
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold tracking-tight">{value}</p>
      {note && <p className="mt-0.5 text-xs text-ink-muted">{note}</p>}
    </div>
  );
}

export function CourseDot({ color }: { color: string | null }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block size-2 shrink-0 rounded-full"
      style={{ backgroundColor: color ?? "var(--color-ink-subtle)" }}
    />
  );
}

export interface BarRow {
  key: string;
  label: string;
  color: string | null;
  value: number;
  display: string;
}

/** Ranked bars in one hue. Name and figure are real text, so this is its own table view. */
export function RankedBars({ rows, label }: { rows: BarRow[]; label: string }) {
  const largest = Math.max(...rows.map((row) => row.value), 1);
  return (
    <ul aria-label={label} className="space-y-3">
      {rows.map((row) => (
        <li key={row.key}>
          <div className="mb-1 flex items-center justify-between gap-3 text-sm">
            <span className="flex min-w-0 items-center gap-2">
              <CourseDot color={row.color} />
              <span className="truncate">{row.label}</span>
            </span>
            <span className="shrink-0 text-ink-muted tabular-nums">{row.display}</span>
          </div>
          <div className="h-2 rounded-full bg-raised">
            <div
              className="h-2 rounded-full bg-brand"
              style={{ width: `${(row.value / largest) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function QuietNote({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-ink-muted">{children}</p>;
}
