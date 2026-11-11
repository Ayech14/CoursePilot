import { Check } from "lucide-react";
import { useState, type FormEvent } from "react";

import { FormError } from "../../components/ui/Alert";
import { Button } from "../../components/ui/Button";
import { TextAreaField, TextField } from "../../components/ui/Field";
import { DialogActions, Modal } from "../../components/ui/Modal";
import { useSaveCourse, type Course } from "./api";

export const COURSE_COLORS = [
  { value: "#45bfae", name: "Teal" },
  { value: "#5b9bf0", name: "Blue" },
  { value: "#9b87f5", name: "Violet" },
  { value: "#e879a9", name: "Pink" },
  { value: "#f28b82", name: "Coral" },
  { value: "#eaa54b", name: "Amber" },
  { value: "#a3c763", name: "Green" },
  { value: "#94a3b8", name: "Slate" },
];

interface Props {
  course?: Course;
  onClose: () => void;
}

export function CourseFormDialog({ course, onClose }: Props) {
  const [name, setName] = useState(course?.name ?? "");
  const [code, setCode] = useState(course?.code ?? "");
  const [description, setDescription] = useState(course?.description ?? "");
  const [color, setColor] = useState(course?.color ?? COURSE_COLORS[0]!.value);
  const save = useSaveCourse(course?.id);
  const errors = save.error?.fieldErrors ?? {};

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    save.mutate(
      { name, code: code.trim() || null, description: description.trim() || null, color },
      { onSuccess: onClose },
    );
  }

  return (
    <Modal title={course ? "Edit course" : "New course"} onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <FormError error={save.error} />
        <TextField
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          error={errors.name}
        />
        <TextField
          label="Course code (optional)"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          error={errors.code}
        />
        <TextAreaField
          label="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          error={errors.description}
        />
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">Color</legend>
          <div className="flex flex-wrap gap-2">
            {COURSE_COLORS.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-label={option.name}
                aria-pressed={color === option.value}
                onClick={() => setColor(option.value)}
                style={{ backgroundColor: option.value }}
                className="flex size-8 items-center justify-center rounded-full text-on-swatch"
              >
                {color === option.value && <Check aria-hidden="true" className="size-4" />}
              </button>
            ))}
          </div>
        </fieldset>
        <DialogActions>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            {course ? "Save changes" : "Create course"}
          </Button>
        </DialogActions>
      </form>
    </Modal>
  );
}
