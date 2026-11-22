import { useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useRefresh } from "../api/hooks";
import { fmtAgo } from "../lib/format";
import { useTheme } from "../lib/theme";

const NAV = [
  { to: "/", label: "Today", icon: "M3 12h4l3-8 4 16 3-8h4" },
  { to: "/sleep", label: "Sleep", icon: "M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" },
  { to: "/heart", label: "Heart", icon: "M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z" },
  { to: "/activity", label: "Activity", icon: "M13 4a1.5 1.5 0 1 0 0 .01M9 20l3-6 3 2v5M7 12l3-3 4 1 3 3" },
  { to: "/trends", label: "Trends", icon: "M4 19V5M4 19h16M8 15l3-4 3 2 5-6" },
  { to: "/records", label: "Records", icon: "M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4ZM7 6H4v2a3 3 0 0 0 3 3M17 6h3v2a3 3 0 0 1-3 3" },
  { to: "/settings", label: "Settings", icon: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3.9a7 7 0 0 0-2-1.2L14 3h-4l-.6 2.6a7 7 0 0 0-2 1.2l-2.3-.9-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-.9a7 7 0 0 0 2 1.2L10 21h4l.6-2.6a7 7 0 0 0 2-1.2l2.3.9 2-3.4-2-1.5c.1-.4.1-.8.1-1.2Z" },
];
const PRIMARY = NAV.slice(0, 4);
const MORE = NAV.slice(4);

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

function MobileNav() {
  const loc = useLocation();
  // Close the sheet whenever the route changes (keyed on pathname, no effect needed).
  const [openAt, setOpenAt] = useState<string | null>(null);
  const open = openAt === loc.pathname;
  const close = () => setOpenAt(null);
  const moreActive = MORE.some((n) => loc.pathname.startsWith(n.to));
  const item = (active: boolean) => `flex flex-col items-center gap-0.5 px-3 text-[11px] ${active ? "text-accent-ink" : "text-muted"}`;
  return (
    <>
      {open && (
        <div className="fixed inset-0 z-20 md:hidden" onClick={close}>
          <div className="absolute inset-0 bg-black/40" />
          <div id="more-sheet" role="dialog" aria-label="More pages" className="card absolute inset-x-3 bottom-[calc(max(env(safe-area-inset-bottom),8px)+64px)] p-2" onClick={(e) => e.stopPropagation()}>
            {MORE.map((n) => (
              <NavLink key={n.to} to={n.to} onClick={close} className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-3 text-sm ${isActive ? "bg-surface-2 text-ink" : "text-ink-2"}`}>
                <Icon d={n.icon} />
                {n.label}
              </NavLink>
            ))}
          </div>
        </div>
      )}
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-30 flex justify-around border-t border-line bg-surface/90 pb-[max(env(safe-area-inset-bottom),8px)] pt-2 backdrop-blur md:hidden">
        {PRIMARY.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => item(isActive)}>
            <Icon d={n.icon} />
            {n.label}
          </NavLink>
        ))}
        <button type="button" className={item(moreActive || open)} aria-expanded={open} aria-controls="more-sheet" onClick={() => setOpenAt(open ? null : loc.pathname)}>
          <Icon d="M5 12h.01M12 12h.01M19 12h.01" />
          More
        </button>
      </nav>
    </>
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
              end={n.to === "/"}
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
      <MobileNav />
    </div>
  );
}
