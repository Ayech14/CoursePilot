import { Play } from "lucide-react";
import { useState } from "react";

import { Button } from "../../components/ui/Button";
import { useActiveTimer } from "./api";
import { QuickStartDialog } from "./QuickStartDialog";

/** "Start timer" for any task. Unavailable while another session is open, as on the server. */
export function StartTimerButton({ variant = "secondary" }: { variant?: "primary" | "secondary" }) {
  const timer = useActiveTimer();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        variant={variant}
        disabled={Boolean(timer.data)}
        title={timer.data ? "Finish the open session first" : undefined}
        onClick={() => setOpen(true)}
      >
        <Play aria-hidden="true" className="size-3.5" />
        Start timer
      </Button>
      {open && <QuickStartDialog onClose={() => setOpen(false)} />}
    </>
  );
}
