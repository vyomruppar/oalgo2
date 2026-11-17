"use client";

import Link from "next/link";
import { useState } from "react";
import { Card, Empty, ErrorBox, KV, Loading, PageTitle, Seg, SignalChip, SymbolLink, Tag, useApi } from "@/components/ui";
import { send, type J } from "@/lib/api";
import { fmtCompact, fmtDateTime, fmtMoney, fmtNum, fmtPct, timeAgo } from "@/lib/format";
import { useLive } from "@/lib/live";

const KINDS = ["all", "signal", "score_change", "risk", "exit_condition", "unusual_volume", "unusual_volatility", "filing", "regime_change", "provider_failure"] as const;
const KIND_LABEL: Record<string, string> = {
  all: "All", signal: "Signals", score_change: "Score changes", risk: "Risk", exit_condition: "Exit conditions", unusual_volume: "Volume", unusual_volatility: "Volatility",
  filing: "Filings", regime_change: "Regime", provider_failure: "Data providers", provider_recovered: "Data providers", scan_failure: "Scan failures",
};
const SEV: Record<string, "dim" | "accent" | "warn" | "down"> = { info: "dim", medium: "accent", high: "warn", critical: "down" };

function Detail({ a }: { a: J }) {
  const p = a.payload ?? {};
  const has = p.entry_conditions || p.exit_conditions || p.risk || p.red_flags?.length;
  if (!has && !p.components) return <p className="note">{a.message}</p>;
  return (
    <div className="grid gap-x-8 gap-y-3 text-[12px] md:grid-cols-3">
      <div>
        <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-faint">Supporting evidence</div>
        {p.reasons?.length ? <ul className="list-disc space-y-0.5 pl-4 text-dim">{p.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul> : <p className="text-faint">{a.message}</p>}
        {p.red_flags?.length > 0 && <ul className="mt-2 list-disc space-y-0.5 pl-4 text-down">{p.red_flags.map((r: J) => <li key={r.code}>{r.text}</li>)}</ul>}
      </div>
      <div>
        <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-faint">Entry and exit conditions</div>
        {p.entry_conditions?.length ? <ul className="list-disc space-y-0.5 pl-4 text-dim">{p.entry_conditions.map((r: string) => <li key={r}>{r}</li>)}</ul> : <p className="text-faint">No entry suggested.</p>}
        {p.exit_conditions?.length > 0 && <ul className="mt-2 list-disc space-y-0.5 pl-4 text-dim">{p.exit_conditions.map((r: string) => <li key={r}>{r}</li>)}</ul>}
      </div>
      <div>
        <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-faint">Risk assessment</div>
        {p.risk ? (
          <KV rows={[
            ["Volatility, 1 year", fmtPct(p.risk.volatility_1y, 0)],
            ["Worst drawdown, 1 year", fmtPct(p.risk.max_drawdown_1y)],
            ["Stop reference", p.risk.stop_reference ? `${fmtMoney(p.risk.stop_reference)} (${fmtPct(p.risk.stop_distance_pct)})` : "—"],
            ["Avg daily dollar volume", fmtCompact(p.risk.adv_dollar_63, "$")],
            ["Data quality", p.data_quality ?? "—"],
          ]} />
        ) : <p className="text-faint">Not applicable to this alert.</p>}
      </div>
    </div>
  );
}

export default function Alerts() {
  const [kind, setKind] = useState<(typeof KINDS)[number]>("all");
  const [unread, setUnread] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const { notifications, enableNotifications } = useLive();
  const q = new URLSearchParams({ limit: "300" });
  if (kind !== "all") q.set("kind", kind);
  if (unread) q.set("unread", "true");
  const { data, error, mutate } = useApi(`/api/alerts?${q}`, 30000);
  const cfg = useApi("/api/config");

  const markAll = async () => {
    await send("POST", "/api/alerts/read");
    mutate();
  };
  const toggle = async (a: J) => {
    setOpen(open === a.id ? null : a.id);
    if (!a.read) {
      await send("POST", `/api/alerts/read?alert_id=${a.id}`);
      mutate();
    }
  };

  return (
    <>
      <PageTitle
        title="Alerts"
        sub="An alert is raised only when something changes: a new or changed signal, a score move, a new risk flag, an exit condition on a held position, unusual volume or volatility, a new filing, a regime change, or a failing data provider. The same condition seen again on the next scan does not repeat."
        right={
          <div className="flex items-center gap-2">
            {notifications === "granted" ? <Tag tone="up">Desktop notifications on</Tag> : notifications === "unsupported" ? <Tag>Desktop notifications unsupported</Tag> : notifications === "denied" ? <Tag tone="down">Blocked in browser settings</Tag> : <button className="btn" onClick={enableNotifications}>Enable desktop notifications</button>}
            <button className="btn" onClick={markAll} disabled={!data?.unread}>Mark all read</button>
          </div>
        }
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Seg options={KINDS} value={kind} onChange={setKind} labels={KIND_LABEL} />
        <label className="flex cursor-pointer items-center gap-1.5 text-[12px] text-dim"><input type="checkbox" checked={unread} onChange={(e) => setUnread(e.target.checked)} className="accent-[#d6a85c]" /> Unread only</label>
        <span className="note ml-auto">{data ? `${data.unread} unread` : ""} · e-mail delivery {cfg.data?.email_configured ? "configured" : "not configured (set OALGO_SMTP_* to enable)"}</span>
      </div>
      <Card pad={false}>
        {error && !data ? <ErrorBox error={error} /> : !data ? <Loading rows={6} /> : data.items.length === 0 ? (
          <Empty title="No alerts">{kind === "all" && !unread ? "Alerts appear after scans detect a meaningful change." : "Nothing matches this filter."}</Empty>
        ) : (
          <ul>
            {data.items.map((a: J) => {
              const p = a.payload ?? {};
              return (
                <li key={a.id} className={`border-b border-line/60 last:border-0 ${a.read ? "" : "bg-raised/40"}`}>
                  <button type="button" onClick={() => toggle(a)} aria-expanded={open === a.id} className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5 text-left hover:bg-raised/60">
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${a.read ? "bg-transparent" : "bg-accent"}`} aria-label={a.read ? "read" : "unread"} />
                    <span className="num w-28 shrink-0 text-[11.5px] text-faint" title={fmtDateTime(a.created_at)}>{fmtDateTime(a.created_at)}</span>
                    <Tag tone={SEV[a.severity] ?? "dim"}>{KIND_LABEL[a.kind] ?? a.kind}</Tag>
                    <span className="min-w-0 flex-1 truncate text-[12.5px]">{a.title}</span>
                    {p.signal && <SignalChip signal={p.signal} />}
                    {p.score != null && <span className="num text-[12px] text-dim">score {fmtNum(p.score, 0)}</span>}
                    {p.price != null && <span className="num text-[12px] text-dim">{fmtMoney(p.price)} <span className="text-faint">{p.price_date}</span></span>}
                    <span className="text-[11px] text-faint">{timeAgo(a.created_at)}</span>
                  </button>
                  {open === a.id && (
                    <div className="border-t border-line/60 bg-bg/40 px-4 py-3">
                      <Detail a={a} />
                      <div className="mt-3 flex items-center gap-4 text-[12px]">
                        {a.symbol && <span>Full research report: <SymbolLink symbol={a.symbol} /></span>}
                        {p.url && <a href={p.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">Open filing on SEC EDGAR</a>}
                        {a.kind.startsWith("provider") && <Link href="/settings" className="text-accent hover:underline">Data provider details</Link>}
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </>
  );
}
