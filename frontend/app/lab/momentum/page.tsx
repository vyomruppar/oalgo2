"use client";

import { FactorIC, StrategyLab } from "@/components/Lab";
import { PageTitle, Tag } from "@/components/ui";

export default function Momentum() {
  return (
    <>
      <PageTitle title="Momentum and trend" sub="Strategies that follow strength: past winners, stocks in an uptrend with a market filter, moving-average crossovers, 52-week-high breakouts, and drift after earnings surprises." right={<Tag tone="warn">Backtested</Tag>} />
      <StrategyLab keys={["momentum", "trend", "earnings", "ma_cross", "breakout"]} />
      <FactorIC factors={["momentum", "earnings"]} initial="momentum" />
      <p className="note mt-3 max-w-3xl">Momentum results here are the most flattered by survivorship bias: the universe is today&apos;s most liquid stocks, which are disproportionately past winners.</p>
    </>
  );
}
