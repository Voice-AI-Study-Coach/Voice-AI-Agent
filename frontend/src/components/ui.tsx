"use client";

import { forwardRef } from "react";
import { AlertIcon } from "./icons";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

/* -------------------------------------------------------------------------- */

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { variant = "primary", size = "md", loading, className, children, disabled, ...rest },
    ref,
  ) => {
    const sizes = {
      sm: "h-8 px-3 text-[13px] gap-1.5",
      md: "h-10 px-4 text-sm gap-2",
      lg: "h-12 px-6 text-[15px] gap-2",
    };
    const variants = {
      primary:
        "bg-ink text-paper hover:bg-ink-soft active:scale-[0.985] elevate-button",
      secondary:
        "bg-surface text-ink border border-line-strong hover:bg-sunken active:scale-[0.985]",
      ghost: "text-ink-soft hover:bg-raised hover:text-ink",
      danger: "bg-danger-soft text-danger hover:bg-danger hover:text-paper",
    };

    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cx(
          "inline-flex items-center justify-center rounded-[10px] font-medium",
          "transition-all duration-150 select-none",
          "disabled:opacity-45 disabled:pointer-events-none",
          sizes[size],
          variants[variant],
          className,
        )}
        {...rest}
      >
        {loading && <Spinner className="size-3.5" />}
        {children}
      </button>
    );
  },
);
Button.displayName = "Button";

/* -------------------------------------------------------------------------- */

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cx("animate-spin", className ?? "size-4")}
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeWidth="2.5"
        opacity="0.2"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

/* -------------------------------------------------------------------------- */

type InputProps = React.InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  hint?: string;
};

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, hint, className, id, ...rest }, ref) => {
    const inputId = id ?? rest.name;
    return (
      <div className="space-y-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-[13px] font-medium text-ink-soft"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cx(
            "w-full h-11 px-3.5 rounded-[10px] bg-surface text-ink text-[15px]",
            "border border-line-strong placeholder:text-ink-ghost",
            "transition-colors duration-150",
            "hover:border-ink-ghost",
            "focus:border-accent focus:outline-none focus:ring-4 focus:ring-accent/8",
            className,
          )}
          {...rest}
        />
        {hint && <p className="text-xs text-ink-faint">{hint}</p>}
      </div>
    );
  },
);
Input.displayName = "Input";

/* -------------------------------------------------------------------------- */

export function ErrorNote({ children }: { children: React.ReactNode }) {
  if (!children) return null;
  return (
    <div className="flex items-start gap-2.5 rounded-[10px] bg-danger-soft px-3.5 py-3 text-[13px] text-danger animate-fade-in">
      <AlertIcon className="size-4 shrink-0 mt-px" />
      <span className="leading-relaxed">{children}</span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

export function Card({
  className,
  children,
  ...rest
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx(
        "rounded-2xl border border-line bg-surface",
        "elevate",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

export function Pill({
  tone = "neutral",
  children,
  className,
}: {
  tone?: "neutral" | "weak" | "mastered" | "accent";
  children: React.ReactNode;
  className?: string;
}) {
  const tones = {
    neutral: "bg-raised text-ink-faint",
    weak: "bg-weak-soft text-weak",
    mastered: "bg-mastered-soft text-mastered",
    accent: "bg-accent-soft text-accent-deep",
  };
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5",
        "text-[11px] font-medium tracking-wide",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------------- */

/** A thin rule with centred text, for separating sections without a heavy border. */
export function Divider({ children }: { children?: React.ReactNode }) {
  if (!children) return <div className="h-px bg-line" />;
  return (
    <div className="flex items-center gap-3">
      <div className="h-px flex-1 bg-line" />
      <span className="text-[11px] uppercase tracking-[0.12em] text-ink-ghost">
        {children}
      </span>
      <div className="h-px flex-1 bg-line" />
    </div>
  );
}

/* -------------------------------------------------------------------------- */

export function ProgressBar({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  return (
    <div className={cx("h-1 rounded-full bg-raised overflow-hidden", className)}>
      <div
        className="h-full rounded-full bg-ink transition-[width] duration-500 ease-out"
        style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */

export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  body?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center animate-fade-up">
      {icon && (
        <div className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-raised text-ink-faint">
          {icon}
        </div>
      )}
      <h3 className="font-serif text-lg text-ink">{title}</h3>
      {body && (
        <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-ink-faint">
          {body}
        </p>
      )}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
