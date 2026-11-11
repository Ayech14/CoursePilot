import { useState, type FormEvent } from "react";

import { FormError } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { SelectField, TextField } from "../../components/ui/Field";
import { DialogActions, Modal } from "../../components/ui/Modal";
import {
  isoToLocalInput,
  localInputToIso,
  minutesToTimeInput,
  timeInputToMinutes,
} from "../../lib/datetime";
import {
  CATEGORIES,
  DAYS,
  useSaveOneOffBlock,
  useSaveRecurringBlock,
  type Category,
  type OneOffBlock,
  type RecurringBlock,
} from "./api";

const DAY_OPTIONS = DAYS.map((label, index) => ({ value: String(index), label }));

function CategoryField({
  value,
  onChange,
  error,
}: {
  value: Category;
  onChange: (value: Category) => void;
  error?: string;
}) {
  return (
    <SelectField
      label="What is it?"
      options={CATEGORIES}
      value={value}
      onChange={(e) => onChange(e.target.value as Category)}
      error={error}
    />
  );
}

interface RecurringProps {
  block?: RecurringBlock;
  onClose: () => void;
}

export function RecurringBlockDialog({ block, onClose }: RecurringProps) {
  const [title, setTitle] = useState(block?.title ?? "");
  const [category, setCategory] = useState<Category>(block?.category ?? "class");
  const [day, setDay] = useState(String(block?.day_of_week ?? 0));
  const [start, setStart] = useState(block ? minutesToTimeInput(block.start_minute) : "09:00");
  const [end, setEnd] = useState(block ? minutesToTimeInput(block.end_minute) : "10:30");
  const save = useSaveRecurringBlock(block?.id);
  const errors = save.error?.fieldErrors ?? {};

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    save.mutate(
      {
        title,
        category,
        day_of_week: Number(day),
        start_minute: timeInputToMinutes(start, "start"),
        end_minute: timeInputToMinutes(end, "end"),
      },
      { onSuccess: onClose },
    );
  }

  return (
    <Modal title={block ? "Edit weekly busy time" : "Busy every week"} onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <FormError error={save.error} />
        <TextField
          label="Title"
          placeholder="Lecture, Tuesday shift, gym"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          error={errors.title}
        />
        <CategoryField value={category} onChange={setCategory} error={errors.category} />
        <SelectField
          label="Day"
          options={DAY_OPTIONS}
          value={day}
          onChange={(e) => setDay(e.target.value)}
          error={errors.day_of_week}
        />
        <div className="grid grid-cols-2 gap-4">
          <TextField
            label="Starts"
            type="time"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            error={errors.start_minute}
          />
          <TextField
            label="Ends"
            type="time"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            error={errors.end_minute}
          />
        </div>
        <DialogActions>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            Save
          </Button>
        </DialogActions>
      </form>
    </Modal>
  );
}

interface OneOffProps {
  block?: OneOffBlock;
  zone: string;
  onClose: () => void;
}

export function OneOffBlockDialog({ block, zone, onClose }: OneOffProps) {
  const [title, setTitle] = useState(block?.title ?? "");
  const [category, setCategory] = useState<Category>(block?.category ?? "social");
  const [start, setStart] = useState(isoToLocalInput(block?.start_at ?? null, zone));
  const [end, setEnd] = useState(isoToLocalInput(block?.end_at ?? null, zone));
  const save = useSaveOneOffBlock(block?.id);
  const errors = save.error?.fieldErrors ?? {};

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    save.mutate(
      { title, category, start_at: localInputToIso(start, zone), end_at: localInputToIso(end, zone) },
      { onSuccess: onClose },
    );
  }

  return (
    <Modal title={block ? "Edit busy time" : "Busy once"} onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <FormError error={save.error} />
        <TextField
          label="Title"
          placeholder="Shift, dinner with friends, trip"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          error={errors.title}
        />
        <CategoryField value={category} onChange={setCategory} error={errors.category} />
        <TextField
          label="Starts"
          type="datetime-local"
          value={start}
          onChange={(e) => setStart(e.target.value)}
          error={errors.start_at}
          hint={`In your time zone, ${zone}.`}
        />
        <TextField
          label="Ends"
          type="datetime-local"
          value={end}
          onChange={(e) => setEnd(e.target.value)}
          error={errors.end_at}
        />
        <DialogActions>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            Save
          </Button>
        </DialogActions>
      </form>
    </Modal>
  );
}
