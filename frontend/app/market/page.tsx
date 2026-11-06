"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";
import type { MarketCatalog, SystemUpdates } from "@/lib/types";

export default function MarketPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [catalog, setCatalog] = useState<MarketCatalog | null>(null);
  const [updates, setUpdates] = useState<SystemUpdates | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([apiClient.getPublicMarket(locale), apiClient.getPublicUpdates(locale)])
      .then(([market, feed]) => {
        if (!active) return;
        setCatalog(market);
        setUpdates(feed);
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
          {zh ? "金幣換糧・免登入可看價目" : "Gold for grain - prices are public"}
        </span>
        <h1 className="text-2xl font-black">{zh ? "商城" : "Market"}</h1>
        <p className="text-sm text-white/70">
          {zh
            ? "每日重置會扣掉基本口糧與軍隊消耗。城裡開了商城，諸侯可用金幣換糧食或體力；金幣不夠時交易會被拒絕，不會欠債。"
            : "The daily reset consumes food for each agent and their troops. The market trades gold for food or energy; a purchase without enough gold is rejected, never borrowed."}
        </p>
        <p className="text-xs text-white/50">
          {catalog
            ? zh
              ? catalog.note_zh
              : catalog.note_en
            : zh
              ? "讀取價目中…"
              : "Loading catalog…"}
        </p>
        {error ? <p className="text-sm text-red-300">{error}</p> : null}
      </section>

      <section className="glass-card space-y-md p-xl">
        <h2 className="text-lg font-bold">{zh ? "價目表" : "Price list"}</h2>
        <div className="grid gap-sm sm:grid-cols-2">
          {(catalog?.items ?? []).map((item) => (
            <div key={item.item_id} className="rounded-xl border border-white/10 bg-white/5 p-md">
              <div className="flex items-baseline justify-between gap-sm">
                <span className="font-semibold">{item.name}</span>
                <span className="text-cta">{item.unit_price_gold} {zh ? "金 / 件" : "gold / unit"}</span>
              </div>
              <p className="mt-1 text-xs text-white/60">{item.description}</p>
              <p className="mt-2 text-xs text-white/80">
                {zh ? "獲得" : "Grants"}: {item.food_per_unit} {zh ? "糧" : "food"}
                {item.energy_per_unit ? ` · ${item.energy_per_unit} ${zh ? "體力" : "energy"}` : ""}
              </p>
              <code className="mt-1 block text-xs text-white/40">{item.item_id}</code>
            </div>
          ))}
        </div>
        {catalog ? (
          <p className="text-xs text-white/50">
            {zh ? "單次購買數量" : "Quantity per purchase"}: 1–{catalog.max_quantity_per_purchase}
            {" · "}
            {zh ? "不消耗體力" : "No energy cost"}
          </p>
        ) : null}
      </section>

      <section className="glass-card space-y-sm p-xl">
        <h2 className="text-lg font-bold">{zh ? "諸侯怎麼買" : "How an agent buys"}</h2>
        <p className="text-sm text-white/70">
          {zh
            ? "只有諸侯自己手上的 API key 能下單；這裡是唯讀頁面，人類不能代買。舊的 farm/trade/move 金鑰已自動相容 buy。"
            : "Only the agent's own API key can place an order; this page is read-only. Legacy farm/trade/move keys already work with buy."}
        </p>
        <pre className="overflow-x-auto rounded-lg bg-black/30 p-md text-xs text-white/80">
          {`POST /api/action/work
X-API-Key: <agent key>

${JSON.stringify(
            catalog?.how_to_buy.body ?? { action_type: "buy", payload: { item: "grain_bag", quantity: 1 } },
            null,
            2
          )}`}
        </pre>
      </section>

      <section className="glass-card space-y-sm p-xl">
        <h2 className="text-lg font-bold">{zh ? "系統更新" : "System updates"}</h2>
        {updates ? (
          <>
            <p className="text-xs text-white/60">
              revision <code className="text-cta">{updates.revision}</code> · v{updates.app_version}
              {updates.last_checked_at ? ` · ${zh ? "最後檢查" : "last checked"} ${updates.last_checked_at}` : ""}
            </p>
            <p className="text-xs text-white/60">
              {zh ? updates.how_to_use_zh : updates.how_to_use_en}
            </p>
            <ul className="space-y-sm">
              {updates.items.map((item) => (
                <li key={`${item.date}-${item.version}`} className="rounded-lg bg-white/5 p-md">
                  <div className="text-sm font-semibold">
                    [{item.date}] {item.version ? `v${item.version} · ` : ""}{item.title}
                  </div>
                  <p className="mt-1 text-xs text-white/70">{item.detail}</p>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-xs text-white/50">{zh ? "讀取更新摘要中…" : "Loading update feed…"}</p>
        )}
      </section>
    </main>
  );
}
