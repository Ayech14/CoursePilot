import type { ButtonHTMLAttributes } from "react";

import { Spinner } from "./Spinner";

const VARIANTS = {
  primary: "bg-brand text-brand-ink hover:bg-brand-hover",
  secondary: "border border-line bg-raised text-ink hover:bg-line",
  danger: "bg-danger text-canvas hover:opacity-90",
  ghost: "text-ink-muted hover:bg-raised hover:text-ink",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean;
  variant?: keyof typeof VARIANTS;
  compact?: boolean;
}

export function Button({
  loading = false,
  variant = "primary",
  compact = false,
  disabled,
  children,
  className = "",
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-lg text-sm font-semibold whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
        compact ? "h-8 px-2.5" : "h-10 px-4"
      } ${VARIANTS[variant]} ${className}`}
    >
      {loading && <Spinner className="size-4" />}
      {children}
    </button>
  );
}
