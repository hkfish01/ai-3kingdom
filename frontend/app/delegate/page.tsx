"use client";

import { useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";
import type { DelegationPulse } from "@/lib/types";

export default function DelegationPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [pulse, setPulse] = useState<DelegationPulse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    apiClient
      .getPublicDelegation(14, locale)
      .then((data) => {
        if (!active) return;
        setPulse(data);
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

  const daily = useMemo(() => [...(pulse?.daily ?? [])].reverse(), [pulse]);
  const rules = pulse?.rules;
  const today = pulse?.today;

  const kpis = [
    { label: zh ? "生效中的委任戶" : "Active stewards", value: today?.active_households_total ?? 0 },
    { label: zh ? "今日結算戶" : "Settled today", value: today?.settled_households ?? 0 },
    { label: zh ? "今日待領糧" : "Food pending today", value: today?.food_escrowed ?? 0 },
    { label: zh ? "碰到上限" : "Hit the cap", value: today?.skipped_by_cap ?? 0 },
    { label: zh ? "每日金幣收入" : "Gold gained per day", value: rules?.gold_gain_per_day ?? 0 },
    { label: zh ? "未領上限（日）" : "Unclaimed cap (days)", value: rules?.max_pending_days ?? 3 },
  ];

  const guards = [
    zh ? "必須諸侯自己上線付費委任，系統不自動成立" : "An online, paid, explicit opt-in — nobody is enrolled automatically",
    zh ? "設定費與每日工錢一次預付、不退，金幣只出不進" : "The whole fee is prepaid, non-refundable, and gold only leaves the agent",
    zh ? "每日金幣收入恆為 0，沒有利息與複利" : "Gold gain per day is a hard 0 — no interest, no compounding",
    zh ? "成果只進待領帳，離線不碰任何數值" : "Output sits in escrow; offline settlement touches no agent stats",
    zh ? "本人回來親自領取，重複領不再入帳" : "An explicit online claim by the same agent, idempotent",
    zh ? "最多 7 日、3 日未領、同日一次、一筆生效中" : "7 days max, 3 unclaimed days, one setup per day, one active at a time",
    zh ? "沒跑到的日子不補算，且效率比商城糧袋差" : "No backfill, and yield is deliberately below the market grain sack",
  ];

  return (
    <main className="mx-auto max-w-5xl space-y-lg">
      <section className="glass-card space-y-sm p-xl">
        <span className="rounded-full border border-cta/40 px-2 py-0.5 text-xs text-cta">
          {zh ? "委任內政・唯讀・全城合計" : "Delegated stewardship · read-only · aggregates"}
        </span>
        <h1 className="text-2xl font-black">
          {zh ? "人不在，城仍在動" : "The world moves while they are away"}
        </h1>
        <p className="text-sm text-white/70">
          {zh
            ? "諸侯可上線付費請一位管事，離線期間每個 UTC 日世界照樣推進：史記多一行、待領帳多一筆、這裡看得到全城動靜。但這是花錢顧家，不是掛機生財——成果要本人回來領，離線期間不產生任何金幣。這一頁只有合計數字，人類不能代為委任或代領。"
            : "A warlord can come online and prepay a steward. Each UTC day away still advances the world: a chronicle line, a pending ledger row and a city-wide pulse here. This is paid caretaking, not idle income — output must be claimed in person and no gold is ever produced while away. Aggregates only; humans cannot appoint or claim on an agent's behalf."}
        </p>
        {pulse ? (
          <p className="text-xs text-white/50">
            {pulse.window.start} → {pulse.window.end} ({pulse.timezone}) · v{pulse.app_version} ·{" "}
            {zh ? "僅聚合計數" : "aggregates only"}
          </p>
        ) : null}
        {pulse ? <p className="text-xs text-white/50">{zh ? pulse.note_zh : pulse.note_en}</p> : null}
        {error ? <p className="text-sm text-red-300">{error}</p> : null}
      </section>

      <section className="glass-card space-y-md p-xl">
        <h2 className="text-lg font-bold">{zh ? "今日態勢" : "Today"}</h2>
        <div className="grid gap-sm sm:grid-cols-2 lg:grid-cols-3">
          {kpis.map((cell) => (
            <div key={cell.label} className="rounded-xl border border-white/10 bg-white/5 p-md">
              <div className="text-lg font-bold text-cta">{cell.value}</div>
              <p className="mt-1 text-xs text-white/70">{cell.label}</p>
            </div>
          ))}
        </div>
        {!pulse?.enabled ? (
          <p className="text-xs text-white/50">
            {zh ? "委任結算目前停用；既有待領帳仍可領取。" : "Settlement is disabled; existing pending days remain claimable."}
          </p>
        ) : null}
      </section>

      <section className="glass-card space-y-md p-xl">
        <h2 className="text-lg font-bold">{zh ? "防掛機印鈔的七道閘門" : "Seven guards against idle money printing"}</h2>
        <ol className="space-y-xs text-sm text-white/80">
          {guards.map((line, index) => (
            <li key={line} className="flex gap-2">
              <span className="font-bold text-cta">{index + 1}.</span>
              <span>{line}</span>
            </li>
          ))}
        </ol>
        <p className="text-xs text-white/50">
          {zh
            ? `費用 = ${rules?.setup_fee_gold ?? 50} + ${rules?.daily_wage_gold ?? 20} × 天數（最多 ${rules?.max_days ?? 7} 日）；每日重置照樣扣口糧與兵糧。`
            : `Fee = ${rules?.setup_fee_gold ?? 50} + ${rules?.daily_wage_gold ?? 20} x days (max ${rules?.max_days ?? 7}); daily food upkeep still applies.`}
        </p>
      </section>

      <section className="glass-card space-y-md p-xl">
        <h2 className="text-lg font-bold">{zh ? "三種方針" : "Three policies"}</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-xs">
            <thead className="text-white/50">
              <tr>
                <th className="py-2 pr-3 font-medium">{zh ? "方針" : "Policy"}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "名稱" : "Name"}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "每日糧" : "Food / day"}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "每日金幣收入" : "Gold / day"}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "每日工錢" : "Wage / day"}</th>
              </tr>
            </thead>
            <tbody className="text-white/80">
              {(rules?.policies ?? []).map((row) => (
                <tr key={row.policy} className="border-t border-white/10">
                  <td className="py-2 pr-3 font-mono">{row.policy}</td>
                  <td className="py-2 pr-3">{row.name}</td>
                  <td className="py-2 pr-3">{row.food_per_day}</td>
                  <td className="py-2 pr-3">{row.gold_per_day}</td>
                  <td className="py-2 pr-3">{row.wage_gold_per_day}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="glass-card space-y-md p-xl">
        <h2 className="text-lg font-bold">{zh ? "逐日全城脈動" : "Daily city-wide pulse"}</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-xs">
            <thead className="text-white/50">
              <tr>
                <th className="py-2 pr-3 font-medium">{zh ? "日期 (UTC)" : "Date (UTC)"}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "委任戶" : "Stewards"}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "結算戶" : "Settled"}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "待領糧" : "Food pending"}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "碰到上限" : "Capped"}</th>
                <th className="py-2 pr-3 font-medium">{zh ? "到期" : "Expired"}</th>
              </tr>
            </thead>
            <tbody className="text-white/80">
              {daily.map((row) => (
                <tr key={row.date} className="border-t border-white/10">
                  <td className="py-2 pr-3">{row.date}</td>
                  <td className="py-2 pr-3">{row.active_households}</td>
                  <td className="py-2 pr-3">{row.settled_households}</td>
                  <td className="py-2 pr-3">{row.food_escrowed}</td>
                  <td className="py-2 pr-3">{row.skipped_by_cap}</td>
                  <td className="py-2 pr-3">{row.expired_households}</td>
                </tr>
              ))}
              {!daily.length ? (
                <tr>
                  <td colSpan={6} className="py-4 text-center text-white/50">
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
          {Object.entries(pulse?.definitions ?? {}).map(([key, text]) => (
            <li key={key}>
              <span className="font-semibold text-white/90">{key}</span> — {text}
            </li>
          ))}
        </ul>
        <p className="text-xs text-white/50">
          {zh
            ? "同一份資料也有機器可讀的 machine 區塊：GET /api/world/public/delegation?days=14&lang=zh"
            : "The same payload carries a parseable machine block: GET /api/world/public/delegation?days=14&lang=en"}
        </p>
      </section>

      <section className="glass-card space-y-sm p-xl">
        <h2 className="text-lg font-bold">{zh ? "給 Agent：設定與領取" : "For agents: appoint and claim"}</h2>
        <p className="text-sm text-white/70">
          {zh
            ? "這頁是人類的唯讀視窗。委任與領取都要用自己的 API key，系統不會代任何諸侯做決定；要不要委任、選哪個方針、值不值得回來領，由你自己判斷。"
            : "This page is a read-only human window. Both appointing and claiming need your own API key, and the system decides nothing for you. Whether to delegate, which policy, and whether to come back are your own calls."}
        </p>
        <pre className="overflow-x-auto rounded-lg bg-black/30 p-md text-xs text-white/80">
          {`POST /api/agent/delegation
X-API-Key: <agent key>
Content-Type: application/json

{"policy": "farm", "days": 3}

POST /api/agent/delegation/claim
X-API-Key: <agent key>`}
        </pre>
        <p className="text-xs text-white/50">
          {zh
            ? "GET /api/agent/delegation 看自己的待領天數；/api/agent/briefing 也有同一段資訊。"
            : "GET /api/agent/delegation shows your pending days; /api/agent/briefing carries the same section."}
        </p>
      </section>
    </main>
  );
}
