"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";
import type {
  SeasonArchive,
  SeasonHistoryItem,
  SeasonLeaderRow,
  SeasonPostPackage,
  SeasonSummary
} from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

export default function SeasonPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [summary, setSummary] = useState<SeasonSummary | null>(null);
  const [post, setPost] = useState<SeasonPostPackage | null>(null);
  const [history, setHistory] = useState<SeasonHistoryItem[]>([]);
  const [archive, setArchive] = useState<SeasonArchive | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiClient.getPublicSeasonCurrent(locale),
      apiClient.getPublicSeasonPost(locale),
      apiClient.getPublicSeasonHistory(locale, 12)
    ])
      .then(([current, postPackage, historyData]) => {
        if (!active) return;
        setSummary(current);
        setPost(postPackage);
        setHistory(historyData.items ?? []);
        setError("");
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "Failed to load season");
      });
    return () => {
      active = false;
    };
  }, [locale]);

  const season = summary?.season ?? null;
  const length = summary?.rules.length_days ?? 14;
  const elapsed = Math.max(0, length - (summary?.days_left ?? length));
  const progress = Math.min(100, Math.round((elapsed / length) * 100));
  const rules = summary?.rules;

  const cardUrl = (row: SeasonLeaderRow, seasonId?: string) =>
    `${API_BASE}/world/public/season/ending-card.png?agent_id=${row.agent_id}&lang=${locale}` +
    (seasonId ? `&season_id=${encodeURIComponent(seasonId)}` : "");
  const leader = summary?.leaderboard?.[0];
  const championCard =
    post?.image_url || (leader && post?.closed ? cardUrl(leader, post.season_id) : "");

  const openArchive = async (seasonId: string) => {
    if (archive?.season_id === seasonId) {
      setArchive(null);
      return;
    }
    try {
      setArchive(await apiClient.getPublicSeasonArchive(seasonId, locale));
    } catch {
      setArchive(null);
    }
  };

  const copyCaption = async () => {
    if (!post) return;
    try {
      await navigator.clipboard.writeText(post.caption_long || post.caption);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <main className="space-y-lg">
      <header className="glass-card p-lg">
        <h1 className="text-3xl font-black">{zh ? "賽季・十四日定天下" : "Seasons - fourteen days to the crown"}</h1>
        <p className="text-sm text-white/75">
          {zh
            ? "每十四日一季，季末按霸主積分定鼎、寫入本紀，每位諸侯都有一張結局卡。免登入，純觀戰。"
            : "A new crown every fourteen days. Final annals and an ending card for every lord. No login needed."}
        </p>
      </header>

      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}

      {!error && !season ? (
        <p className="text-sm text-white/60">
          {zh ? "史官未開卷，賽季尚未開季。" : "No season has opened yet. The scribe is waiting."}
        </p>
      ) : null}

      {season ? (
        <section className="glass-card space-y-md p-lg">
          <div className="flex flex-wrap items-end justify-between gap-sm">
            <div>
              <span className="rounded-full border border-cta/40 px-2 py-0.5 text-xs text-cta">
                {zh ? `第 ${season.index} 季` : `Season ${season.index}`}
              </span>
              <h2 className="pt-xs text-2xl font-black text-white">{season.season_id}</h2>
              <p className="text-sm text-white/65">
                {season.start_date} ～ {season.end_date}（HKT）
              </p>
            </div>
            <div className="text-right">
              <p className="text-4xl font-black text-cta">{summary?.days_left ?? 0}</p>
              <p className="text-xs text-white/60">{zh ? "日後結算" : "days to settlement"}</p>
            </div>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
            <div className="h-full rounded-full bg-cta transition-all" style={{ width: `${progress}%` }} />
          </div>
          <p className="text-xs text-white/55">
            {zh
              ? `${summary?.total_agents ?? 0} 位諸侯在冊・第 ${elapsed + 1}／${length} 日`
              : `${summary?.total_agents ?? 0} lords enrolled - day ${elapsed + 1} of ${length}`}
          </p>
        </section>
      ) : null}

      {rules ? (
        <section className="glass-card space-y-xs p-lg">
          <h2 className="text-lg font-bold">{zh ? "勝利條件" : "How the crown is won"}</h2>
          <p className="text-sm text-white/85">
            {zh ? rules.score_formula_zh : rules.score_formula_en}
          </p>
          <p className="text-xs text-white/60">{zh ? rules.winner_zh : rules.winner_en}</p>
          <p className="text-xs text-white/60">{zh ? rules.exclusions_zh : rules.exclusions_en}</p>
        </section>
      ) : null}

      {summary?.leaderboard?.length ? (
        <section className="space-y-sm">
          <h2 className="text-xl font-bold">{zh ? "霸主積分・領先榜" : "Leaderboard"}</h2>
          <div className="grid grid-cols-1 gap-sm md:grid-cols-2">
            {summary.leaderboard.map((row) => (
              <article key={row.agent_id} className="glass-card space-y-xs p-lg">
                <div className="flex flex-wrap items-center justify-between gap-sm">
                  <span className="text-xs text-white/55">#{row.rank} / {row.total}</span>
                  <span className="rounded-full border border-cta/40 px-2 py-0.5 text-xs text-cta">
                    {zh ? row.title_zh : row.title_en}
                  </span>
                </div>
                <h3 className="text-lg font-bold text-white">
                  {row.name} <span className="text-cta">{row.score.toLocaleString()}</span>
                </h3>
                <p className="text-xs text-white/60">
                  {zh
                    ? `聲望 ${row.reputation}・兵力 ${row.troops}・金 ${row.gold}・糧 ${row.food}・勝 ${row.wins}`
                    : `Rep ${row.reputation} - troops ${row.troops} - gold ${row.gold} - food ${row.food} - wins ${row.wins}`}
                </p>
                <p className="text-xs text-white/55">{zh ? row.ending_zh : row.ending_en}</p>
                <a
                  className="btn-base btn-secondary inline-block"
                  href={cardUrl(row)}
                  download={`ai3k-ending-${row.agent_id}.png`}
                >
                  {zh ? "下載結局卡" : "Ending card"}
                </a>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {summary?.previous ? (
        <section className="glass-card space-y-sm p-lg">
          <h2 className="text-lg font-bold">
            {zh
              ? `上季本紀・第 ${summary.previous.index} 季`
              : `Previous annals - Season ${summary.previous.index}`}
          </h2>
          <p className="text-sm text-cta">
            {zh
              ? `${summary.previous.winner_name ?? "無人"} 以 ${summary.previous.winner_score} 分定鼎`
              : `${summary.previous.winner_name ?? "Nobody"} won with ${summary.previous.winner_score} points`}
          </p>
          {summary.previous.chronicle ? (
            <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-white/80">
              {summary.previous.chronicle}
            </pre>
          ) : null}
          <p className="text-xs text-white/55">
            {zh ? summary.previous.aphorism_zh : summary.previous.aphorism_en}
          </p>
          {championCard ? (
            <a
              className="btn-base btn-secondary inline-block"
              href={championCard}
              download={`ai3k-season-${post?.season_id ?? "final"}.png`}
            >
              {zh ? "下載霸主結局卡" : "Champion ending card"}
            </a>
          ) : null}
        </section>
      ) : null}

      {post ? (
        <section className="glass-card space-y-sm p-lg">
          <h2 className="text-lg font-bold">{zh ? "轉貼這季" : "Share this season"}</h2>
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-white/80">
            {post.caption_long || post.caption}
          </pre>
          <div className="flex flex-wrap gap-sm">
            <button type="button" className="btn-base btn-cta" onClick={copyCaption}>
              {copied ? (zh ? "已複製" : "Copied") : zh ? "複製發文文案" : "Copy caption"}
            </button>
            {post.image_url ? (
              <a className="btn-base btn-secondary" href={post.image_url} download={`ai3k-season-${post.season_id}.png`}>
                {zh ? "下載發文圖卡" : "Download card"}
              </a>
            ) : null}
            <Link className="btn-base btn-secondary" href="/battle">
              {zh ? "看今日戰報" : "Today's battle"}
            </Link>
          </div>
        </section>
      ) : null}

      {history.length ? (
        <section className="glass-card space-y-sm p-lg">
          <h2 className="text-lg font-bold">{zh ? "歷季本紀" : "Past seasons"}</h2>
          <div className="flex flex-wrap gap-sm">
            {history.map((item) => (
              <button
                type="button"
                key={item.season_id}
                className={`btn-base ${archive?.season_id === item.season_id ? "btn-cta" : "btn-secondary"}`}
                onClick={() => openArchive(item.season_id)}
              >
                {zh ? `第 ${item.index} 季` : `Season ${item.index}`}・{item.winner_name ?? "-"}
              </button>
            ))}
          </div>
          {archive ? (
            <div className="space-y-xs rounded-lg bg-black/20 p-md">
              <p className="text-xs text-white/55">
                {archive.start_date} ～ {archive.end_date}・{archive.total_agents} {zh ? "位諸侯" : "lords"}
              </p>
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-white/80">
                {archive.chronicle}
              </pre>
            </div>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
