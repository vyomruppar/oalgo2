"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import EChart, { C, baseOption, catAxis, valueAxis } from "@/components/EChart";
import NewsFeed from "@/components/NewsFeed";
import { Banner, Card, Empty, Loading, PageTitle, Seg, useApi } from "@/components/ui";
import type { J } from "@/lib/api";

export default function News() {
  const router = useRouter();
  const [scope, setScope] = useState<"holdings" | "all">("holdings");
  const [strict, setStrict] = useState(false);
  const { data } = useApi(`/api/news?scope=${scope}&limit=1`, 300000);

  const tone = useMemo(() => {
    const s: Record<string, J> = data?.sentiment ?? {};
    const rows = Object.entries(s).filter(([, v]) => v.score != null && v.n >= 2).sort((a, b) => a[1].score - b[1].score).slice(-30);
    if (!rows.length) return null;
    return baseOption({
      grid: { left: 64, right: 40, top: 8, bottom: 30 },
      legend: { show: false },
      tooltip: { trigger: "item", formatter: (p: J) => { const v = rows[p.dataIndex][1]; return `<b>${rows[p.dataIndex][0]}</b><br/>tone ${v.score >= 0 ? "+" : ""}${v.score.toFixed(2)} from ${v.n} headlines<br/>${v.counts.positive} positive · ${v.counts.neutral} neutral · ${v.counts.negative} negative`; } },
      xAxis: valueAxis({ min: -1, max: 1, scale: false, name: "Weighted headline tone", nameLocation: "middle", nameGap: 20, nameTextStyle: { color: C.faint, fontSize: 11 } }),
      yAxis: catAxis(rows.map(([k]) => k), { axisLine: { show: false }, axisLabel: { color: C.dim, fontSize: 11, interval: 0 } }),
      series: [{ type: "bar", barWidth: 10, data: rows.map(([k, v]) => ({ name: k, value: +v.score.toFixed(3), itemStyle: { color: v.score >= 0.15 ? C.up : v.score <= -0.15 ? C.down : C.dim, borderRadius: 3 } })), label: { show: true, position: "right", color: C.faint, fontSize: 10.5, formatter: (p: J) => `${rows[p.dataIndex][1].n}` } }],
    });
  }, [data]);

  return (
    <>
      <PageTitle title="News and sentiment" sub="Recent headlines for the stocks you own and for buy and watchlist names, each scored for tone. Recent and directly relevant headlines count for more in each stock's average." right={<Seg options={["holdings", "all"] as const} value={scope} onChange={setScope} labels={{ holdings: "My holdings", all: "Everything stored" }} />} />
      {data?.engine && !data.engine.is_ai && <Banner tone="info">{data.engine.note ?? "Headlines are being scored with the built-in word list."} The word list is a simple statistical method; install the local FinBERT model for AI scoring.</Banner>}
      <div className="mt-3 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
        <Card title="Tone by stock">
          {!data ? <Loading /> : tone ? <EChart option={tone} height={Math.max(220, Object.keys(data.sentiment).length * 22 + 50)} onClick={(p) => typeof p.name === "string" && p.name && router.push(`/stocks/${p.name}`)} /> : <Empty title="Not enough headlines yet">A stock needs at least two scored headlines to appear here.</Empty>}
          <p className="note mt-1">The number beside each bar is how many headlines were scored. Click a bar to open the stock. Tone is not used in the research score unless you give it a weight in Settings, because it has no test history yet.</p>
        </Card>
        <Card title="Headlines" right={<label className="flex cursor-pointer items-center gap-1.5 text-[12px] text-dim"><input type="checkbox" checked={strict} onChange={(e) => setStrict(e.target.checked)} className="accent-[#8b7cff]" /> Only stories about the company itself</label>}>
          <NewsFeed scope={scope} limit={40} minRelevance={strict ? 0.9 : 0} />
        </Card>
      </div>
    </>
  );
}
