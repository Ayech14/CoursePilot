import {
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

const CONTROL_CLASSES =
  "h-10 w-full rounded-lg border border-line bg-canvas px-3 text-sm text-ink placeholder:text-ink-subtle disabled:bg-surface disabled:text-ink-subtle aria-invalid:border-danger";

interface WrapperProps {
  label: string;
  error?: string;
  hint?: string;
  children: (ids: { id: string; describedBy: string | undefined }) => ReactNode;
}

function FieldWrapper({ label, error, hint, children }: WrapperProps) {
  const id = useId();
  const messageId = `${id}-message`;
  const message = error ?? hint;
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-ink">
        {label}
      </label>
      {children({ id, describedBy: message ? messageId : undefined })}
      {message && (
        <p id={messageId} className={`text-xs ${error ? "text-danger" : "text-ink-subtle"}`}>
          {message}
        </p>
      )}
    </div>
  );
}

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: string;
}

export function TextField({ label, error, hint, ...rest }: TextFieldProps) {
  return (
    <FieldWrapper label={label} error={error} hint={hint}>
      {({ id, describedBy }) => (
        <input
          {...rest}
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={CONTROL_CLASSES}
        />
      )}
    </FieldWrapper>
  );
}

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  options: (string | SelectOption)[];
  error?: string;
  hint?: string;
}

export function SelectField({ label, options, error, hint, ...rest }: SelectFieldProps) {
  return (
    <FieldWrapper label={label} error={error} hint={hint}>
      {({ id, describedBy }) => (
        <select
          {...rest}
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={CONTROL_CLASSES}
        >
          {options.map((option) => {
            const { value, label: text } =
              typeof option === "string" ? { value: option, label: option } : option;
            return (
              <option key={value} value={value}>
                {text}
              </option>
            );
          })}
        </select>
      )}
    </FieldWrapper>
  );
}

interface TextAreaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  error?: string;
  hint?: string;
}

export function TextAreaField({ label, error, hint, ...rest }: TextAreaFieldProps) {
  return (
    <FieldWrapper label={label} error={error} hint={hint}>
      {({ id, describedBy }) => (
        <textarea
          rows={3}
          {...rest}
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={`${CONTROL_CLASSES} h-auto py-2`}
        />
      )}
    </FieldWrapper>
  );
}
