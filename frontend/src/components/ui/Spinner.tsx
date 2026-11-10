import { LoaderCircle } from "lucide-react";

export function Spinner({ className = "size-6" }: { className?: string }) {
  return <LoaderCircle aria-hidden="true" className={`animate-spin ${className}`} />;
}

export function FullPageSpinner() {
  return (
    <div role="status" className="flex min-h-dvh items-center justify-center text-ink-muted">
      <Spinner />
      <span className="sr-only">Loading</span>
    </div>
  );
}
