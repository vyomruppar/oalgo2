"use client";

import { FactorCorrelation, FactorIC, StrategyLab } from "@/components/Lab";
import { PageTitle, Tag } from "@/components/ui";

export default function Factors() {
  return (
    <>
      <PageTitle title="Factors" sub="Characteristics with a documented link to returns: cheapness, profitability, conservative investment, size, and the composite that blends them. Each is ranked within the screened universe and tested on its own." right={<Tag tone="warn">Backtested</Tag>} />
      <StrategyLab keys={["multifactor", "value", "quality", "investment"]} />
      <FactorIC factors={["value", "quality", "investment", "size", "financial_strength"]} initial="quality" />
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <FactorCorrelation />
      </div>
    </>
  );
}
