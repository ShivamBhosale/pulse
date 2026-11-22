import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { api, LOCKED_EVENT } from "../api/client";

/** Optional 4–6 digit passcode screen (only shown when a passcode is set on the server). */
export function PasscodeGate({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const session = useQuery({ queryKey: ["session"], queryFn: api.session, staleTime: Infinity });
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onLocked = () => void qc.invalidateQueries({ queryKey: ["session"] });
    window.addEventListener(LOCKED_EVENT, onLocked);
    return () => window.removeEventListener(LOCKED_EVENT, onLocked);
  }, [qc]);

  if (session.isPending) return null;
  if (!session.data || session.data.authenticated) return <>{children}</>;

  const submit = async (value: string) => {
    if (value.length < 4 || busy) return;
    setBusy(true);
    const result = await api.unlock(value);
    setBusy(false);
    if (result === "ok") {
      setCode("");
      setError(null);
      await qc.invalidateQueries();
    } else {
      setCode("");
      setError(result === "limited" ? "Too many attempts. Wait a minute." : "Wrong passcode.");
    }
  };

  const press = (k: string) => {
    setError(null);
    if (k === "del") return setCode((c) => c.slice(0, -1));
    if (k === "ok") return void submit(code);
    const next = (code + k).slice(0, 6);
    setCode(next);
    if (next.length === 6) void submit(next);
  };

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-8 px-6">
      <div className="text-center">
        <div className="text-lg font-semibold">Pulse is locked</div>
        <div className="text-sm text-muted">Enter your passcode</div>
      </div>
      <div className="flex gap-3" aria-live="polite" aria-label={`${code.length} digits entered`}>
        {Array.from({ length: 6 }, (_, i) => (
          <span key={i} className={`h-3 w-3 rounded-full border ${i < code.length ? "border-accent bg-accent" : "border-line"}`} />
        ))}
      </div>
      <div className="h-5 text-sm text-serious">{error}</div>
      <div className="grid grid-cols-3 gap-3">
        {["1", "2", "3", "4", "5", "6", "7", "8", "9", "del", "0", "ok"].map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => press(k)}
            disabled={busy}
            className="num card h-16 w-16 text-xl text-ink transition-colors hover:bg-surface-2 active:bg-surface-2"
            aria-label={k === "del" ? "Delete" : k === "ok" ? "Unlock" : k}
          >
            {k === "del" ? "⌫" : k === "ok" ? "→" : k}
          </button>
        ))}
      </div>
    </div>
  );
}
