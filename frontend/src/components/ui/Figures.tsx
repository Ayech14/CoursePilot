import type { LucideIcon } from "lucide-react";
import { describeDue, formatDateTime, type DueTone } from "../../lib/datetime";
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

/**
 * A course's name on a soft wash of its own color. The text stays in the ink color, because
 * students pick course colors freely and many of them would be unreadable as text.
 */
export function CourseBadge({ name, color }: { name: string; color: string | null }) {
  const hue = color ?? "var(--color-ink-subtle)";
  return (
    <span
      className="inline-flex max-w-full items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium text-ink"
      style={{ backgroundColor: `color-mix(in srgb, ${hue} 18%, transparent)` }}
    >
      <CourseDot color={color} />
      <span className="truncate">{name}</span>
    </span>
  );
}

const DUE_TONES: Record<DueTone, string> = {
  danger: "bg-danger-soft text-danger",
  accent: "bg-accent-soft text-accent",
  neutral: "bg-raised text-ink-muted",
};

/** "Due tomorrow", "In 3 days" or "Overdue", with the exact time for anyone who hovers. */
export function DueBadge({ iso, zone, now }: { iso: string; zone: string; now?: Date }) {
  const { label, tone } = describeDue(iso, zone, now);
  return (
    <span
      title={formatDateTime(iso, zone)}
      className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${DUE_TONES[tone]}`}
    >
      {label}
    </span>
  );
}

/** A ring showing part of a whole. The figure in the middle and the label carry the meaning. */
export function ProgressRing({
  value,
  total,
  label,
  children,
  size = 88,
}: {
  value: number;
  total: number;
  label: string;
  children?: ReactNode;
  size?: number;
}) {
  const stroke = 8;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const fraction = total <= 0 ? 0 : Math.min(value / total, 1);
  return (
    <div
      role="img"
      aria-label={label}
      className="relative grid shrink-0 place-items-center"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke} className="stroke-raised" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - fraction)}
          className={`stroke-brand transition-[stroke-dashoffset] duration-700 ${fraction === 0 ? "opacity-0" : ""}`}
        />
      </svg>
      <div aria-hidden="true" className="absolute inset-0 grid place-items-center text-center">
        {children}
      </div>
    </div>
  );
}
