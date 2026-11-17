"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fmtCompact, fmtMoney, fmtPct, signalStyle } from "@/lib/format";
import { layoutStars, nearestStar, SIGNAL_COLOR, type Star, type StarInput } from "@/lib/starmap";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "held", label: "Owned" },
  { key: "buy", label: "Buy" },
  { key: "watch", label: "Watchlist" },
  { key: "sell", label: "Sell" },
] as const;
type FilterKey = (typeof FILTERS)[number]["key"];

function matches(s: Star, f: FilterKey, q: string, sector: string | null): boolean {
  if (sector && s.sector !== sector) return false;
  if (q && !s.symbol.toLowerCase().startsWith(q) && !(s.company ?? "").toLowerCase().includes(q)) return false;
  if (f === "held") return s.held;
  if (f === "buy") return s.signal === "BUY" || s.signal === "STRONG BUY";
  if (f === "watch") return s.signal === "WATCHLIST";
  if (f === "sell") return s.signal === "SELL";
  return true;
}

/**
 * The scanned universe drawn as a galaxy. Each star is a stock; hover for details, click to open its
 * research page, scroll to zoom, drag to pan. Stocks the user owns carry an orbit ring and a label.
 */
export default function StarMap({ stars: input, height = 520 }: { stars: StarInput[]; height?: number }) {
  const router = useRouter();
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(900);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [query, setQuery] = useState("");
  const [sector, setSector] = useState<string | null>(null);
  const [hover, setHover] = useState<{ star: Star; x: number; y: number } | null>(null);
  const view = useRef({ k: 1, tx: 0, ty: 0 });
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const hoverIdx = useRef(-1);
  const intro = useRef(0);
  const state = useRef({ filter, query, sector });
  state.current = { filter, query: query.trim().toLowerCase(), sector };

  const { stars, arms } = useMemo(() => layoutStars(input, width, height), [input, width, height]);

  useEffect(() => {
    if (!wrap.current) return;
    const ro = new ResizeObserver((e) => setWidth(Math.max(320, Math.round(e[0].contentRect.width))));
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);

  // one draw loop; everything it needs is read from refs so it never restarts on hover
  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    c.width = width * dpr;
    c.height = height * dpr;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const start = performance.now();
    intro.current = reduce ? 1 : 0;
    let raf = 0;
    const cx = width / 2;
    const cy = height / 2;

    const draw = (now: number) => {
      const t = (now - start) / 1000;
      if (!reduce) intro.current = Math.min(1, t / 1.8);
      const ease = 1 - Math.pow(1 - intro.current, 3);
      const { k, tx, ty } = view.current;
      const f = state.current;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      // galactic core glow
      const g = ctx.createRadialGradient(cx * k + tx, cy * k + ty, 0, cx * k + tx, cy * k + ty, Math.min(width, height) * 0.55 * k);
      g.addColorStop(0, `rgba(170,150,255,${0.26 * ease})`);
      g.addColorStop(0.35, `rgba(120,90,255,${0.1 * ease})`);
      g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, width, height);

      ctx.save();
      ctx.translate(tx, ty);
      ctx.scale(k, k);
      const placed: [number, number, number, number][] = [];
      // returns a label position that does not collide with labels already drawn (tries four sides)
      const place = (sx: number, sy: number, off: number, text: string, size: number): [number, number] | null => {
        const w = text.length * size * 0.62;
        const h = size * 1.2;
        const tries: [number, number][] = [[sx + off, sy + size * 0.35], [sx - off - w, sy + size * 0.35], [sx - w / 2, sy - off - 2 / k], [sx - w / 2, sy + off + h]];
        for (const [x, y] of tries) {
          const box: [number, number, number, number] = [x, y - h, x + w, y];
          if (!placed.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) {
            placed.push(box);
            return [x, y];
          }
        }
        return null;
      };
      for (let i = 0; i < stars.length; i++) {
        const s = stars[i];
        const on = matches(s, f.filter, f.query, f.sector);
        // intro: stars fly in from a scattered position along their arm
        const sx = cx + (s.x - cx) * (0.15 + 0.85 * ease) * (1 + (1 - ease) * Math.sin(i * 12.9898) * 1.4);
        const sy = cy + (s.y - cy) * (0.15 + 0.85 * ease) * (1 + (1 - ease) * Math.cos(i * 78.233) * 1.4);
        const tw = reduce ? 1 : 0.82 + 0.18 * Math.sin(t * 1.6 + i * 1.7);
        const a = (on ? s.alpha : 0.07) * tw * ease;
        const hovered = i === hoverIdx.current;
        const r = (s.r * (hovered ? 1.7 : 1)) / Math.sqrt(k);
        if (on && (s.alpha > 0.7 || s.held || hovered)) {
          const glow = ctx.createRadialGradient(sx, sy, 0, sx, sy, r * 5);
          glow.addColorStop(0, s.color + "66");
          glow.addColorStop(1, s.color + "00");
          ctx.globalAlpha = a;
          ctx.fillStyle = glow;
          ctx.beginPath();
          ctx.arc(sx, sy, r * 5, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.globalAlpha = a;
        ctx.fillStyle = s.color;
        ctx.beginPath();
        ctx.arc(sx, sy, r, 0, Math.PI * 2);
        ctx.fill();
        if (s.held && on) {
          // orbit ring: owned stocks are the bodies you circle
          const rr = r + 6 / k + (reduce ? 0 : Math.sin(t * 2 + i) * 0.8);
          ctx.globalAlpha = 0.9 * ease;
          ctx.strokeStyle = "#e8ebff";
          ctx.lineWidth = 1 / k;
          ctx.beginPath();
          ctx.arc(sx, sy, rr, 0, Math.PI * 2);
          ctx.stroke();
          const oa = reduce ? 0.8 : t * 0.9 + i;
          ctx.fillStyle = "#e8ebff";
          ctx.beginPath();
          ctx.arc(sx + rr * Math.cos(oa), sy + rr * Math.sin(oa), 1.4 / k, 0, Math.PI * 2);
          ctx.fill();
          ctx.font = `600 ${11 / k}px "Hanken Grotesk Variable", sans-serif`;
          ctx.globalAlpha = ease;
          const at = place(sx, sy, rr + 4 / k, s.symbol, 11 / k);
          if (at) ctx.fillText(s.symbol, at[0], at[1]);
        } else if (hovered || (on && (f.query || f.filter !== "all" || k > 1.9) && (s.alpha > 0.5 || f.filter !== "all"))) {
          ctx.font = `500 ${10.5 / k}px "Hanken Grotesk Variable", sans-serif`;
          ctx.globalAlpha = hovered ? 1 : 0.75 * ease;
          ctx.fillStyle = "#e8ebff";
          const at = place(sx, sy, r + 4 / k, s.symbol, 10.5 / k);
          if (at || hovered) ctx.fillText(s.symbol, at ? at[0] : sx + r + 4 / k, at ? at[1] : sy + 3.5 / k);
        }
      }
      // sector names at the end of each arm
      ctx.textAlign = "center";
      for (const arm of arms) {
        const dim = f.sector && f.sector !== arm.sector;
        ctx.globalAlpha = (dim ? 0.25 : 0.7) * ease;
        ctx.fillStyle = f.sector === arm.sector ? "#e8ebff" : "#a0a8d6";
        ctx.font = `500 ${10.5 / k}px "Hanken Grotesk Variable", sans-serif`;
        ctx.fillText(arm.sector, Math.max(60, Math.min(width - 60, arm.lx)), Math.max(14, Math.min(height - 8, arm.ly)));
      }
      ctx.textAlign = "start";
      ctx.restore();
      ctx.globalAlpha = 1;
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    const onVis = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden) raf = requestAnimationFrame(draw);
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [stars, arms, width, height]);

  const toWorld = useCallback((e: { clientX: number; clientY: number }) => {
    const rect = canvas.current!.getBoundingClientRect();
    const { k, tx, ty } = view.current;
    return { mx: e.clientX - rect.left, my: e.clientY - rect.top, x: (e.clientX - rect.left - tx) / k, y: (e.clientY - rect.top - ty) / k };
  }, []);

  const pick = useCallback(
    (e: { clientX: number; clientY: number }) => {
      const p = toWorld(e);
      const f = state.current;
      const visible = stars.filter((s) => matches(s, f.filter, f.query, f.sector));
      const j = nearestStar(visible, p.x, p.y, 16 / view.current.k);
      return { p, star: j >= 0 ? visible[j] : null };
    },
    [stars, toWorld],
  );

  const onMove = (e: React.PointerEvent) => {
    if (drag.current) {
      const dx = e.clientX - drag.current.x;
      const dy = e.clientY - drag.current.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) drag.current.moved = true;
      view.current.tx += dx;
      view.current.ty += dy;
      drag.current.x = e.clientX;
      drag.current.y = e.clientY;
      setHover(null);
      return;
    }
    const { p, star } = pick(e);
    hoverIdx.current = star ? stars.indexOf(star) : -1;
    setHover(star ? { star, x: p.mx, y: p.my } : null);
  };

  const onWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    const rect = canvas.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const v = view.current;
    const k = Math.max(1, Math.min(6, v.k * Math.exp(-e.deltaY * 0.0015)));
    v.tx = mx - ((mx - v.tx) / v.k) * k;
    v.ty = my - ((my - v.ty) / v.k) * k;
    v.k = k;
    if (k === 1) v.tx = v.ty = 0;
  }, []);

  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    c.addEventListener("wheel", onWheel, { passive: false });
    return () => c.removeEventListener("wheel", onWheel);
  }, [onWheel]);

  const reset = () => {
    view.current = { k: 1, tx: 0, ty: 0 };
    setSector(null);
    setFilter("all");
    setQuery("");
  };

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: stars.length, held: 0, buy: 0, watch: 0, sell: 0 };
    for (const s of stars) {
      if (s.held) c.held++;
      if (s.signal === "BUY" || s.signal === "STRONG BUY") c.buy++;
      if (s.signal === "WATCHLIST") c.watch++;
      if (s.signal === "SELL") c.sell++;
    }
    return c;
  }, [stars]);

  const h = hover?.star;
  return (
    <div ref={wrap} className="relative select-none" style={{ height }}>
      <canvas
        ref={canvas}
        style={{ width: "100%", height, cursor: hover ? "pointer" : drag.current ? "grabbing" : "grab", touchAction: "none" }}
        role="img"
        aria-label={`Map of ${stars.length} scanned stocks arranged by sector. ${counts.held} owned, ${counts.buy} rated buy, ${counts.sell} rated sell. Use the stock explorer for a keyboard-accessible list.`}
        onPointerMove={onMove}
        onPointerDown={(e) => {
          drag.current = { x: e.clientX, y: e.clientY, moved: false };
          (e.target as Element).setPointerCapture(e.pointerId);
        }}
        onPointerUp={(e) => {
          const moved = drag.current?.moved;
          drag.current = null;
          if (!moved) {
            const { star } = pick(e);
            if (star) router.push(`/stocks/${star.symbol}`);
          }
        }}
        onPointerLeave={() => {
          hoverIdx.current = -1;
          setHover(null);
          drag.current = null;
        }}
      />

      <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-end p-3">
        <div className="pointer-events-auto flex max-w-full flex-wrap items-center justify-end gap-2 lg:max-w-[62%]">
          <div className="seg">
            {FILTERS.map((f) => (
              <button key={f.key} type="button" data-on={filter === f.key} onClick={() => setFilter(f.key)}>
                {f.label} <span className="num opacity-60">{counts[f.key]}</span>
              </button>
            ))}
          </div>
          <input className="input w-36 bg-bg/60" placeholder="Find a stock" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Find a stock on the map" />
          <select className="input bg-bg/60" value={sector ?? ""} onChange={(e) => setSector(e.target.value || null)} aria-label="Highlight a sector">
            <option value="">All sectors</option>
            {arms.map((a) => (
              <option key={a.sector} value={a.sector}>
                {a.sector} ({a.count})
              </option>
            ))}
          </select>
          <button type="button" className="btn" onClick={reset}>
            Reset view
          </button>
        </div>
      </div>

      <div className="pointer-events-none absolute bottom-2 left-3 right-3 flex flex-wrap items-end justify-between gap-x-4 gap-y-1 text-[11px] text-faint">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {[["Buy", SIGNAL_COLOR.BUY], ["Watchlist", SIGNAL_COLOR.WATCHLIST], ["Hold", SIGNAL_COLOR.HOLD], ["Sell", SIGNAL_COLOR.SELL], ["Screened out", SIGNAL_COLOR.NONE]].map(([l, c]) => (
            <span key={l} className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full" style={{ background: c }} />
              {l}
            </span>
          ))}
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full border border-ink" />
            You own it
          </span>
        </div>
        <span className="hidden md:inline">Each arm is a sector. Larger companies sit nearer the core and higher scores shine brighter. Scroll to zoom, drag to pan, click to open.</span>
      </div>

      {h && hover && (
        <div className="pointer-events-none absolute z-10 w-60 rounded-xl border border-line/70 bg-panel/95 p-3 text-[12px] shadow-2xl backdrop-blur" style={{ left: Math.min(hover.x + 14, width - 250), top: Math.max(8, Math.min(hover.y + 14, height - 150)) }}>
          <div className="flex items-center justify-between gap-2">
            <span className="text-[14px] font-semibold">{h.symbol}</span>
            <span className={`chip ${signalStyle(h.signal).cls}`}>{signalStyle(h.signal).label}</span>
          </div>
          <div className="truncate text-dim">{(h.company ?? "").replace(/ - .*$| Common Stock.*$/i, "")}</div>
          <dl className="num mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5">
            <dt className="text-faint">Score</dt>
            <dd className="text-right">{h.score == null ? "not scored" : h.score.toFixed(0)}</dd>
            <dt className="text-faint">Price</dt>
            <dd className="text-right">{fmtMoney(h.price)}</dd>
            <dt className="text-faint">Last session</dt>
            <dd className={`text-right ${h.ret_1d == null ? "" : h.ret_1d >= 0 ? "text-up" : "text-down"}`}>{fmtPct(h.ret_1d, 2, true)}</dd>
            <dt className="text-faint">Market cap</dt>
            <dd className="text-right">{fmtCompact(h.market_cap, "$")}</dd>
            <dt className="text-faint">Sector</dt>
            <dd className="truncate text-right">{h.sector}</dd>
          </dl>
          {h.held && <div className="mt-1.5 text-accent">In your portfolio</div>}
        </div>
      )}
    </div>
  );
}
