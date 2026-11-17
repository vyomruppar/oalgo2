"use client";

import { useEffect, useRef } from "react";

/**
 * Fixed deep-space backdrop: two soft nebula clouds (CSS) and three depth layers of stars (canvas)
 * that drift slowly and shift slightly with the pointer. Purely decorative and never behind numbers
 * at full strength: panels are translucent glass on top of it. Static under prefers-reduced-motion.
 */
export default function Backdrop() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0;
    let h = 0;
    let raf = 0;
    let px = 0;
    let py = 0;
    let tx = 0;
    let ty = 0;
    type Star = { x: number; y: number; r: number; a: number; layer: number; tw: number; hue: number };
    let stars: Star[] = [];

    const seed = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = Math.min(520, Math.round((w * h) / 4200));
      let s = 1234567;
      const rnd = () => ((s = (s * 1664525 + 1013904223) % 4294967296) / 4294967296);
      stars = Array.from({ length: n }, () => {
        const layer = rnd() < 0.6 ? 0 : rnd() < 0.7 ? 1 : 2;
        return { x: rnd() * w, y: rnd() * h, r: 0.35 + layer * 0.35 + rnd() * 0.5, a: 0.25 + rnd() * 0.55, layer, tw: rnd() * Math.PI * 2, hue: rnd() };
      });
    };

    const draw = (t: number) => {
      px += (tx - px) * 0.04;
      py += (ty - py) * 0.04;
      ctx.clearRect(0, 0, w, h);
      for (const s of stars) {
        const depth = (s.layer + 1) * 6;
        const drift = reduce ? 0 : (t / 1000) * (0.6 + s.layer * 0.9);
        const x = (((s.x + drift - px * depth) % w) + w) % w;
        const y = (((s.y - py * depth) % h) + h) % h;
        const twinkle = reduce ? 1 : 0.75 + 0.25 * Math.sin(t / 900 + s.tw);
        ctx.globalAlpha = s.a * twinkle;
        ctx.fillStyle = s.hue < 0.12 ? "#b9a8ff" : s.hue < 0.2 ? "#9df3e2" : "#e8ebff";
        ctx.beginPath();
        ctx.arc(x, y, s.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      if (!reduce) raf = requestAnimationFrame(draw);
    };

    const onMove = (e: PointerEvent) => {
      tx = e.clientX / w - 0.5;
      ty = e.clientY / h - 0.5;
    };
    const onResize = () => {
      seed();
      if (reduce) draw(0);
    };
    const onVis = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden && !reduce) raf = requestAnimationFrame(draw);
    };

    seed();
    raf = requestAnimationFrame(draw);
    window.addEventListener("resize", onResize);
    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(60% 50% at 78% 8%, rgba(139,124,255,0.22), transparent 70%), radial-gradient(45% 40% at 12% 85%, rgba(61,242,196,0.10), transparent 70%), radial-gradient(40% 35% at 55% 55%, rgba(214,92,255,0.07), transparent 70%), linear-gradient(180deg, #060818 0%, #080a22 55%, #05061a 100%)",
        }}
      />
      <canvas ref={ref} className="absolute inset-0 h-full w-full" />
    </div>
  );
}
