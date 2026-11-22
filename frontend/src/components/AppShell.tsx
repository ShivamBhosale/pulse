import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useRefresh } from "../api/hooks";
import { fmtAgo } from "../lib/format";
import { useTheme } from "../lib/theme";

const NAV = [
  { to: "/", label: "Today", icon: "M3 12h4l3-8 4 16 3-8h4" },
  { to: "/sleep", label: "Sleep", icon: "M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" },
];

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

function ReconnectBanner({ error }: { error: string | null | undefined }) {
  return (
    <div role="alert" className="card mb-4 flex items-start gap-3 border-serious/40 p-3 text-sm">
      <span aria-hidden className="mt-0.5 text-serious">▲</span>
      <div>
        <div className="font-medium text-ink">Google connection needs attention</div>
        <div className="text-ink-2">
          Syncing has stopped. On the server run <code className="num rounded bg-surface-2 px-1">pulse auth</code> to reconnect.
        </div>
        {error && <div className="mt-1 text-xs text-muted">{error}</div>}
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { theme, toggle } = useTheme();
  const { refresh, syncing, status } = useRefresh();
  const lastSync = status?.last_sync;
  return (
    <div className="mx-auto min-h-dvh max-w-[1180px] px-4 pb-24 pt-[max(env(safe-area-inset-top),14px)] md:px-8 md:pb-10">
      <header className="mb-5 flex items-center gap-3">
        <div className="flex items-center gap-2">
          <svg viewBox="0 0 512 512" width="26" height="26" aria-hidden>
            <rect width="512" height="512" rx="112" fill="var(--surface-2)" />
            <path d="M84 280h88l34-92 52 176 44-128 26 44h100" fill="none" stroke="var(--accent)" strokeWidth="34" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="text-[17px] font-semibold tracking-tight">Pulse</span>
        </div>
        <nav className="ml-6 hidden gap-1 md:flex" aria-label="Main">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end
              className={({ isActive }) =>
                `rounded-lg px-3 py-1.5 text-sm transition-colors ${isActive ? "bg-surface-2 text-ink" : "text-muted hover:text-ink"}`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={refresh}
            disabled={syncing}
            className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-1.5 text-xs text-ink-2 transition-colors hover:text-ink disabled:opacity-70"
            title="Sync now"
          >
            <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${syncing ? "syncing-dot bg-accent" : "bg-good"}`} />
            <span className="num">{syncing ? "Syncing…" : `Synced ${fmtAgo(lastSync)}`}</span>
          </button>
          <button
            type="button"
            onClick={toggle}
            className="rounded-lg border border-line p-1.5 text-muted transition-colors hover:text-ink"
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            <Icon d={theme === "dark" ? "M12 3v2M12 19v2M5 12H3M21 12h-2M6.3 6.3 4.9 4.9M19.1 19.1l-1.4-1.4M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z" : "M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"} />
          </button>
        </div>
      </header>
      {status && !status.auth.ok && <ReconnectBanner error={status.auth.error} />}
      <main>{children}</main>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-10 flex justify-around border-t border-line bg-surface/90 pb-[max(env(safe-area-inset-bottom),8px)] pt-2 backdrop-blur md:hidden"
      >
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end
            className={({ isActive }) => `flex flex-col items-center gap-0.5 px-6 text-[11px] ${isActive ? "text-accent-ink" : "text-muted"}`}
          >
            <Icon d={n.icon} />
            {n.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
