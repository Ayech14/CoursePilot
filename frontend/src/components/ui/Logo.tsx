import { Compass } from "lucide-react";

// The mark keeps its own colours in both themes, as a logo should.
export function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <span className="flex size-8 items-center justify-center rounded-xl bg-gradient-to-br from-[#4fd1bd] to-[#f5b454] text-[#04231e] shadow-sm">
        <Compass aria-hidden="true" className="size-5" />
      </span>
      <span className="text-base font-semibold tracking-tight">CoursePilot</span>
    </span>
  );
}
