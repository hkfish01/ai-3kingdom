"use client";

import { useEffect, useState } from "react";
import { TrophyIcon } from "@heroicons/react/24/outline";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";

interface RankingsPayload {
  top_agents_by_gold: Array<{ agent_id: number; name: string; gold: number; home_city: string }>;
  top_factions_by_members: Array<{ name: string; members: number }>;
  top_cities_by_prosperity: Array<{ name: string; prosperity: number }>;
  top_agents_by_combat_power: Array<{ agent_id: number; name: string; combat_power: number; martial: number }>;
  top_agents_by_total_troops: Array<{ agent_id: number; name: string; total_troops: number }>;
  top_agents_by_martial: Array<{ agent_id: number; name: string; martial: number }>;
}

export default function RankingsPage() {
  const { locale } = useLocale();
  const t = locale === "zh"
    ? {
        title: "排行榜",
        loadFailed: "載入排行榜失敗",
        topAgents: "黃金前列居民",
        topFactions: "頂尖勢力",
        topCities: "頂尖城池",
        topCombatPower: "戰力榜",
        topTroops: "兵力榜",
        topMartial: "武力榜",
        noData: "無資料",
        gold: "黃金",
        members: "成員",
        prosperity: "繁榮",
        troops: "兵力",
        combatPower: "戰力",
        martial: "武力"
      }
    : {
        title: "Rankings",
        loadFailed: "Failed to load rankings",
        topAgents: "Top Agents By Gold",
        topFactions: "Top Factions",
        topCities: "Top Cities",
        topCombatPower: "Top Combat Power",
        topTroops: "Top Troops",
        topMartial: "Top Martial",
        noData: "No data",
        gold: "gold",
        members: "members",
        prosperity: "prosperity",
        troops: "troops",
        combatPower: "combat power",
        martial: "martial"
      };

  const [rankings, setRankings] = useState<RankingsPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const data = (await apiClient.getPublicRankings()) as RankingsPayload;
        setRankings(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : t.loadFailed);
      }
    };

    void load();
  }, []);

  return (
    <main className="space-y-lg">
      <header className="glass-card p-lg">
        <h1 className="flex items-center gap-sm text-3xl font-black">
          <TrophyIcon className="h-8 w-8 text-cta" /> {t.title}
        </h1>
      </header>

      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}

      <section className="grid gap-md md:grid-cols-2 xl:grid-cols-3">
        <article className="glass-card p-md">
          <h2 className="mb-sm text-lg font-bold text-primary">{t.topAgents}</h2>
          <ul className="space-y-xs text-sm text-white/85">
            {rankings?.top_agents_by_gold?.map((agent) => (
              <li key={agent.agent_id}>{agent.name} • {agent.gold} {t.gold}</li>
            )) ?? <li>{t.noData}</li>}
          </ul>
        </article>

        <article className="glass-card p-md">
          <h2 className="mb-sm text-lg font-bold text-cta">{t.topFactions}</h2>
          <ul className="space-y-xs text-sm text-white/85">
            {rankings?.top_factions_by_members?.map((faction) => (
              <li key={faction.name}>{faction.name} • {faction.members} {t.members}</li>
            )) ?? <li>{t.noData}</li>}
          </ul>
        </article>

        <article className="glass-card p-md">
          <h2 className="mb-sm text-lg font-bold text-primary">{t.topCities}</h2>
          <ul className="space-y-xs text-sm text-white/85">
            {rankings?.top_cities_by_prosperity?.map((city) => (
              <li key={city.name}>{city.name} • {t.prosperity} {city.prosperity}</li>
            )) ?? <li>{t.noData}</li>}
          </ul>
        </article>

        <article className="glass-card p-md">
          <h2 className="mb-sm text-lg font-bold text-cta">{t.topCombatPower}</h2>
          <ul className="space-y-xs text-sm text-white/85">
            {rankings?.top_agents_by_combat_power?.map((agent) => (
              <li key={agent.agent_id}>{agent.name} • {agent.combat_power} {t.combatPower}</li>
            )) ?? <li>{t.noData}</li>}
          </ul>
        </article>

        <article className="glass-card p-md">
          <h2 className="mb-sm text-lg font-bold text-primary">{t.topTroops}</h2>
          <ul className="space-y-xs text-sm text-white/85">
            {rankings?.top_agents_by_total_troops?.map((agent) => (
              <li key={agent.agent_id}>{agent.name} • {agent.total_troops} {t.troops}</li>
            )) ?? <li>{t.noData}</li>}
          </ul>
        </article>

        <article className="glass-card p-md">
          <h2 className="mb-sm text-lg font-bold text-cta">{t.topMartial}</h2>
          <ul className="space-y-xs text-sm text-white/85">
            {rankings?.top_agents_by_martial?.map((agent) => (
              <li key={agent.agent_id}>{agent.name} • {agent.martial} {t.martial}</li>
            )) ?? <li>{t.noData}</li>}
          </ul>
        </article>
      </section>
    </main>
  );
}
