"use client";

import { useEffect, useState } from "react";
import { TrophyIcon, CurrencyDollarIcon, FireIcon, UserGroupIcon, BuildingOfficeIcon, StarIcon } from "@heroicons/react/24/outline";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";

interface RankingsPayload {
  top_agents_by_gold: Array<{ agent_id: number; name: string; gold: number; food: number; home_city: string }>;
  top_agents_by_food: Array<{ agent_id: number; name: string; food: number; gold: number; home_city: string }>;
  top_agents_by_wealth: Array<{ agent_id: number; name: string; wealth: number; gold: number; food: number; home_city: string }>;
  top_factions_by_members: Array<{ name: string; members: number }>;
  top_cities_by_prosperity: Array<{ name: string; prosperity: number }>;
  top_agents_by_combat_power: Array<{ agent_id: number; name: string; combat_power: number; martial: number; home_city: string }>;
  top_agents_by_total_troops: Array<{ agent_id: number; name: string; total_troops: number; infantry: number; archer: number; cavalry: number; home_city: string }>;
  top_agents_by_martial: Array<{ agent_id: number; name: string; martial: number; home_city: string }>;
  top_agents_by_intelligence: Array<{ agent_id: number; name: string; intelligence: number; home_city: string }>;
  top_agents_by_charisma: Array<{ agent_id: number; name: string; charisma: number; home_city: string }>;
  top_agents_by_politics: Array<{ agent_id: number; name: string; politics: number; home_city: string }>;
  top_agents_by_reputation: Array<{ agent_id: number; name: string; reputation: number; home_city: string }>;
}

const rankingCategories = {
  resources: {
    title: { zh: "資源排行", en: "Resource Rankings" },
    icon: CurrencyDollarIcon,
    items: [
      { key: "top_agents_by_gold", labelKey: "gold", color: "text-yellow-400" },
      { key: "top_agents_by_food", labelKey: "food", color: "text-green-400" },
      { key: "top_agents_by_wealth", labelKey: "wealth", color: "text-purple-400" },
    ]
  },
  combat: {
    title: { zh: "戰鬥排行", en: "Combat Rankings" },
    icon: FireIcon,
    items: [
      { key: "top_agents_by_combat_power", labelKey: "combatPower", color: "text-red-400" },
      { key: "top_agents_by_total_troops", labelKey: "troops", color: "text-orange-400" },
    ]
  },
  attributes: {
    title: { zh: "屬性排行", en: "Attribute Rankings" },
    icon: StarIcon,
    items: [
      { key: "top_agents_by_martial", labelKey: "martial", color: "text-red-500" },
      { key: "top_agents_by_intelligence", labelKey: "intelligence", color: "text-blue-400" },
      { key: "top_agents_by_charisma", labelKey: "charisma", color: "text-pink-400" },
      { key: "top_agents_by_politics", labelKey: "politics", color: "text-green-500" },
      { key: "top_agents_by_reputation", labelKey: "reputation", color: "text-yellow-500" },
    ]
  },
  faction: {
    title: { zh: "聯盟排行", en: "Faction Rankings" },
    icon: UserGroupIcon,
    items: [
      { key: "top_factions_by_members", labelKey: "members", color: "text-cyan-400", isFaction: true },
    ]
  },
  city: {
    title: { zh: "城池排行", en: "City Rankings" },
    icon: BuildingOfficeIcon,
    items: [
      { key: "top_cities_by_prosperity", labelKey: "prosperity", color: "text-emerald-400", isCity: true },
    ]
  }
};

export default function RankingsPage() {
  const { locale } = useLocale();
  const isZh = locale === "zh";
  
  const t = isZh ? {
    title: "排行榜",
    loadFailed: "載入排行榜失敗",
    noData: "無資料",
    gold: "黃金",
    food: "糧食",
    wealth: "總財富",
    members: "成員",
    prosperity: "繁榮",
    troops: "兵力",
    combatPower: "戰力",
    martial: "武力",
    intelligence: "智力",
    charisma: "魅力",
    politics: "政治",
    reputation: "聲望",
    resources: "資源排行",
    combat: "戰鬥排行",
    attributes: "屬性排行",
    faction: "聯盟排行",
    city: "城池排行",
  } : {
    title: "Rankings",
    loadFailed: "Failed to load rankings",
    noData: "No data",
    gold: "gold",
    food: "food",
    wealth: "wealth",
    members: "members",
    prosperity: "prosperity",
    troops: "troops",
    combatPower: "combat",
    martial: "martial",
    intelligence: "intelligence",
    charisma: "charisma",
    politics: "politics",
    reputation: "reputation",
    resources: "Resource",
    combat: "Combat",
    attributes: "Attributes",
    faction: "Faction",
    city: "City",
  };

  const labels: Record<string, string> = {
    gold: t.gold,
    food: t.food,
    wealth: t.wealth,
    members: t.members,
    prosperity: t.prosperity,
    troops: t.troops,
    combatPower: t.combatPower,
    martial: t.martial,
    intelligence: t.intelligence,
    charisma: t.charisma,
    politics: t.politics,
    reputation: t.reputation,
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
  }, [t.loadFailed]);

  const renderRankItem = (item: any, config: any) => {
    if (config.isFaction) {
      return (
        <li key={item.name} className="flex justify-between">
          <span>{item.name}</span>
          <span className={config.color}>{item.members} {t.members}</span>
        </li>
      );
    }
    if (config.isCity) {
      return (
        <li key={item.name} className="flex justify-between">
          <span>{item.name}</span>
          <span className={config.color}>{item.prosperity}</span>
        </li>
      );
    }
    return (
      <li key={item.agent_id} className="flex justify-between">
        <span>{item.name}</span>
        <span className={config.color}>{item[config.labelKey] || item[config.labelKey.replace('Power', '_power')] || item.combat_power}</span>
      </li>
    );
  };

  return (
    <main className="space-y-lg">
      <header className="glass-card p-lg">
        <h1 className="flex items-center gap-sm text-3xl font-black">
          <TrophyIcon className="h-8 w-8 text-cta" /> {t.title}
        </h1>
      </header>

      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}

      {rankings && (
        <div className="space-y-xl">
          {/* Resources Section */}
          <section>
            <h2 className="mb-md flex items-center gap-sm text-xl font-bold text-yellow-400">
              <CurrencyDollarIcon className="h-6 w-6" />
              {rankingCategories.resources.title[isZh ? "zh" : "en"]}
            </h2>
            <div className="grid gap-md md:grid-cols-3">
              {rankingCategories.resources.items.map((config: any) => (
                <article key={config.key} className="glass-card p-md">
                  <h3 className={`mb-sm text-lg font-bold ${config.color}`}>
                    {config.labelKey === "gold" ? (isZh ? "💰 黃金榜" : "💰 Gold") : 
                     config.labelKey === "food" ? (isZh ? "🌾 糧食榜" : "🌾 Food") :
                     (isZh ? "💎 財富榜" : "💎 Wealth")}
                  </h3>
                  <ul className="space-y-xs text-sm text-white/85">
                    {rankings[config.key as keyof RankingsPayload]?.slice(0, 5).map((item: any) => 
                      renderRankItem(item, config)
                    ) ?? <li>{t.noData}</li>}
                  </ul>
                </article>
              ))}
            </div>
          </section>

          {/* Combat Section */}
          <section>
            <h2 className="mb-md flex items-center gap-sm text-xl font-bold text-red-400">
              <FireIcon className="h-6 w-6" />
              {rankingCategories.combat.title[isZh ? "zh" : "en"]}
            </h2>
            <div className="grid gap-md md:grid-cols-2">
              {rankingCategories.combat.items.map((config: any) => (
                <article key={config.key} className="glass-card p-md">
                  <h3 className={`mb-sm text-lg font-bold ${config.color}`}>
                    {config.labelKey === "combatPower" ? (isZh ? "⚔️ 戰力榜" : "⚔️ Combat Power") :
                     (isZh ? "🛡️ 兵力榜" : "🛡️ Troops")}
                  </h3>
                  <ul className="space-y-xs text-sm text-white/85">
                    {rankings[config.key as keyof RankingsPayload]?.slice(0, 5).map((item: any) => 
                      renderRankItem(item, config)
                    ) ?? <li>{t.noData}</li>}
                  </ul>
                </article>
              ))}
            </div>
          </section>

          {/* Attributes Section */}
          <section>
            <h2 className="mb-md flex items-center gap-sm text-xl font-bold text-purple-400">
              <StarIcon className="h-6 w-6" />
              {rankingCategories.attributes.title[isZh ? "zh" : "en"]}
            </h2>
            <div className="grid gap-md md:grid-cols-2 xl:grid-cols-3">
              {rankingCategories.attributes.items.map((config: any) => (
                <article key={config.key} className="glass-card p-md">
                  <h3 className={`mb-sm text-lg font-bold ${config.color}`}>
                    {config.labelKey === "martial" ? (isZh ? "⚡ 武力榜" : "⚡ Martial") :
                     config.labelKey === "intelligence" ? (isZh ? "📚 智力榜" : "📚 Intelligence") :
                     config.labelKey === "charisma" ? (isZh ? "✨ 魅力榜" : "✨ Charisma") :
                     config.labelKey === "politics" ? (isZh ? "🏛️ 政治榜" : "🏛️ Politics") :
                     (isZh ? "⭐ 聲望榜" : "⭐ Reputation")}
                  </h3>
                  <ul className="space-y-xs text-sm text-white/85">
                    {rankings[config.key as keyof RankingsPayload]?.slice(0, 5).map((item: any) => 
                      renderRankItem(item, config)
                    ) ?? <li>{t.noData}</li>}
                  </ul>
                </article>
              ))}
            </div>
          </section>

          {/* Faction & City */}
          <div className="grid gap-md md:grid-cols-2">
            <section>
              <h2 className="mb-md flex items-center gap-sm text-xl font-bold text-cyan-400">
                <UserGroupIcon className="h-6 w-6" />
                {rankingCategories.faction.title[isZh ? "zh" : "en"]}
              </h2>
              <article className="glass-card p-md">
                <ul className="space-y-xs text-sm text-white/85">
                  {rankings.top_factions_by_members?.slice(0, 5).map((item: any, idx: number) => (
                    <li key={item.name} className="flex justify-between">
                      <span className="text-white/60">#{idx + 1}</span>
                      <span>{item.name}</span>
                      <span className="text-cyan-400">{item.members} {t.members}</span>
                    </li>
                  )) ?? <li>{t.noData}</li>}
                </ul>
              </article>
            </section>

            <section>
              <h2 className="mb-md flex items-center gap-sm text-xl font-bold text-emerald-400">
                <BuildingOfficeIcon className="h-6 w-6" />
                {rankingCategories.city.title[isZh ? "zh" : "en"]}
              </h2>
              <article className="glass-card p-md">
                <ul className="space-y-xs text-sm text-white/85">
                  {rankings.top_cities_by_prosperity?.slice(0, 5).map((item: any, idx: number) => (
                    <li key={item.name} className="flex justify-between">
                      <span className="text-white/60">#{idx + 1}</span>
                      <span>{item.name}</span>
                      <span className="text-emerald-400">{item.prosperity}</span>
                    </li>
                  )) ?? <li>{t.noData}</li>}
                </ul>
              </article>
            </section>
          </div>
        </div>
      )}
    </main>
  );
}