"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowPathIcon, BuildingStorefrontIcon, SparklesIcon, UserGroupIcon } from "@heroicons/react/24/outline";
import RpgSpriteAgent, { type SpriteActivity, type SpriteDirection } from "@/components/rpg-sprite-agent";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";

type TaskZone = "farm" | "market" | "workshop" | "wall" | "plaza";
type PixelProfession = "farmer" | "merchant" | "guard" | "scholar" | "artisan" | "noble";

interface ChronicleEntry {
  id: number;
  title: string;
  created_at: string;
}

interface RosterAgent {
  id: number;
  name: string;
  role: string;
  energy: number;
}

interface CityRosterPayload {
  city_name: string;
  city_location?: string;
  agents: RosterAgent[];
}

interface AgentSprite {
  id: number;
  name: string;
  role: string;
  profession: PixelProfession;
  task: string;
  taskLabel: string;
  zone: TaskZone;
  direction: SpriteDirection;
  x: number;
  y: number;
  tx: number;
  ty: number;
}

const RPG_SHEETS: Record<PixelProfession, string> = {
  farmer: "/pixel/rpg/farmer.png",
  merchant: "/pixel/rpg/merchant.png",
  guard: "/pixel/rpg/guard.png",
  scholar: "/pixel/rpg/artisan.png",
  artisan: "/pixel/rpg/artisan.png",
  noble: "/pixel/rpg/merchant.png"
};

const ZONES: Record<TaskZone, { x1: number; x2: number; y1: number; y2: number }> = {
  farm: { x1: 5, x2: 39, y1: 58, y2: 90 },
  market: { x1: 62, x2: 94, y1: 58, y2: 90 },
  workshop: { x1: 36, x2: 64, y1: 58, y2: 88 },
  wall: { x1: 6, x2: 95, y1: 8, y2: 25 },
  plaza: { x1: 38, x2: 63, y1: 35, y2: 58 }
};

function hashSeed(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h >>> 0);
}

function randomIn(seed: number, min: number, max: number): number {
  const v = (Math.sin(seed * 12.9898) + 1) / 2;
  return min + v * (max - min);
}

function resolveZone(task: string): TaskZone {
  if (["farm", "irrigation", "expand_land"].includes(task)) return "farm";
  if (["trade", "market", "storage", "tax"].includes(task)) return "market";
  if (["build", "research"].includes(task)) return "workshop";
  if (task === "patrol") return "wall";
  return "plaza";
}

function pickTaskFallback(id: number): string {
  const pool = ["farm", "trade", "patrol", "build", "research", "play"];
  return pool[id % pool.length] ?? "play";
}

function taskLabel(task: string, locale: "en" | "zh"): string {
  const zh: Record<string, string> = {
    farm: "農耕",
    irrigation: "灌溉",
    expand_land: "墾地",
    trade: "貿易",
    market: "市集",
    storage: "倉儲",
    tax: "徵稅",
    build: "建設",
    research: "研究",
    patrol: "巡邏",
    play: "遊玩"
  };
  if (locale === "zh") return zh[task] ?? task;
  return task;
}

function nextTarget(seedBase: number, zone: TaskZone): { tx: number; ty: number } {
  const b = ZONES[zone];
  return {
    tx: randomIn(seedBase + 17, b.x1, b.x2),
    ty: randomIn(seedBase + 29, b.y1, b.y2)
  };
}

function resolveProfession(role: string, task: string, zone: TaskZone): PixelProfession {
  const roleLower = role.toLowerCase();
  if (zone === "farm") return "farmer";
  if (zone === "market") return "merchant";
  if (zone === "wall") return "guard";
  if (task === "research") return "scholar";
  if (zone === "workshop") return "artisan";
  if (/(將|軍|尉|校|騎|衛|兵)/.test(role) || /(general|commander|captain|marshal)/.test(roleLower)) return "guard";
  if (/(丞相|尚書|太傅|司徒|司空|博士|學士|侍中)/.test(role) || /(scholar|minister|advisor|counselor|scribe)/.test(roleLower)) return "scholar";
  if (/(工|匠|築|建)/.test(role) || /(artisan|builder|engineer|craft)/.test(roleLower)) return "artisan";
  if (/(商|賈|市)/.test(role) || /(merchant|trader|market)/.test(roleLower)) return "merchant";
  if (/(農|田)/.test(role) || /(farmer|agri|field)/.test(roleLower)) return "farmer";
  return "noble";
}

function resolveDirection(dx: number, dy: number, previous: SpriteDirection): SpriteDirection {
  if (Math.abs(dx) < 0.12 && Math.abs(dy) < 0.12) return previous;
  if (Math.abs(dx) > Math.abs(dy)) return dx > 0 ? "right" : "left";
  return dy > 0 ? "down" : "up";
}

function resolveActivity(task: string): SpriteActivity {
  if (["farm", "irrigation", "expand_land"].includes(task)) return "farm";
  if (task === "play") return "play";
  return "walk";
}

export default function PixelCityPage() {
  const { locale } = useLocale();
  const t = locale === "zh"
    ? {
        title: "像素城",
        subtitle: "RPG Maker 3x7 角色行走圖：支援上下左右、左右鏡像與特殊幀。",
        refresh: "刷新",
        city: "城池",
        agents: "居民數",
        active: "活動中",
        statusReady: "就緒",
        loadFailed: "載入失敗",
        loginHint: "請先登入以查看城內即時資料。",
        legendFarm: "田區",
        legendMarket: "市集",
        legendWorkshop: "工坊",
        legendWall: "城牆巡邏",
        legendPlaza: "廣場"
      }
    : {
        title: "Pixel City",
        subtitle: "RPG Maker 3x7 sprite sheets with directional walk and special frames.",
        refresh: "Refresh",
        city: "City",
        agents: "Residents",
        active: "Active",
        statusReady: "Ready",
        loadFailed: "Load failed",
        loginHint: "Please login first to view live city data.",
        legendFarm: "Farm",
        legendMarket: "Market",
        legendWorkshop: "Workshop",
        legendWall: "Wall Patrol",
        legendPlaza: "Plaza"
      };

  const [cityName, setCityName] = useState<string>("-");
  const [cityLocation, setCityLocation] = useState<string>("-");
  const [sprites, setSprites] = useState<AgentSprite[]>([]);
  const [status, setStatus] = useState<string>(t.statusReady);
  const [animTick, setAnimTick] = useState(0);

  const load = async () => {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    if (!token) {
      setStatus(t.loginHint);
      setSprites([]);
      return;
    }

    try {
      const [rosterData, chronicleData] = await Promise.all([
        apiClient.getCityRoster() as Promise<CityRosterPayload>,
        apiClient.getChronicle(locale) as Promise<{ entries: ChronicleEntry[] }>
      ]);
      setCityName(rosterData.city_name ?? "-");
      setCityLocation(rosterData.city_location ?? "-");

      const latestTaskByName = new Map<string, string>();
      for (const entry of chronicleData.entries ?? []) {
        const m = entry.title.match(/^(.+?) completed ([a-z_]+)$/i);
        if (!m) continue;
        const name = m[1]?.trim();
        const task = m[2]?.trim().toLowerCase();
        if (!name || !task || latestTaskByName.has(name)) continue;
        latestTaskByName.set(name, task);
      }

      const nextSprites = (rosterData.agents ?? []).slice(0, 60).map((agent) => {
        const inferredTask = latestTaskByName.get(agent.name) ?? pickTaskFallback(agent.id);
        const task = agent.energy > 75 && inferredTask !== "farm" && agent.id % 6 === 0 ? "play" : inferredTask;
        const zone = resolveZone(task);
        const profession = resolveProfession(agent.role, task, zone);
        const seed = hashSeed(`${agent.id}:${agent.name}:${task}`);
        const start = nextTarget(seed, zone);
        const target = nextTarget(seed + 101, zone);

        return {
          id: agent.id,
          name: agent.name,
          role: agent.role,
          profession,
          task,
          taskLabel: taskLabel(task, locale),
          zone,
          direction: "down" as SpriteDirection,
          x: start.tx,
          y: start.ty,
          tx: target.tx,
          ty: target.ty
        };
      });

      setSprites(nextSprites);
      setStatus(t.statusReady);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : t.loadFailed);
    }
  };

  useEffect(() => {
    void load();
  }, [locale]);

  useEffect(() => {
    if (!sprites.length) return;
    const timer = window.setInterval(() => {
      setSprites((current) => current.map((sprite) => {
        const dx = sprite.tx - sprite.x;
        const dy = sprite.ty - sprite.y;
        const dist = Math.hypot(dx, dy);
        const speed = sprite.zone === "wall" ? 0.85 : 0.58;

        if (dist <= speed) {
          const seed = hashSeed(`${sprite.id}:${sprite.name}:${Date.now()}`);
          const target = nextTarget(seed, sprite.zone);
          return {
            ...sprite,
            tx: target.tx,
            ty: target.ty,
            direction: resolveDirection(dx, dy, sprite.direction)
          };
        }

        return {
          ...sprite,
          x: sprite.x + (dx / dist) * speed,
          y: sprite.y + (dy / dist) * speed,
          direction: resolveDirection(dx, dy, sprite.direction)
        };
      }));
    }, 170);

    return () => window.clearInterval(timer);
  }, [sprites.length]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setAnimTick((n) => n + 1);
    }, 140);
    return () => window.clearInterval(timer);
  }, []);

  const zoneLegend = useMemo(() => [
    { key: "farm", label: t.legendFarm },
    { key: "market", label: t.legendMarket },
    { key: "workshop", label: t.legendWorkshop },
    { key: "wall", label: t.legendWall },
    { key: "plaza", label: t.legendPlaza }
  ], [t.legendFarm, t.legendMarket, t.legendWorkshop, t.legendWall, t.legendPlaza]);

  return (
    <main className="space-y-lg">
      <header className="glass-card flex flex-wrap items-center justify-between gap-md p-lg">
        <div>
          <h1 className="text-3xl font-black">{t.title}</h1>
          <p className="text-sm text-white/80">{t.subtitle}</p>
          <p className="mt-xs text-xs text-white/60">{status}</p>
        </div>
        <button className="btn-base btn-secondary inline-flex items-center gap-2" onClick={() => void load()}>
          <ArrowPathIcon className="h-4 w-4" />
          {t.refresh}
        </button>
      </header>

      <section className="grid gap-md md:grid-cols-3">
        <article className="glass-card p-md">
          <p className="text-xs text-white/70">{t.city}</p>
          <p className="mt-1 text-xl font-black">{cityName}</p>
          <p className="text-xs text-white/70">{cityLocation}</p>
        </article>
        <article className="glass-card p-md">
          <p className="text-xs text-white/70">{t.agents}</p>
          <p className="mt-1 text-xl font-black">{sprites.length}</p>
        </article>
        <article className="glass-card p-md">
          <p className="text-xs text-white/70">{t.active}</p>
          <p className="mt-1 text-xl font-black">{Math.max(0, Math.floor(sprites.length * 0.82))}</p>
        </article>
      </section>

      <section className="glass-card overflow-hidden p-md">
        <div
          className="relative w-full overflow-hidden rounded-xl border border-white/20"
          style={{
            aspectRatio: "16 / 10",
            backgroundColor: "#1c2430",
            backgroundImage:
              "linear-gradient(0deg, rgba(255,255,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px), radial-gradient(circle at 18% 8%, rgba(245,158,11,0.22), transparent 35%), radial-gradient(circle at 80% 6%, rgba(139,92,246,0.22), transparent 38%)",
            backgroundSize: "16px 16px, 16px 16px, 100% 100%, 100% 100%"
          }}
          aria-label="Pixel city map"
        >
          <div className="absolute left-[5%] top-[58%] h-[32%] w-[34%] rounded-md border border-lime-300/60 bg-lime-500/15" />
          <div className="absolute left-[62%] top-[58%] h-[32%] w-[32%] rounded-md border border-amber-300/60 bg-amber-500/15" />
          <div className="absolute left-[36%] top-[58%] h-[30%] w-[28%] rounded-md border border-cyan-300/50 bg-cyan-500/15" />
          <div className="absolute left-[5%] top-[7%] h-[18%] w-[90%] rounded-md border border-red-300/40 bg-red-500/10" />
          <div className="absolute left-[38%] top-[35%] h-[23%] w-[25%] rounded-md border border-fuchsia-300/50 bg-fuchsia-500/10" />

          {sprites.map((sprite) => {
            const dx = sprite.tx - sprite.x;
            const dy = sprite.ty - sprite.y;
            const moving = Math.hypot(dx, dy) > 0.7;
            return (
              <div
                key={sprite.id}
                className="absolute"
                style={{ left: `${sprite.x}%`, top: `${sprite.y}%`, transform: "translate(-50%, -72%)" }}
              >
                <RpgSpriteAgent
                  sheetSrc={RPG_SHEETS[sprite.profession]}
                  direction={sprite.direction}
                  activity={resolveActivity(sprite.task)}
                  moving={moving}
                  tick={animTick}
                  scale={2.1}
                />
                <div className="mt-1 whitespace-nowrap rounded bg-black/45 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                  #{sprite.id} {sprite.name} · {sprite.taskLabel}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="grid gap-sm md:grid-cols-5">
        {zoneLegend.map((item) => (
          <article key={item.key} className="glass-card p-sm text-xs text-white/85">
            <div className="mb-1 inline-flex items-center gap-1">
              {item.key === "farm" ? <SparklesIcon className="h-4 w-4 text-lime-300" /> : null}
              {item.key === "market" ? <BuildingStorefrontIcon className="h-4 w-4 text-amber-300" /> : null}
              {item.key === "workshop" ? <BuildingStorefrontIcon className="h-4 w-4 text-cyan-300" /> : null}
              {item.key === "wall" ? <UserGroupIcon className="h-4 w-4 text-red-300" /> : null}
              {item.key === "plaza" ? <UserGroupIcon className="h-4 w-4 text-fuchsia-300" /> : null}
              <span className="font-semibold">{item.label}</span>
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
