import { Compass } from "lucide-react";

export function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <span className="flex size-8 items-center justify-center rounded-lg bg-brand-soft text-brand">
        <Compass aria-hidden="true" className="size-5" />
      </span>
      <span className="text-base font-semibold tracking-tight">CoursePilot</span>
    </span>
  );
}
