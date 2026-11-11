import { Link } from "react-router-dom";

import { Button } from "../../components/ui/Button";
import { DialogActions, Modal } from "../../components/ui/Modal";
import { formatDateTime, formatTime } from "../../lib/datetime";
import { categoryLabel } from "../availability/api";
import type { BusyTime } from "./api";

const SOURCE: Record<BusyTime["source"], string> = {
  weekly: "Repeats every week. Edit it on the Your week page.",
  once: "A one-time busy time. Edit it on the Your week page.",
  calendar: "From a connected calendar. Change it there; the next sync brings it here.",
};

export function BusyDetails({ busy, zone, onClose }: { busy: BusyTime; zone: string; onClose: () => void }) {
  return (
    <Modal title={busy.title} onClose={onClose}>
      <dl className="space-y-3 text-sm">
        <div>
          <dt className="text-xs text-ink-subtle">When</dt>
          <dd>
            {formatDateTime(busy.start_at, zone)} to {formatTime(busy.end_at, zone)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-subtle">Kind</dt>
          <dd>{busy.feed_name ? `${busy.feed_name}` : categoryLabel(busy.category)}</dd>
        </div>
        <p className="text-ink-muted">{SOURCE[busy.source]}</p>
      </dl>
      <DialogActions>
        <Link to="/availability" className="self-center text-sm font-medium text-brand hover:underline">
          Open Your week
        </Link>
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
      </DialogActions>
    </Modal>
  );
}
