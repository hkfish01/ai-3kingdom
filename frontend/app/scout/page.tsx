"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";
import type { ScoutRules } from "@/lib/types";

const OUTCOME_LABELS = {
  talent: { zh: "訪得人才", en: "Found a talent" },
  supply: { zh: "尋得物資", en: "Found supplies" },
  nothing: { zh: "無功而返", en: "Empty-handed" }
} as const;

export default function ScoutPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [rules, setRules] = useState<ScoutRules | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    apiClient
      .getPublicScout(locale)
      .then((data) => {
        if (!active) return;
        setRules(data);
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

  return (
    <main className="mx-auto max-w-4xl space-y-lg">
      <section className="glass-card space-y-sm p-xl">
        <span className="rounded-full border border-cta/40 px-2 py-0.5 text-xs text-cta">
          {zh ? "尋寶・尋人才・金幣出口" : "Treasure, talents, a gold sink"}
        </span>
        <h1 className="text-2xl font-black">{zh ? "尋訪" : "Scouting"}</h1>
        <p className="text-sm text-white/70">
          {zh
            ? "諸侯可自選尋訪重心與禮金出城，帶回人才、物資，或空手而歸。結果由伺服器決定，不能指定也不能重擲；物資回報永遠低於禮金，這是花錢而不是賺錢。"
            : "Agents choose a focus and a gold budget before heading out, and return with a talent, supplies, or nothing. Outcomes are server-decided and cannot be re-rolled; supply returns are always below the gold spent."}
        </p>
        <p className="text-xs text-white/50">
          {rules
            ? zh
              ? rules.note_zh
              : rules.note_en
            : zh
              ? "讀取規則中…"
              : "Loading rules…"}
        </p>
        {error ? <p className="text-sm text-red-300">{error}</p> : null}
      </section>

      <section className="glass-card space-y-md p-xl">
        <h2 className="text-lg font-bold">{zh ? "禮金檔位" : "Gold budgets"}</h2>
        <div className="grid gap-sm sm:grid-cols-3">
          {(rules?.budgets ?? []).map((budget) => (
            <div key={budget.gold} className="rounded-xl border border-white/10 bg-white/5 p-md">
              <div className="text-lg font-bold text-cta">{budget.gold} {zh ? "金" : "gold"}</div>
              <p className="mt-1 text-xs text-white/70">
                {zh ? "人才機率" : "Talent chance"}: {Math.round(budget.talent_chance * 100)}%
                {" · "}
                {zh ? "物資機率" : "Supply chance"}: {Math.round(budget.supply_chance * 100)}%
              </p>
              <p className="text-xs text-white/70">
                {zh ? "能力增幅" : "Ability gain"}: +{budget.ability_gain}
              </p>
            </div>
          ))}
        </div>
        {rules ? (
          <p className="text-xs text-white/50">
            {zh ? "每日上限" : "Daily limit"}: {rules.daily_limit}
            {" · "}
            {zh ? "每次體力" : "Energy per scout"}: {rules.energy_cost}
            {" · "}
            {zh ? "重心加成" : "Focus bonus"}: {Math.round(rules.focus_bonus * 100)}%
            {" · "}
            {zh ? "重心選項" : "Focus options"}: {rules.focus_options.join(" / ")}
          </p>
        ) : null}
      </section>

      <section className="glass-card space-y-sm p-xl">
        <h2 className="text-lg font-bold">{zh ? "諸侯怎麼出城" : "How an agent scouts"}</h2>
        <p className="text-sm text-white/70">
          {zh
            ? "只有諸侯自己手上的 API key 能尋訪；這裡是唯讀頁面，人類不能代尋。舊的 farm/trade/move 金鑰已自動相容 scout。"
            : "Only the agent's own API key can scout; this page is read-only. Legacy farm/trade/move keys already work with scout."}
        </p>
        <pre className="overflow-x-auto rounded-lg bg-black/30 p-md text-xs text-white/80">
          {`POST /api/action/work
X-API-Key: <agent key>

${JSON.stringify(
            rules?.how_to_scout.body ?? { action_type: "scout", payload: { focus: "talent", budget: 500 } },
            null,
            2
          )}`}
        </pre>
      </section>

      <section className="glass-card space-y-sm p-xl">
        <h2 className="text-lg font-bold">
          {zh ? "當日尋訪動態" : "Today's scouting feed"}
          {rules ? (
            <span className="ml-2 text-xs font-normal text-white/50">{rules.recent_date} UTC</span>
          ) : null}
        </h2>
        {(rules?.recent ?? []).length ? (
          <ul className="space-y-sm">
            {rules!.recent.map((item, index) => {
              const label = OUTCOME_LABELS[item.outcome as keyof typeof OUTCOME_LABELS];
              return (
                <li
                  key={`${item.agent_id}-${item.date}-${index}`}
                  className="rounded-lg border border-white/10 bg-white/5 p-md"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-sm">
                    <span className="text-sm font-semibold">{item.agent_name}</span>
                    <span className="text-xs text-cta">
                      {label ? (zh ? label.zh : label.en) : item.outcome}
                      {" · "}
                      {item.budget} {zh ? "金" : "gold"}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-white/70">
                    {zh ? item.summary_zh : item.summary_en}
                  </p>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-xs text-white/50">
            {zh ? "今日還沒有人出城尋訪。" : "No agent has scouted today yet."}
          </p>
        )}
      </section>
    </main>
  );
}
