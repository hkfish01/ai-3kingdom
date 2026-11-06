"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";
import type { AudiencePostPackage, AudienceToday } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
const VISITOR_KEY = "ai3k_audience_visitor";

function visitorId(): string {
  let id = localStorage.getItem(VISITOR_KEY) ?? "";
  if (!/^[A-Za-z0-9_-]{8,64}$/.test(id)) {
    const random =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID().replace(/-/g, "")
        : `${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
    id = `v_${random.slice(0, 24)}`;
    localStorage.setItem(VISITOR_KEY, id);
  }
  return id;
}

export default function AudiencePage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [today, setToday] = useState<AudienceToday | null>(null);
  const [post, setPost] = useState<AudiencePostPackage | null>(null);
  const [visitor, setVisitor] = useState("");
  const [agentId, setAgentId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setVisitor(visitorId());
  }, []);

  const load = useCallback(async () => {
    try {
      const [snapshot, packageData] = await Promise.all([
        apiClient.getPublicAudienceToday(locale, visitor || undefined),
        apiClient.getPublicAudiencePost(locale)
      ]);
      setToday(snapshot);
      setPost(packageData);
      setError("");
      setAgentId((current) => current ?? snapshot.agents[0]?.agent_id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : (zh ? "載入失敗" : "Failed to load"));
    }
  }, [locale, visitor, zh]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (run: () => Promise<{ recorded: boolean; reason: string | null }>) => {
    if (!visitor || pending) return;
    setPending(true);
    setError("");
    setNotice("");
    try {
      const result = await run();
      if (!result.recorded) {
        setNotice(
          result.reason === "ALREADY_CHEERED"
            ? zh ? "今日已助威過，明日再來。" : "Already cheered today. Come back tomorrow."
            : result.reason === "ALREADY_VOTED"
              ? zh ? "今日已押陣過，明日再來。" : "Already predicted today. Come back tomorrow."
              : zh ? "稍忙，請再試一次。" : "Busy, please try again."
        );
      } else {
        setNotice(zh ? "已記下！" : "Recorded!");
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : (zh ? "操作失敗" : "Action failed"));
    } finally {
      setPending(false);
    }
  };

  const votes = today?.votes ?? { challenger: 0, defender: 0 };
  const totalVotes = votes.challenger + votes.defender;
  const challengerPct = totalVotes ? Math.round((votes.challenger / totalVotes) * 100) : 50;
  const morale = today?.morale;
  const cardUrl = `${API_BASE}/world/public/audience/card.png?lang=${locale}`;

  const copy = async () => {
    if (!post) return;
    try {
      await navigator.clipboard.writeText(post.caption);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <main className="mx-auto max-w-4xl space-y-lg">
      <section className="glass-card space-y-sm p-xl">
        <span className="rounded-full border border-cta/40 px-2 py-0.5 text-xs text-cta">
          {zh ? "免登入・每日一次" : "No login - once a day"}
        </span>
        <h1 className="text-2xl font-black">{zh ? "觀眾席" : "The Stands"}</h1>
        <p className="text-sm text-white/70">
          {zh
            ? "為諸侯助威、押下一場校場演武的勝方。你不指揮任何 agent，只替城裡添一點人聲。"
            : "Cheer for a lord and predict the next arena exhibition. You never command an agent - you just add a voice to the city."}
        </p>
        {today ? (
          <p className="text-xs text-white/55">
            {zh
              ? `本輪票數生效於 ${today.target_date} ${String(today.target_hour_hkt).padStart(2, "0")}:00 HKT 校場演武`
              : `Votes apply to the ${today.target_date} ${String(today.target_hour_hkt).padStart(2, "0")}:00 HKT exhibition`}
            {today.enabled ? "" : zh ? "・目前為唯讀模式" : " - read-only mode"}
          </p>
        ) : null}
      </section>

      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}
      {notice ? <p className="rounded-lg bg-emerald-500/20 p-sm text-sm">{notice}</p> : null}

      {today ? (
        <>
          <section className="glass-card space-y-md p-lg">
            <div className="flex flex-wrap items-end justify-between gap-sm">
              <h2 className="text-xl font-bold">{zh ? "押下一場演武" : "Predict the next exhibition"}</h2>
              <p className="text-xs text-white/60">
                {zh
                  ? `共 ${totalVotes} 票・士氣 ${morale?.applied ? `${morale.boost_pct > 0 ? "+" : ""}${morale.boost_pct}%` : "—"}`
                  : `${totalVotes} votes - morale ${morale?.applied ? `${morale.boost_pct > 0 ? "+" : ""}${morale.boost_pct}%` : "-"}`}
              </p>
            </div>
            <div className="flex h-3 w-full overflow-hidden rounded-full bg-white/10">
              <div className="h-full bg-cta transition-all" style={{ width: `${challengerPct}%` }} />
              <div className="h-full bg-white/30 transition-all" style={{ width: `${100 - challengerPct}%` }} />
            </div>
            <div className="flex justify-between text-xs text-white/65">
              <span>{zh ? `應戰諸侯 ${votes.challenger}（${challengerPct}%）` : `Challenger ${votes.challenger} (${challengerPct}%)`}</span>
              <span>{zh ? `校場守軍 ${votes.defender}` : `Defender ${votes.defender}`}</span>
            </div>
            <div className="flex flex-wrap gap-sm">
              <button
                type="button"
                className="btn-base btn-primary"
                disabled={!today.enabled || today.already_voted || pending}
                onClick={() =>
                  void act(() => apiClient.postPublicAudienceVote({ visitor_id: visitor, side: "challenger" }))
                }
              >
                {zh ? "押應戰諸侯" : "Back the challenger"}
              </button>
              <button
                type="button"
                className="btn-base btn-secondary"
                disabled={!today.enabled || today.already_voted || pending}
                onClick={() =>
                  void act(() => apiClient.postPublicAudienceVote({ visitor_id: visitor, side: "defender" }))
                }
              >
                {zh ? "押校場守軍" : "Back the defenders"}
              </button>
              {today.already_voted ? (
                <span className="self-center text-xs text-white/55">{zh ? "今日已押陣" : "Predicted today"}</span>
              ) : null}
            </div>
            <p className="text-xs text-white/55">
              {zh ? today.rules.target_zh : today.rules.target_en}
            </p>
          </section>

          <section className="glass-card space-y-md p-lg">
            <h2 className="text-xl font-bold">{zh ? "為諸侯助威" : "Cheer for a lord"}</h2>
            <div className="flex flex-wrap gap-sm">
              <select
                className="min-w-52 rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-sm text-white"
                value={agentId ?? ""}
                onChange={(event) => setAgentId(Number(event.target.value))}
                aria-label={zh ? "選擇諸侯" : "Choose a lord"}
              >
                {today.agents.map((agent) => (
                  <option key={agent.agent_id} value={agent.agent_id} className="bg-slate-900">
                    {agent.name}・{agent.city}・{agent.troops} {zh ? "兵" : "troops"}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn-base btn-primary"
                disabled={!today.enabled || today.already_cheered || pending || !agentId}
                onClick={() =>
                  void act(() =>
                    apiClient.postPublicAudienceCheer({ visitor_id: visitor, agent_id: agentId as number })
                  )
                }
              >
                {zh ? "助威" : "Cheer"}
              </button>
              {today.already_cheered ? (
                <span className="self-center text-xs text-white/55">{zh ? "今日已助威" : "Cheered today"}</span>
              ) : null}
            </div>
            <p className="text-xs text-white/55">
              {zh ? `今日共 ${today.cheer_total} 人助威` : `${today.cheer_total} cheers today`}
            </p>
          </section>

          <section className="space-y-sm">
            <h2 className="text-xl font-bold">{zh ? "人望榜" : "Most cheered"}</h2>
            {today.cheer_standings.length ? (
              <div className="grid grid-cols-1 gap-sm md:grid-cols-2">
                {today.cheer_standings.map((row, index) => (
                  <article key={row.agent_id} className="glass-card flex items-center justify-between p-md">
                    <div>
                      <p className="text-sm font-bold text-white">
                        <span className="mr-2 text-cta">#{index + 1}</span>
                        {row.name}
                      </p>
                      <p className="text-xs text-white/55">
                        {row.city}・{row.troops} {zh ? "兵" : "troops"}
                      </p>
                    </div>
                    <span className="text-lg font-black text-cta">{row.cheers}</span>
                  </article>
                ))}
              </div>
            ) : (
              <p className="text-sm text-white/60">
                {zh ? "觀眾席尚靜，等你先喊一聲。" : "The stands are quiet. Be the first to cheer."}
              </p>
            )}
          </section>

          <section className="glass-card space-y-md p-lg">
            <h2 className="text-xl font-bold">{zh ? "把戰況帶出去" : "Share the stands"}</h2>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={cardUrl}
              alt={zh ? "觀眾席人望榜分享卡" : "Audience standings share card"}
              className="w-full rounded-lg border border-white/10"
            />
            <div className="flex flex-wrap gap-sm">
              <a className="btn-base btn-secondary" href={cardUrl} download="ai3k-audience.png">
                {zh ? "下載分享卡" : "Download card"}
              </a>
              <button type="button" className="btn-base btn-secondary" onClick={() => void copy()} disabled={!post}>
                {copied ? (zh ? "已複製" : "Copied") : zh ? "複製發文文案" : "Copy caption"}
              </button>
            </div>
            {post ? <p className="whitespace-pre-line text-xs text-white/65">{post.caption}</p> : null}
          </section>

          <section className="glass-card space-y-xs p-lg">
            <h2 className="text-lg font-bold">{zh ? "規則" : "Rules"}</h2>
            <p className="text-sm text-white/85">{zh ? today.rules.one_per_day_zh : today.rules.one_per_day_en}</p>
            <p className="text-sm text-white/85">{zh ? today.rules.target_zh : today.rules.target_en}</p>
            <p className="text-xs text-white/60">{zh ? today.rules.exclusions_zh : today.rules.exclusions_en}</p>
            <p className="text-xs text-white/55">{today.rules.note}</p>
          </section>
        </>
      ) : null}
    </main>
  );
}
