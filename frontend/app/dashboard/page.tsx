"use client";

import { useEffect, useState } from "react";
import {
  BuildingOffice2Icon,
  CurrencyDollarIcon,
  GlobeAsiaAustraliaIcon,
  ShieldCheckIcon,
  UsersIcon
} from "@heroicons/react/24/outline";
import { apiClient } from "@/lib/api-client";
import { WorldState } from "@/lib/types";
import { useLocale } from "@/lib/locale";

interface PositionItem {
  key: string;
  role: string;
  branch: string;
  tier: number;
  promotion_cost: number;
  max_slots?: number | null;
  bonus: Record<string, number>;
}

interface RosterAgent {
  id: number;
  name: string;
  role: string;
  branch: string;
  tier: number;
  bonus: Record<string, number>;
  energy: number;
  gold: number;
  food: number;
  abilities?: {
    martial: number;
    intelligence: number;
    charisma: number;
    politics: number;
  };
  faction_id?: number | null;
}

interface CityRosterPayload {
  city_name: string;
  city_location?: string;
  civil_hierarchy: PositionItem[];
  military_hierarchy: PositionItem[];
  agents: RosterAgent[];
}

interface OccupiedRoleItem {
  role: string;
  branch: string;
  tier: number;
  promotion_cost: number;
  max_slots?: number | null;
  bonus: Record<string, number>;
  count: number;
}

function bonusText(bonus: Record<string, number>, locale: "en" | "zh"): string {
  const gold = bonus.work_gold_pct ?? 0;
  const food = bonus.work_food_pct ?? 0;
  const defense = bonus.defense_pct ?? 0;
  if (locale === "zh") {
    return `工作黃金+${gold}% / 工作糧食+${food}% / 防禦+${defense}%`;
  }
  return `Work Gold +${gold}% / Work Food +${food}% / Defense +${defense}%`;
}

export default function DashboardPage() {
  const { locale } = useLocale();
  const t = locale === "zh"
    ? {
        title: "城池儀表板",
        subtitle: "僅顯示城內代理與職位架構（代理與勢力建立改為 Agent 自主行為）。",
        refresh: "刷新",
        agentCount: "代理數量",
        prosperity: "繁榮度",
        defense: "防禦力",
        treasury: "國庫黃金",
        cityRoster: "城內代理名冊",
        roleStructure: "在職職位（僅顯示目前有人任職）",
        role: "職位",
        tier: "層級",
        cost: "升職花費",
        bonus: "加成",
        slots: "名額",
        name: "名稱",
        branch: "體系",
        energy: "體力",
        gold: "黃金",
        food: "糧食",
        faction: "勢力",
        noData: "無資料",
        status: "狀態",
        ready: "就緒",
        loadFailed: "載入失敗",
        civilLabel: "文臣",
        militaryLabel: "武將"
      }
    : {
        title: "City Dashboard",
        subtitle: "Read-only city roster and position hierarchy (agent/faction creation is AI-driven).",
        refresh: "Refresh",
        agentCount: "Agent Count",
        prosperity: "Prosperity",
        defense: "Defense",
        treasury: "Treasury Gold",
        cityRoster: "City Agent Roster",
        roleStructure: "Occupied Positions (Only roles currently assigned)",
        role: "Position",
        tier: "Tier",
        cost: "Promotion Cost",
        bonus: "Bonus",
        slots: "Slots",
        name: "Name",
        branch: "Branch",
        energy: "Energy",
        gold: "Gold",
        food: "Food",
        faction: "Faction",
        noData: "No data",
        status: "Status",
        ready: "Ready",
        loadFailed: "Load failed",
        civilLabel: "Civil",
        militaryLabel: "Military"
      };

  const [world, setWorld] = useState<WorldState | null>(null);
  const [roster, setRoster] = useState<CityRosterPayload | null>(null);
  const [message, setMessage] = useState(t.ready);

  const occupiedRoles = (() => {
    if (!roster) return [] as OccupiedRoleItem[];
    const merged = [...roster.civil_hierarchy, ...roster.military_hierarchy];
    const byRole = new Map<string, PositionItem>();
    for (const item of merged) {
      byRole.set(item.role, item);
    }
    const counts = new Map<string, number>();
    for (const agent of roster.agents) {
      counts.set(agent.role, (counts.get(agent.role) ?? 0) + 1);
    }
    const out: OccupiedRoleItem[] = [];
    for (const [role, count] of counts.entries()) {
      const def = byRole.get(role);
      if (def) {
        out.push({
          role,
          branch: def.branch,
          tier: def.tier,
          promotion_cost: def.promotion_cost,
          bonus: def.bonus,
          max_slots: def.max_slots,
          count
        });
      }
    }
    return out.sort((a, b) => b.tier - a.tier || a.role.localeCompare(b.role));
  })();

  const load = async () => {
    try {
      const [worldData, rosterData] = await Promise.all([
        apiClient.getWorldState() as Promise<WorldState>,
        apiClient.getCityRoster() as Promise<CityRosterPayload>
      ]);
      setWorld(worldData);
      setRoster(rosterData);
      setMessage(t.ready);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : t.loadFailed);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <main className="space-y-lg">
      <header className="glass-card flex flex-wrap items-center justify-between gap-md p-lg">
        <div>
          <h1 className="text-3xl font-black">{t.title}</h1>
          <p className="text-sm text-white/80">{t.subtitle}</p>
        </div>
        <button className="btn-base btn-secondary" onClick={() => void load()}>
          {t.refresh}
        </button>
      </header>

      <section className="grid-auto">
        <article className="glass-card p-md">
          <UsersIcon className="mb-xs h-6 w-6 text-primary" />
          <p className="text-xs text-white/70">{t.agentCount}</p>
          <p className="text-2xl font-black">{world?.agent_count ?? "-"}</p>
        </article>
        <article className="glass-card p-md">
          <GlobeAsiaAustraliaIcon className="mb-xs h-6 w-6 text-cta" />
          <p className="text-xs text-white/70">{t.prosperity}</p>
          <p className="text-2xl font-black">{world?.prosperity ?? "-"}</p>
        </article>
        <article className="glass-card p-md">
          <ShieldCheckIcon className="mb-xs h-6 w-6 text-primary" />
          <p className="text-xs text-white/70">{t.defense}</p>
          <p className="text-2xl font-black">{world?.defense_power ?? "-"}</p>
        </article>
        <article className="glass-card p-md">
          <CurrencyDollarIcon className="mb-xs h-6 w-6 text-cta" />
          <p className="text-xs text-white/70">{t.treasury}</p>
          <p className="text-2xl font-black">{world?.treasury?.gold ?? "-"}</p>
        </article>
      </section>

      <section className="glass-card p-lg">
        <h2 className="mb-md flex items-center gap-2 text-xl font-bold">
          <BuildingOffice2Icon className="h-6 w-6 text-cta" />
          {t.roleStructure}
        </h2>
        <ul className="space-y-sm text-sm">
          {occupiedRoles.length ? occupiedRoles.map((item) => (
            <li key={item.role} className="rounded-lg border border-white/15 bg-white/5 p-sm">
              <p className="font-semibold">{item.role} × {item.count}</p>
              <p className="text-white/75">{t.tier}: {item.tier} • {t.cost}: {item.promotion_cost} • {t.slots}: {item.max_slots ?? "∞"}</p>
              <p className="text-white/70">{bonusText(item.bonus, locale)}</p>
            </li>
          )) : <li className="text-white/70">{t.noData}</li>}
        </ul>
      </section>

      <section className="glass-card p-lg">
        <h2 className="mb-md text-xl font-bold">{t.cityRoster}</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="text-white/70">
              <tr>
                <th className="pb-sm">{t.name}</th>
                <th className="pb-sm">{t.role}</th>
                <th className="pb-sm">{t.branch}</th>
                <th className="pb-sm">{t.bonus}</th>
                <th className="pb-sm">{t.energy}</th>
                <th className="pb-sm">{t.gold}</th>
                <th className="pb-sm">{t.food}</th>
                <th className="pb-sm">{t.faction}</th>
              </tr>
            </thead>
            <tbody>
              {(roster?.agents ?? []).length ? (roster?.agents ?? []).map((agent) => (
                <tr key={agent.id} className="border-t border-white/10">
                  <td className="py-sm">{agent.name}</td>
                  <td className="py-sm">{agent.role}</td>
                  <td className="py-sm">{agent.branch === "military" ? t.militaryLabel : t.civilLabel}</td>
                  <td className="py-sm">{bonusText(agent.bonus, locale)}</td>
                  <td className="py-sm">{agent.energy}</td>
                  <td className="py-sm">{agent.gold}</td>
                  <td className="py-sm">{agent.food}</td>
                  <td className="py-sm">{agent.faction_id ?? "-"}</td>
                </tr>
              )) : (
                <tr>
                  <td className="py-sm text-white/70" colSpan={8}>{t.noData}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <p className="rounded-lg bg-white/10 p-sm text-sm text-white/90">{t.status}: {message}</p>
    </main>
  );
}
