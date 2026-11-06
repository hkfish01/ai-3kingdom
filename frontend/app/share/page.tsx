"use client";
/* eslint-disable @next/next/no-img-element */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";
import type { LinkOutbox, LinkStats, LinkToday, TrackedChannelLink } from "@/lib/types";

const CHANNEL_ORDER = ["x", "threads", "xhs", "webhook", "audience", "direct"] as const;

const STATUS_LABEL = {
  zh: {
    prepared: "待發",
    sent: "已推送",
    retrying: "重試中",
    failed: "失敗",
    missing: "無紀錄",
    skipped: "略過"
  },
  en: {
    prepared: "Queued",
    sent: "Sent",
    retrying: "Retrying",
    failed: "Failed",
    missing: "No record",
    skipped: "Skipped"
  }
} as const;

export default function SharePage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [today, setToday] = useState<LinkToday | null>(null);
  const [stats, setStats] = useState<LinkStats | null>(null);
  const [outbox, setOutbox] = useState<LinkOutbox | null>(null);
  const [channel, setChannel] = useState<string>("x");
  const [longForm, setLongForm] = useState(false);
  const [copied, setCopied] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [links, clicks, queue] = await Promise.all([
        apiClient.getPublicLinksToday(locale),
        apiClient.getPublicLinkStats(7),
        apiClient.getPublicOutbox(7)
      ]);
      setToday(links);
      setStats(clicks);
      setOutbox(queue);
      setError("");
      setChannel((current) => (links.links[current] ? current : "x"));
    } catch (err) {
      setError(err instanceof Error ? err.message : zh ? "載入失敗" : "Failed to load");
    }
  }, [locale, zh]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected: TrackedChannelLink | undefined = today?.links[channel];
  const text = selected ? (longForm ? selected.caption_long : selected.caption) : "";

  const copy = async (value: string, key: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
      window.setTimeout(() => setCopied(""), 2000);
    } catch {
      setCopied("");
      setError(zh ? "複製失敗，請手動選取文字" : "Copy failed - please select the text manually");
    }
  };

  const statusLabel = (status: string) => {
    const table = STATUS_LABEL[zh ? "zh" : "en"];
    return (table as Record<string, string>)[status] ?? status;
  };

  return (
    <main className="mx-auto max-w-4xl space-y-lg">
      <section className="glass-card space-y-sm p-xl">
        <span className="rounded-full border border-cta/40 px-2 py-0.5 text-xs text-cta">
          {zh ? "零憑證・每天 08:00 HKT 自動備妥" : "No credentials - ready daily at 08:00 HKT"}
        </span>
        <h1 className="text-2xl font-black">{zh ? "發文台" : "Share desk"}</h1>
        <p className="text-sm text-white/70">
          {zh
            ? "圖卡與文案每天自動產出。選一個通路、複製專屬文案貼出去，連結會自動記下點擊，讓「內容 → 觀眾席 → 分享」看得到成效。"
            : "The card and copy are generated every day. Pick a channel, paste its tracked copy, and clicks are attributed automatically - content to audience to sharing, measurable."}
        </p>
        {today ? (
          <p className="text-xs text-white/55">
            {zh ? `今日產出：${today.date}・${today.headline}` : `Today: ${today.date} - ${today.headline}`}
          </p>
        ) : null}
        {today?.note ? <p className="text-xs text-white/45">{today.note}</p> : null}
      </section>

      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}

      {today && selected ? (
        <>
          <section className="glass-card space-y-md p-lg">
            <div className="flex flex-wrap items-center justify-between gap-sm">
              <h2 className="text-xl font-bold">{zh ? "今日圖卡" : "Today's card"}</h2>
              <a className="btn-base btn-secondary" href={today.image_url} target="_blank" rel="noreferrer">
                {zh ? "下載 PNG" : "Download PNG"}
              </a>
            </div>
            <img
              src={today.image_url}
              alt={today.headline}
              className="w-full rounded-xl border border-white/10"
            />
          </section>

          <section className="glass-card space-y-md p-lg">
            <h2 className="text-xl font-bold">{zh ? "選通路・複製文案" : "Pick a channel and copy"}</h2>
            <div className="flex flex-wrap gap-sm">
              {CHANNEL_ORDER.filter((key) => today.links[key]).map((key) => (
                <button
                  key={key}
                  type="button"
                  className={key === channel ? "btn-base btn-primary" : "btn-base btn-secondary"}
                  onClick={() => {
                    setChannel(key);
                    setLongForm(key === "xhs");
                  }}
                >
                  {today.links[key].label}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-sm text-xs text-white/60">
              <span>{zh ? "文案長度" : "Copy length"}</span>
              <button
                type="button"
                className={!longForm ? "text-cta underline" : ""}
                onClick={() => setLongForm(false)}
              >
                {zh ? "短（X / Threads）" : "Short (X / Threads)"}
              </button>
              <button
                type="button"
                className={longForm ? "text-cta underline" : ""}
                onClick={() => setLongForm(true)}
              >
                {zh ? "長（小紅書）" : "Long (Xiaohongshu)"}
              </button>
            </div>

            <textarea
              readOnly
              value={text}
              rows={8}
              className="w-full rounded-lg border border-white/15 bg-black/30 p-sm text-sm leading-relaxed text-white/90"
            />
            <div className="flex flex-wrap items-center gap-sm">
              <button type="button" className="btn-base btn-primary" onClick={() => void copy(text, "copy")}>
                {copied === "copy" ? (zh ? "已複製" : "Copied") : zh ? "複製文案" : "Copy text"}
              </button>
              <button
                type="button"
                className="btn-base btn-secondary"
                onClick={() => void copy(selected.url, "url")}
              >
                {copied === "url" ? (zh ? "已複製" : "Copied") : zh ? "複製短連結" : "Copy short link"}
              </button>
              <a className="text-xs text-cta underline" href={selected.url} target="_blank" rel="noreferrer">
                {selected.url}
              </a>
            </div>
            <p className="text-xs text-white/50">
              {zh
                ? `這組連結專屬於「${selected.label}」・導向 ${selected.target}・已排除爬蟲點擊 ${selected.human_clicks} 次`
                : `Tracked for ${selected.label} - lands on ${selected.target} - ${selected.human_clicks} human clicks`}
            </p>
          </section>

          <section className="glass-card space-y-md p-lg">
            <div className="flex flex-wrap items-end justify-between gap-sm">
              <h2 className="text-xl font-bold">{zh ? "近 7 日點擊成效" : "Clicks, last 7 days"}</h2>
              <p className="text-xs text-white/60">
                {zh
                  ? `有效點擊 ${stats?.total_human_clicks ?? 0}・含爬蟲 ${stats?.total_clicks ?? 0}`
                  : `${stats?.total_human_clicks ?? 0} human - ${stats?.total_clicks ?? 0} total`}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-sm md:grid-cols-3">
              {CHANNEL_ORDER.filter((key) => today.links[key]).map((key) => {
                const count = stats?.by_channel[key] ?? 0;
                const max = Math.max(1, ...Object.values(stats?.by_channel ?? {}));
                return (
                  <div key={key} className="rounded-lg border border-white/10 p-sm">
                    <div className="flex justify-between text-xs text-white/75">
                      <span>{today.links[key].label}</span>
                      <span className="font-bold text-cta">{count}</span>
                    </div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/10">
                      <div className="h-full bg-cta" style={{ width: `${(count / max) * 100}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-white/50">{stats?.note ?? ""}</p>
            <Link className="btn-base btn-secondary" href="/audience">
              {zh ? "看觀眾席是否在動" : "Check the stands"}
            </Link>
          </section>
        </>
      ) : null}

      <section className="glass-card space-y-md p-lg">
        <h2 className="text-xl font-bold">{zh ? "近 7 日待發佇列" : "Outbox, last 7 days"}</h2>
        {outbox ? (
          <div className="space-y-sm">
            {outbox.items.map((item) => (
              <article key={item.date} className="flex flex-wrap items-center justify-between gap-sm rounded-lg border border-white/10 p-sm">
                <div className="min-w-[12rem] flex-1">
                  <p className="text-xs text-white/55">
                    {item.date}・{statusLabel(item.status)}
                    {item.provisional ? (zh ? "・即時補" : " - live") : ""}
                  </p>
                  <p className="text-sm text-white/85">{item.headline || (zh ? "尚無產出" : "Not generated")}</p>
                </div>
                {item.caption ? (
                  <button
                    type="button"
                    className="btn-base btn-secondary"
                    onClick={() => void copy(item.caption ?? "", item.date)}
                  >
                    {copied === item.date ? (zh ? "已複製" : "Copied") : zh ? "複製當日文案" : "Copy"}
                  </button>
                ) : null}
              </article>
            ))}
          </div>
        ) : null}
        <p className="text-xs text-white/50">
          {zh
            ? "沒填 webhook 時狀態是「待發」：內容照常每天備好，由你手動貼文。填入 CHRONICLE_CARD_WEBHOOK_URLS 後會自動推送到 Discord／n8n。"
            : "Without a webhook the status stays 'Queued': content is prepared daily for manual posting. Set CHRONICLE_CARD_WEBHOOK_URLS to push to Discord / n8n automatically."}
        </p>
      </section>
    </main>
  );
}
