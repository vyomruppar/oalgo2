"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import useSWR from "swr";
import { fetcher, send, type J } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { Card, Tag } from "./ui";

const BUSY = ["downloading", "restarting"];

export function useUpdate() {
  const sawRestart = useRef(false);
  const { data, mutate, error } = useSWR<J>("/api/update/status", fetcher, {
    keepPreviousData: true,
    revalidateOnFocus: false,
    refreshInterval: (d) => (d?.job && BUSY.includes(d.job.state) ? 1500 : d?.restart_pending ? 1500 : 30 * 60 * 1000),
  });
  const state: string | undefined = data?.job?.state;
  useEffect(() => {
    if (state === "restarting") sawRestart.current = true;
  }, [state]);
  // After a restart the engine comes back with an idle job: reload to pick up the new dashboard.
  useEffect(() => {
    if (sawRestart.current && data?.enabled && state === "idle" && !error) window.location.reload();
  }, [data, state, error]);
  return { data, error, mutate, restarting: state === "restarting" || (sawRestart.current && Boolean(error)) };
}

const short = (sha?: string | null) => (sha ? sha.slice(0, 7) : "unknown");

export function UpdateDialog({ onClose }: { onClose: () => void }) {
  const { data, mutate, restarting } = useUpdate();
  const [err, setErr] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const job = data?.job ?? { state: "idle", percent: 0, message: "" };
  const busy = BUSY.includes(job.state) || restarting;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const start = async () => {
    setErr(null);
    try {
      await send("POST", "/api/update/install");
      mutate();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };
  const recheck = async () => {
    setChecking(true);
    try {
      mutate(await send("POST", "/api/update/check"), { revalidate: false });
    } finally {
      setChecking(false);
    }
  };

  // Rendered at the page root: the status bar's blur would otherwise become the dialog's frame of reference.
  if (typeof document === "undefined") return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg/80 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="upd-title" onClick={() => !busy && onClose()}>
      <div className="card w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <h2 id="upd-title" className="display text-[17px] font-medium">
          {busy ? "Updating oalgo2" : job.state === "error" ? "The update did not finish" : data?.update_available ? "A new version is ready" : "oalgo2 is up to date"}
        </h2>

        {busy ? (
          <div className="mt-4" aria-live="polite">
            <div className="h-1.5 rounded-sm bg-line">
              <div className="h-full rounded-sm bg-gradient-to-r from-accent to-up transition-[width] duration-500" style={{ width: `${restarting ? 100 : Math.max(4, job.percent)}%` }} />
            </div>
            <p className="mt-3 text-[13px]">{restarting ? "Installing the update and restarting" : job.message}</p>
            <p className="note mt-1">This window closes and reopens by itself in about 2 minutes. Your holdings, settings and scan history stay as they are. Please do not close it.</p>
          </div>
        ) : (
          <>
            {data?.error && <p className="mt-3 text-[12.5px] text-down">{data.error}</p>}
            {job.state === "error" && <p className="mt-3 text-[12.5px] text-down">{job.message}</p>}
            {err && <p className="mt-3 text-[12.5px] text-down">{err}</p>}
            {data?.update_available && (
              <div className="mt-3 text-[12.5px]">
                {data.unknown_installed && <p className="mb-2 text-dim">This copy came from a manual download, so its version is not recorded. Updating makes sure it is current.</p>}
                <div className="sub">What is new</div>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-dim">
                  {(data.changes ?? []).map((c: string, i: number) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
                <p className="note mt-2">
                  Newest version {short(data.latest_sha)}
                  {data.latest_date ? `, ${fmtDateTime(data.latest_date)}` : ""}. Your data is kept. oalgo2 restarts by itself.
                </p>
              </div>
            )}
            {!data?.update_available && !data?.error && <p className="mt-3 text-[12.5px] text-dim">You have the newest version ({short(data?.installed_sha)}).</p>}
            {data?.scan_running && data?.update_available && <p className="mt-3 text-[12.5px] text-warn">A scan is running. Wait for it to finish, then update.</p>}
            <div className="mt-5 flex items-center justify-end gap-2">
              <button className="btn" onClick={recheck} disabled={checking}>
                {checking ? "Checking" : "Check again"}
              </button>
              <button className="btn" onClick={onClose}>
                Not now
              </button>
              {data?.update_available && (
                <button className="btn btn-primary" onClick={start} disabled={data?.scan_running}>
                  {job.state === "error" ? "Try again" : "Update now"}
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}

/** Status-bar chip: shows only when a newer version exists. */
export function UpdateChip() {
  const { data } = useUpdate();
  const [open, setOpen] = useState(false);
  if (!data?.enabled) return null;
  const busy = data.job && BUSY.includes(data.job.state);
  if (!data.update_available && !busy && !open) return null;
  return (
    <>
      <button type="button" className="chip border-accent/60 bg-accent/15 text-ink hover:bg-accent/30" onClick={() => setOpen(true)}>
        {busy ? "Updating" : "Update available"}
      </button>
      {(open || busy) && <UpdateDialog onClose={() => setOpen(false)} />}
    </>
  );
}

/** Card for the Scans and data page: version, check now, update. */
export function UpdateCard() {
  const { data } = useUpdate();
  const [open, setOpen] = useState(false);
  if (!data?.enabled) return null;
  return (
    <Card title="Software updates" className="mt-3" right={data.update_available ? <Tag tone="accent">Update available</Tag> : <Tag tone="up">Up to date</Tag>}>
      <div className="flex flex-wrap items-center justify-between gap-3 text-[12.5px]">
        <div>
          <div>
            Installed version <span className="num">{short(data.installed_sha)}</span>
            {data.installed_at ? <span className="text-faint"> · updated {fmtDateTime(data.installed_at)}</span> : <span className="text-faint"> · from a manual download</span>}
          </div>
          <div className="text-dim">
            {data.error ? data.error : data.update_available ? `Newest: ${data.latest_message}` : "You have the newest version."} <span className="text-faint">Checked {fmtDateTime(data.checked_at)}</span>
          </div>
        </div>
        <button className="btn btn-primary" onClick={() => setOpen(true)}>
          {data.update_available ? "Update now" : "Check for updates"}
        </button>
      </div>
      {open && <UpdateDialog onClose={() => setOpen(false)} />}
    </Card>
  );
}
