import type { NavItem } from "../../components/layout/navigation";

/** An explicit "not built yet" page, so unfinished areas are never mistaken for working features. */
export function PlannedPage({ item }: { item: NavItem }) {
  const Icon = item.icon;
  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">{item.label}</h1>
      <section className="mt-8 flex flex-col items-center rounded-xl border border-dashed border-line px-6 py-16 text-center">
        <Icon aria-hidden="true" className="size-7 text-ink-subtle" />
        <h2 className="mt-4 text-base font-semibold">Not built yet</h2>
        <p className="mt-1.5 max-w-md text-sm text-ink-muted">{item.plannedDescription}</p>
        <p className="mt-3 text-xs text-ink-subtle">Planned for Milestone {item.plannedMilestone}</p>
      </section>
    </>
  );
}
