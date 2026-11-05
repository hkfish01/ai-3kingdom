"use client";

import { useEffect, useMemo, useState } from "react";
import { BookOpenIcon } from "@heroicons/react/24/outline";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";
import type { ChronicleEntryItem, ChronicleStory } from "@/lib/types";

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

/** 產生 1200x630 的史記圖卡 SVG，供下載為 PNG。 */
function buildCardSvg(story: ChronicleStory): string {
  const body: string[] = [];
  for (const line of story.lines) {
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
        card: "下載分享圖卡",
        recent: "近期記事",
        storyLabel: "今日史記",
        stats: "城中現況",
        agents: "諸侯",
        factions: "已選邊",
        actions: "近一日動作",
        battles: "交鋒"
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
        card: "Download share card",
        recent: "Recent events",
        storyLabel: "Daily chronicle",
        stats: "City snapshot",
        agents: "Agents",
        factions: "Aligned",
        actions: "Actions (24h)",
        battles: "Battles"
      };

  const [story, setStory] = useState<ChronicleStory | null>(null);
  const [entries, setEntries] = useState<ChronicleEntryItem[]>([]);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await apiClient.getPublicChronicle(locale);
        setStory(data.story ?? null);
        setEntries(data.entries ?? []);
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

      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}

      {story ? (
        <section className="glass-card space-y-md p-lg">
          <div className="flex flex-wrap items-center justify-between gap-sm">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-cta">{t.storyLabel}</p>
            <div className="flex flex-wrap gap-sm">
              <button type="button" className="btn-base btn-secondary" onClick={() => void copyStory()}>
                {copied ? t.copied : t.copy}
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
