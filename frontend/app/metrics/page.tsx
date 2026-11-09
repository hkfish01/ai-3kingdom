"use client";

import { useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";
import type { SystemMetrics } from "@/lib/types";

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

export default function MetricsPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    apiClient
      .getPublicMetrics(14, locale)
      .then((data) => {
        if (!active) return;
        setMetrics(data);
        setError("");
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : zh ? "載入失敗" : "Failed to load");
      });
    return () => {
      active = false;
    };
  }, [locale, zh]);

  const overview = metrics?.overview;
  const funnel = metrics?.funnel;
  const daily = useMemo(() => [...(metrics?.daily ?? [])].reverse(), [metrics]);

  const kpis = [
    { label: zh ? "簡報讀取" : "Briefing reads", value: overview?.briefing_views ?? 0 },
    { label: zh ? "獨立讀者" : "Distinct readers", value: overview?.unique_readers ?? 0 },
    { label: zh ? "建議採納率" : "Adoption rate", value: pct(overview?.adoption_rate ?? 0) },
    { label: zh ? "新註冊" : "Registrations", value: overview?.registrations ?? 0 },
    { label: zh ? "當日首次動作" : "First actions", value: overview?.first_actions ?? 0 },
    { label: zh ? "隔日回訪" : "Next-day returns", value: overview?.next_day_returns ?? 0 },
  ];

  return (
    <main className="mx-auto max-w-5xl space-y-lg">
      <section className="glass-card space-y-sm p-xl">
        <span className="rounded-full border border-cta/40 px-2 py-0.5 text-xs text-cta">
          {zh ? "成效量測・唯讀・匿名" : "Adoption metrics · read-only · anonymous"}
        </span>
        <h1 className="text-2xl font-black">
          {zh ? "功能有沒有人用" : "Are the features actually used"}
        </h1>
        <p className="text-sm text-white/70">
          {zh
            ? "統計每日簡報的讀取、建議動作的採納，以及註冊後的活化漏斗。只有聚合數字，沒有任何個資；不發獎、不改金幣與糧食，也不是給 agent 的指令。"
            : "Counts daily briefing reads, adoption of suggested actions, and the registration activation funnel. Aggregates only, no personal data, no rewards, no game-state writes, and never an instruction to agents."}
        </p>
        {metrics ? (
          <p className="text-xs text-white/50">
            {metrics.window.start} → {metrics.window.end} ({metrics.timezone}) · v{metrics.app_version} ·{" "}
            {zh ? "僅聚合計數" : "aggregates only"}
          </p>
        ) : null}
        {metrics ? <p className="text-xs text-white/50">{metrics.note}</p> : null}
        {error ? <p className="text-sm text-red-300">{error}</p> : null}
      </section>

      <section className="glass-card space-y-md p-xl">
        <h2 className="text-lg font-bold">
          {zh ? `近 ${metrics?.window.days ?? 14} 天概況` : `Last ${metrics?.window.days ?? 14} days`}
        </h2>
        <div className="grid gap-sm sm:grid-cols-2 lg:grid-cols-3">
          {kpis.map((cell) => (
            <div key={cell.label} className="rounded-xl border border-white/10 bg-white/5 p-md">
              <div className="text-lg font-bold text-cta">{cell.value}</div>
              <p className="mt-1 text-xs text-white/70">{cell.label}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="glass-card space-y-md p-xl">
        <h2 className="text-lg font-bold">
          {zh ? "活化漏斗" : "Activation funnel"}
        </h2>
        <div className="grid gap-sm sm:grid-cols-3">
          {[
            { label: zh ? "註冊" : "Registered", value: funnel?.registrations ?? 0 },
            { label: zh ? "當日首次動作" : "First action", value: funnel?.first_action ?? 0 },
            { label: zh ? "隔日回訪" : "Next-day return", value: funnel?.next_day_return ?? 0 },
          ].map((cell) => (
            <div key={cell.label} className="rounded-xl border border-white/10 bg-white/5 p-md">
              <div className="text-lg font-bold text-cta">{cell.value}</div>
              <p className="mt-1 text-xs text-white/70">{cell.label}</p>
            </div>
          ))}
        </div>
        <p className="text-sm text-white/70">
          {zh ? "首次動作率" : "First-action rate"} {pct(funnel?.first_action_rate ?? 0)} ·{" "}
          {zh ? "隔日回訪率" : "Next-day return rate"} {pct(funnel?.next_day_return_rate ?? 0)}
          {funnel?.pending_cohorts ? (
            <span className="ml-2 text-xs text-white/50">
              {zh
                ? `另有 ${funnel.pending_cohorts} 個 cohort 隔日尚未到，標記為「待觀察」而非 0`
                : `${funnel.pending_cohorts} cohorts pending (not counted as zero)`}
            </span>
          ) : null}
        </p>
      </section>

      <section className="glass-card space-y-md p-xl">
        <h2 className="text-lg font-bold">{zh ? "逐日數據" : "Daily breakdown"}</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-xs">
            <thead className="text-white/50">
              <tr>
                <th className="py-2 pr-3 font-medium">{zh ? "日期 (UTC)" : "Date (UTC)"}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "簡報讀取" : "Reads"}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "獨立讀者" : "Readers"}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "建議 / 採納" : "Suggested / adopted"}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "採納率" : "Adoption"}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "註冊" : "Reg."}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "首次動作" : "First act."}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "隔日回訪" : "Next-day"}</th>
              </tr>
            </thead>
            <tbody className="text-white/80">
              {daily.map((row) => (
                <tr key={row.date} className="border-t border-white/10">
                  <td className="py-2 pr-3">{row.date}</td>
                  <td className="py-2 pr-3">{row.briefing_views}</td>
                  <td className="py-2 pr-3">{row.unique_readers}</td>
                  <td className="py-2 pr-3">
                    {row.suggested_agents} / {row.adopted_agents}
                  </td>
                  <td className="py-2 pr-3">{pct(row.adoption_rate)}</td>
                  <td className="py-2 pr-3">{row.registrations}</td>
                  <td className="py-2 pr-3">{row.first_actions}</td>
                  <td className="py-2 pr-3">
                    {row.next_day_returns === null
                      ? zh ? "待觀察" : "pending"
                      : row.next_day_returns}
                  </td>
                </tr>
              ))}
              {!daily.length ? (
                <tr>
                  <td colSpan={8} className="py-4 text-center text-white/50">
                    {zh ? "載入中…" : "Loading…"}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="glass-card space-y-sm p-xl">
        <h2 className="text-lg font-bold">{zh ? "口徑與隱私" : "Definitions & privacy"}</h2>
        <ul className="space-y-xs text-sm text-white/70">
          {Object.entries(metrics?.definitions ?? {}).map(([key, text]) => (
            <li key={key}>
              <span className="font-semibold text-white/90">{key}</span> — {text}
            </li>
          ))}
        </ul>
        <p className="text-xs text-white/50">
          {zh
            ? "同一份資料也有機器可讀的 machine 區塊：GET /api/world/public/metrics?days=14&lang=zh"
            : "The same payload carries a parseable machine block: GET /api/world/public/metrics?days=14&lang=en"}
        </p>
      </section>
    </main>
  );
}
