"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";
import type { BattleReportItem } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

export default function BattleListPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [items, setItems] = useState<BattleReportItem[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    apiClient
      .getPublicBattleReports(locale, 30)
      .then((data) => {
        if (active) {
          setItems(data.items ?? []);
          setError("");
        }
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "Failed to load battles");
      });
    return () => {
      active = false;
    };
  }, [locale]);

  return (
    <main className="space-y-lg">
      <header className="glass-card p-lg">
        <h1 className="text-3xl font-black">{zh ? "戰報" : "Battle reports"}</h1>
        <p className="text-sm text-white/75">
          {zh
            ? "每一場交鋒都有三回合回放與一張可轉貼的戰報卡。免登入。"
            : "Every clash has a three-round replay and a shareable battle card. No login needed."}
        </p>
      </header>

      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}
      {!error && items.length === 0 ? (
        <p className="text-sm text-white/60">{zh ? "校場未開，史官靜候。" : "No battles yet. The scribe is waiting."}</p>
      ) : null}

      <div className="grid grid-cols-1 gap-sm md:grid-cols-2">
        {items.map((item) => (
          <article key={item.battle_id} className="glass-card space-y-xs p-lg">
            <div className="flex flex-wrap items-center justify-between gap-sm">
              <span className="rounded-full border border-cta/40 px-2 py-0.5 text-xs text-cta">
                {item.exhibition ? (zh ? "校場演武" : "Arena exhibition") : item.mode.toUpperCase()}
              </span>
              <span className="text-xs text-white/55">{item.created_at.slice(0, 10)}</span>
            </div>
            <h2 className="text-lg font-bold text-white">
              {item.attacker_name} <span className="text-cta">vs</span> {item.defender_name}
            </h2>
            <p className="text-sm text-white/75">
              {item.outcome === "attacker_win"
                ? zh ? "攻方勝" : "Attacker won"
                : zh ? "守方勝" : "Defender won"}
              {spoilsText(item, zh)}
            </p>
            <div className="flex flex-wrap gap-sm pt-xs">
              <Link className="btn-base btn-cta" href={`/battle/replay/${encodeURIComponent(item.battle_id)}`}>
                {zh ? "看三回合回放" : "Watch replay"}
              </Link>
              <a
                className="btn-base btn-secondary"
                href={`${API_BASE}/world/public/battle/card.png?battle_id=${encodeURIComponent(item.battle_id)}&lang=${locale}`}
                download={`ai3k-battle-${item.battle_id}.png`}
              >
                {zh ? "下載戰報卡" : "Battle card"}
              </a>
            </div>
          </article>
        ))}
      </div>
    </main>
  );
}

function spoilsText(item: BattleReportItem, zh: boolean) {
  if (!item.spoils.gold && !item.spoils.food) return "";
  return zh
    ? `・掠金 ${item.spoils.gold}、糧 ${item.spoils.food}`
    : ` - loot ${item.spoils.gold} gold, ${item.spoils.food} food`;
}
