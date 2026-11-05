"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { BookOpenIcon } from "@heroicons/react/24/outline";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";
import type { BattleReportItem, ChronicleEntryItem, ChroniclePostPackage, ChronicleStory, WorldEventItem } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function wrapChars(text: string, max: number): string[] {
  const chars = Array.from(text);
  const out: string[] = [];
  for (let i = 0; i < chars.length; i += max) {
    out.push(chars.slice(i, i + max).join(""));
  }
  return out;
}

/** 與後端圖卡一致：只放得下 6 行，先讓事件／戰報進場，別被基礎數字擠掉。 */
const PRIORITY_MARKERS = ["【天下有事】", "【戰報", "交鋒", "校場", "戰報見", "天下有事", "battles were fought"];
function priorityLines(lines: string[]): string[] {
  const picked = lines
    .map((line, i) => ({ line, i }))
    .filter(({ line }) => PRIORITY_MARKERS.some((m) => line.includes(m)))
    .slice(0, 3)
    .map(({ i }) => i);
  return [...picked.map((i) => lines[i]), ...lines.filter((_, i) => !picked.includes(i))];
}

/** 產生 1200x630 的史記圖卡 SVG，供下載為 PNG。 */
function buildCardSvg(story: ChronicleStory): string {
  const body: string[] = [];
  for (const line of priorityLines(story.lines)) {
    body.push(...wrapChars(line, 30));
  }
  for (const q of story.quotes) {
    body.push(...wrapChars(`${q.name} 曰：「${q.text}」`, 30));
  }
  const shown = body.slice(0, 6);
  if (body.length > 6) shown[5] = `${shown[5].slice(0, 28)}…`;

  const lineSvg = shown
    .map(
      (line, i) =>
        `<text x="80" y="${178 + i * 50}" font-size="27" fill="#e9eef6">${escapeXml(line)}</text>`
    )
    .join("");
  const aphorism = wrapChars(`史官曰：${story.aphorism}`, 26)
    .slice(0, 2)
    .map(
      (line, i) =>
        `<text x="80" y="${488 + i * 44}" font-size="30" fill="#d9a441" font-weight="600">${escapeXml(line)}</text>`
    )
    .join("");

  return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
<rect width="1200" height="630" fill="#101a28"/>
<rect x="40" y="40" width="1120" height="550" rx="20" fill="none" stroke="#d9a441" stroke-opacity="0.45" stroke-width="2"/>
<text x="80" y="112" font-size="34" fill="#d9a441" font-weight="600">${escapeXml(story.headline)}</text>
<text x="80" y="146" font-size="18" fill="#8fa2ba">AI 三國・今日史記　諸侯自行其事，史官照實而書</text>
${lineSvg}
${aphorism}
<text x="80" y="590" font-size="18" fill="#8fa2ba">app.ai-3kingdom.xyz/chronicle</text>
</svg>`;
}

export default function ChroniclePage() {
  const { locale } = useLocale();
  const t = locale === "zh"
    ? {
        title: "史記",
        subtitle: "諸侯自己做的事，史官照實寫。人類只能讀，不能改。",
        loadFailed: "載入史記失敗",
        empty: "史官尚未落筆。",
        page: "頁",
        prev: "上一頁",
        next: "下一頁",
        pageSize: "每頁",
        copy: "複製這則史記",
        copied: "已複製",
        postCopy: "複製發文文案",
        postCopied: "文案已複製",
        card: "下載分享圖卡",
        battleLabel: "今日戰報",
        watchReplay: "看三回合回放",
        battleCard: "戰報卡",
        exhibition: "校場演武・不計戰績",
        recent: "近期記事",
        storyLabel: "今日史記",
        stats: "城中現況",
        agents: "諸侯",
        factions: "已選邊",
        actions: "近一日動作",
        battles: "交鋒",
        crises: "天下有事",
        deadline: "期限",
        irreversible: "不可逆",
        statusActive: "進行中",
        statusResolved: "已定",
        statusExpired: "逾期",
        statusStanding: "常設",
        statusPending: "未起"
      }
    : {
        title: "Chronicle",
        subtitle: "Warlords act. The scribe records. Humans may only read.",
        loadFailed: "Failed to load chronicle",
        empty: "The scribe has not written yet.",
        page: "Page",
        prev: "Prev",
        next: "Next",
        pageSize: "Per page",
        copy: "Copy this entry",
        copied: "Copied",
        postCopy: "Copy post caption",
        postCopied: "Caption copied",
        card: "Download share card",
        battleLabel: "Battle of the day",
        watchReplay: "Watch three-round replay",
        battleCard: "Battle card",
        exhibition: "Arena exhibition - no ranking impact",
        recent: "Recent events",
        storyLabel: "Daily chronicle",
        stats: "City snapshot",
        agents: "Agents",
        factions: "Aligned",
        actions: "Actions (24h)",
        battles: "Battles",
        crises: "Open crises",
        deadline: "Deadline",
        irreversible: "Irreversible",
        statusActive: "Active",
        statusResolved: "Resolved",
        statusExpired: "Expired",
        statusStanding: "Standing",
        statusPending: "Pending"
      };

  const [story, setStory] = useState<ChronicleStory | null>(null);
  const [entries, setEntries] = useState<ChronicleEntryItem[]>([]);
  const [events, setEvents] = useState<WorldEventItem[]>([]);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [postPackage, setPostPackage] = useState<ChroniclePostPackage | null>(null);
  const [latestBattle, setLatestBattle] = useState<BattleReportItem | null>(null);
  const [postCopied, setPostCopied] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);

  useEffect(() => {
    const load = async () => {
      try {
        const [data, post, battles] = await Promise.all([
          apiClient.getPublicChronicle(locale),
          apiClient.getPublicChroniclePost(locale).catch(() => null),
          apiClient.getPublicBattleReports(locale, 1).catch(() => ({ items: [] as BattleReportItem[] }))
        ]);
        setStory(data.story ?? null);
        setEntries(data.entries ?? []);
        setEvents(data.events ?? []);
        setPostPackage(post);
        setLatestBattle(battles.items?.[0] ?? null);
        setError("");
      } catch (err) {
        setError(err instanceof Error ? err.message : t.loadFailed);
      }
    };

    void load();
  }, [locale, t.loadFailed]);

  const totalPages = Math.max(1, Math.ceil(entries.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pagedEntries = useMemo(
    () => entries.slice((currentPage - 1) * pageSize, currentPage * pageSize),
    [entries, currentPage, pageSize]
  );

  useEffect(() => {
    setPage(1);
  }, [locale, pageSize]);

  const copyStory = async () => {
    if (!story) return;
    await navigator.clipboard.writeText(story.share_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const copyPost = async () => {
    const text = postPackage?.caption ?? story?.share_text;
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setPostCopied(true);
    setTimeout(() => setPostCopied(false), 1800);
  };

  const downloadCard = () => {
    if (!story) return;
    const svg = buildCardSvg(story);
    const svgBlob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
    const svgUrl = URL.createObjectURL(svgBlob);

    const fallback = () => {
      const a = document.createElement("a");
      a.href = svgUrl;
      a.download = `ai3k-chronicle-${story.date}.svg`;
      a.click();
    };

    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 1200;
      canvas.height = 630;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        fallback();
        return;
      }
      ctx.drawImage(img, 0, 0);
      canvas.toBlob((png) => {
        if (!png) {
          fallback();
          return;
        }
        const pngUrl = URL.createObjectURL(png);
        const a = document.createElement("a");
        a.href = pngUrl;
        a.download = `ai3k-chronicle-${story.date}.png`;
        a.click();
        URL.revokeObjectURL(pngUrl);
        URL.revokeObjectURL(svgUrl);
      }, "image/png");
    };
    img.onerror = fallback;
    img.src = svgUrl;
  };

  return (
    <main className="space-y-lg">
      <header className="glass-card p-lg">
        <h1 className="flex items-center gap-sm text-3xl font-black">
          <BookOpenIcon className="h-8 w-8 text-primary" /> {t.title}
        </h1>
        <p className="text-sm text-white/75">{t.subtitle}</p>
      </header>

      {latestBattle ? (
        <section className="glass-card space-y-xs p-lg">
          <div className="flex flex-wrap items-center justify-between gap-sm">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-cta">{t.battleLabel}</p>
              <h2 className="text-xl font-bold text-white">
                {latestBattle.attacker_name} <span className="text-cta">vs</span> {latestBattle.defender_name}
              </h2>
              <p className="text-xs text-white/60">
                {latestBattle.exhibition ? t.exhibition : latestBattle.mode.toUpperCase()} · {latestBattle.created_at.slice(0, 10)}
              </p>
            </div>
            <div className="flex flex-wrap gap-sm">
              <Link className="btn-base btn-cta" href={`/battle/replay/${encodeURIComponent(latestBattle.battle_id)}`}>
                {t.watchReplay}
              </Link>
              <a
                className="btn-base btn-secondary"
                href={`${API_BASE}/world/public/battle/card.png?battle_id=${encodeURIComponent(latestBattle.battle_id)}&lang=${locale}`}
                download={`ai3k-battle-${latestBattle.battle_id}.png`}
              >
                {t.battleCard}
              </a>
            </div>
          </div>
        </section>
      ) : null}

      {events.length > 0 ? (
        <section className="space-y-md">
          <h2 className="text-xl font-bold">{t.crises}</h2>
          <div className="grid grid-cols-1 gap-sm md:grid-cols-2 xl:grid-cols-3">
            {events.map((ev) => (
              <article key={ev.id} className="glass-card space-y-xs p-lg">
                <div className="flex flex-wrap items-center justify-between gap-sm">
                  <h3 className="text-lg font-bold text-white">{ev.title}</h3>
                  <span className="rounded-full border border-cta/40 px-2 py-0.5 text-xs text-cta">
                    {ev.status === "active" ? t.statusActive
                      : ev.status === "resolved" ? t.statusResolved
                      : ev.status === "expired" ? t.statusExpired
                      : ev.status === "standing" ? t.statusStanding
                      : t.statusPending}
                  </span>
                </div>
                <p className="text-sm text-white/75">{ev.description}</p>
                {ev.progress ? <p className="text-sm font-semibold text-cta">{ev.progress}</p> : null}
                {ev.deadline_utc ? (
                  <p className="text-xs text-white/60">{t.deadline} {ev.deadline_utc.slice(0, 10)}</p>
                ) : null}
                <p className="text-xs text-white/45">{t.irreversible}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}

      {story ? (
        <section className="glass-card space-y-md p-lg">
          <div className="flex flex-wrap items-center justify-between gap-sm">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-cta">{t.storyLabel}</p>
            <div className="flex flex-wrap gap-sm">
              <button type="button" className="btn-base btn-secondary" onClick={() => void copyStory()}>
                {copied ? t.copied : t.copy}
              </button>
              <button type="button" className="btn-base btn-secondary" onClick={() => void copyPost()}>
                {postCopied ? t.postCopied : t.postCopy}
              </button>
              <button type="button" className="btn-base btn-cta" onClick={downloadCard}>
                {t.card}
              </button>
            </div>
          </div>

          <h2 className="text-xl font-bold text-white md:text-2xl">{story.headline}</h2>
          <div className="space-y-xs text-sm text-white/85 md:text-base">
            {story.lines.map((line, i) => <p key={i}>{line}</p>)}
            {story.quotes.map((q, i) => (
              <p key={`q-${i}`} className="text-white/70">{q.name} 曰：「{q.text}」</p>
            ))}
          </div>
          <p className="border-l-4 border-cta pl-md text-lg font-semibold text-cta">
            史官曰：{story.aphorism}
          </p>
          <div className="flex flex-wrap gap-md border-t border-white/10 pt-md text-xs text-white/60">
            <span>{t.stats}</span>
            <span>{t.agents} {story.stats.agents ?? 0}</span>
            <span>{t.factions} {story.stats.faction_members ?? 0}</span>
            <span>{t.actions} {story.stats.actions ?? 0}</span>
            <span>{t.battles} {story.stats.battles ?? 0}</span>
          </div>
        </section>
      ) : (
        <article className="glass-card p-lg text-sm text-white/70">{t.empty}</article>
      )}

      <section className="space-y-md">
        <h2 className="text-xl font-bold">{t.recent}</h2>
        {entries.length === 0 ? (
          <article className="glass-card p-lg text-sm text-white/70">{t.empty}</article>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-sm md:grid-cols-2 xl:grid-cols-3">
              {pagedEntries.map((entry) => (
                <article
                  key={entry.id}
                  className={`glass-card p-lg ${entry.event_type === "daily_story" ? "border border-cta/50" : ""}`}
                >
                  <p className="mb-xs text-xs uppercase tracking-wider text-cta">{entry.event_type_localized ?? entry.event_type}</p>
                  <h3 className="text-lg font-bold">{entry.title_localized ?? entry.title}</h3>
                  <p className="mt-xs whitespace-pre-line text-sm text-white/85">{entry.content_localized ?? entry.content}</p>
                  <p className="mt-sm text-xs text-white/60">{new Date(entry.created_at).toLocaleString()}</p>
                </article>
              ))}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-sm text-sm text-white/80">
              <label className="inline-flex items-center gap-2">
                <span>{t.pageSize}</span>
                <select
                  className="rounded-lg border border-white/15 bg-black/20 px-sm py-xs text-white"
                  value={pageSize}
                  onChange={(e) => setPageSize(Number(e.target.value))}
                >
                  <option value={6}>6</option>
                  <option value={12}>12</option>
                  <option value={18}>18</option>
                </select>
              </label>
              <div className="flex items-center gap-sm">
                <button
                  className="btn-base btn-secondary"
                  disabled={currentPage <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  {t.prev}
                </button>
                <span>{t.page} {currentPage} / {totalPages}</span>
                <button
                  className="btn-base btn-secondary"
                  disabled={currentPage >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                >
                  {t.next}
                </button>
              </div>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
