import type { ReactNode } from "react";

export function Card({ title, subtitle, actions, children, index = 0 }: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  index?: number;
}) {
  return (
    <section className="card reveal p-4" style={{ ["--i" as string]: index }}>
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div>
          <h2 className="text-sm font-medium text-ink">{title}</h2>
          {subtitle && <div className="text-xs text-muted">{subtitle}</div>}
        </div>
        {actions}
      </header>
      {children}
    </section>
  );
}

export function RangeTabs<T extends string>({ value, options, onChange }: {
  value: T;
  options: readonly T[];
  onChange: (v: T) => void;
}) {
  return (
    <div role="tablist" className="inline-flex rounded-lg border border-line p-0.5">
      {options.map((o) => (
        <button
          key={o}
          role="tab"
          type="button"
          aria-selected={o === value}
          onClick={() => onChange(o)}
          className={`num rounded-md px-2.5 py-1 text-xs transition-colors ${o === value ? "bg-surface-2 text-ink" : "text-muted hover:text-ink"}`}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

export function Stat({ label, value, unit, hint }: { label: string; value: ReactNode; unit?: string; hint?: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="eyebrow mb-1">{label}</div>
      <div className="flex items-baseline gap-1">
        <span className="num text-xl font-medium text-ink">{value}</span>
        {unit && <span className="text-xs text-muted">{unit}</span>}
      </div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="flex h-40 items-center justify-center text-sm text-muted">{children}</div>;
}

export function ErrorNote({ error }: { error: unknown }) {
  return (
    <div role="alert" className="card p-4 text-sm text-ink-2">
      <span className="text-serious" aria-hidden>▲ </span>
      Couldn't load data: {error instanceof Error ? error.message : String(error)}
    </div>
  );
}
