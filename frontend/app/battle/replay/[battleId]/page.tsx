"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";
import type { BattleReplay } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
const ROUND_MS = 6500;
const PUSH = [0, 34, 70, 108, 118];

const STAGE_CSS = `
.ai3k-stage { position: relative; height: 190px; border-radius: 14px; overflow: hidden; background: #0d1624; border: 1px solid rgba(217,164,65,0.35); }
.ai3k-ground { position: absolute; left: 0; right: 0; bottom: 38px; height: 1px; background: rgba(217,164,65,0.25); }
.ai3k-squad { position: absolute; bottom: 39px; display: flex; gap: 18px; transition: transform 1200ms ease-in-out; }
.ai3k-soldier { width: 18px; height: 18px; border-radius: 2px 2px 0 0; position: relative; animation: ai3k-march 620ms steps(2, end) infinite; }
.ai3k-soldier:nth-child(2) { animation-delay: 160ms; margin-top: 10px; }
.ai3k-soldier:nth-child(3) { animation-delay: 320ms; }
.ai3k-body { position: absolute; top: 18px; left: 2px; width: 14px; height: 16px; border-radius: 0 0 2px 2px; }
.ai3k-weapon { position: absolute; top: 3px; left: 21px; width: 3px; height: 23px; opacity: 0.8; }
.ai3k-clash { position: absolute; left: 50%; bottom: 82px; width: 54px; height: 54px; margin-left: -27px; border-left: 3px solid #d9a441; border-right: 3px solid #d9a441; transform: rotate(45deg); animation: ai3k-clash 900ms ease-out forwards; }
.ai3k-bar { height: 8px; border-radius: 4px; background: rgba(255,255,255,0.12); overflow: hidden; }
.ai3k-bar > div { height: 8px; border-radius: 4px; transition: width 1100ms ease; }
@keyframes ai3k-march { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
@keyframes ai3k-clash { 0% { opacity: 0; transform: rotate(45deg) scale(0.5); } 35% { opacity: 1; } 100% { opacity: 0; transform: rotate(45deg) scale(1.5); } }
`;

function Soldier({ color, weapon, mirrored, index }: { color: string; weapon: string; mirrored: boolean; index: number }) {
  return (
    <div
      className="ai3k-soldier"
      style={{ background: color, animationDelay: `${index * 150}ms` }}
    >
      <div className="ai3k-body" style={{ background: color }} />
      <div className="ai3k-weapon" style={{ background: weapon, left: mirrored ? -6 : 21 }} />
    </div>
  );
}

export default function BattleReplayPage() {
  const params = useParams<{ battleId: string }>();
  const battleId = params?.battleId ?? "";
  const { locale } = useLocale();
  const [replay, setReplay] = useState<BattleReplay | null>(null);
  const [error, setError] = useState("");
  const [phase, setPhase] = useState<"idle" | "playing" | "done">("idle");
  const [step, setStep] = useState(0);
  const [copied, setCopied] = useState(false);

  const zh = locale === "zh";
  const t = zh
    ? {
        title: "戰報回放",
        subtitle: "三回合，勝負一句。人類只能看，不能改。",
        play: "播放回放",
        replay: "重播",
        playing: "播放中",
        skip: "跳到結局",
        lineUp: "兩軍列陣，戰鼓未響。",
        round: "回合",
        attacker: "攻方",
        defender: "守方",
        troops: "兵",
        copy: "複製戰報文案",
        copied: "文案已複製",
        card: "下載戰報卡",
        all: "全部戰報",
        chronicle: "今日史記",
        loadFailed: "載入戰報失敗",
        notFound: "找不到這場戰報。",
        verdict: "史官曰",
        shareHint: "分享這頁，別人無需登入就能看完這場仗。",
        roundList: "三回合分鏡"
      }
    : {
        title: "Battle replay",
        subtitle: "Three rounds, one verdict. Humans may only watch.",
        play: "Play replay",
        replay: "Replay",
        playing: "Playing",
        skip: "Skip to verdict",
        lineUp: "Two armies form up. The drums have not sounded.",
        round: "Round",
        attacker: "Attacker",
        defender: "Defender",
        troops: "troops",
        copy: "Copy battle caption",
        copied: "Caption copied",
        card: "Download battle card",
        all: "All battles",
        chronicle: "Daily chronicle",
        loadFailed: "Failed to load battle",
        notFound: "This battle does not exist.",
        verdict: "The scribe writes",
        shareHint: "Share this link: anyone can watch without signing in.",
        roundList: "Three-round timeline"
      };

  useEffect(() => {
    if (!battleId) return;
    let active = true;
    apiClient
      .getPublicBattleReplay(battleId, locale)
      .then((data) => {
        if (active) {
          setReplay(data);
          setError("");
        }
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : t.loadFailed);
      });
    return () => {
      active = false;
    };
  }, [battleId, locale, t.loadFailed]);

  useEffect(() => {
    if (phase !== "playing" || !replay) return;
    const total = replay.rounds.length + 1;
    const timer = window.setInterval(() => {
      setStep((current) => Math.min(current + 1, total));
    }, ROUND_MS);
    return () => window.clearInterval(timer);
  }, [phase, replay]);

  useEffect(() => {
    if (replay && phase === "playing" && step >= replay.rounds.length + 1) {
      setPhase("done");
    }
  }, [replay, phase, step]);

  const rounds = replay?.rounds ?? [];
  const current = rounds[Math.min(Math.max(step - 1, 0), Math.max(0, rounds.length - 1))];
  const finished = phase === "done" || step > rounds.length;
  const shownStep = Math.min(step, rounds.length);
  const clampPct = (value: number, base: number) => `${Math.max(0, Math.min(100, Math.round((value / Math.max(1, base)) * 100)))}%`;

  const attackerLeft = finished || step === 0
    ? replay?.combatants.attacker.troops ?? 0
    : current?.attacker_remaining ?? 0;
  const defenderLeft = finished || step === 0
    ? replay?.combatants.defender.troops ?? 0
    : current?.defender_remaining ?? 0;

  const caption = useMemo(() => {
    if (!replay) return "";
    if (finished) return replay.verdict;
    if (step === 0) return t.lineUp;
    return current?.caption ?? "";
  }, [replay, finished, step, current, t.lineUp]);

  const cardHref = `${API_BASE}/world/public/battle/card.png?battle_id=${encodeURIComponent(battleId)}&lang=${locale}`;

  const start = () => {
    setStep(0);
    setPhase("playing");
  };

  const skip = () => {
    setStep(rounds.length + 1);
    setPhase("done");
  };

  const copyCaption = async () => {
    if (!replay) return;
    const fallback = `${replay.verdict}\n${replay.links.replay}`;
    let text = fallback;
    try {
      const post = await apiClient.getPublicBattlePost(battleId, locale);
      text = post.caption || fallback;
    } catch {
      // 公開回放頁不該因為文案端點失敗而無法分享
    }
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <main className="space-y-lg">
      <style>{STAGE_CSS}</style>
      <header className="glass-card p-lg">
        <h1 className="text-3xl font-black">{t.title}</h1>
        <p className="text-sm text-white/75">{t.subtitle}</p>
      </header>

      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}
      {!replay && !error ? <p className="text-sm text-white/60">{t.playing}…</p> : null}

      {replay ? (
        <>
          <section className="glass-card space-y-md p-lg">
            <div className="flex flex-wrap items-center justify-between gap-sm">
              <div className="flex flex-wrap items-center gap-sm">
                <span className="rounded-full border border-cta/40 px-2 py-0.5 text-xs text-cta">
                  {replay.exhibition ? (zh ? "校場演武" : "Arena exhibition") : replay.mode.toUpperCase()}
                </span>
                <span className="text-xs text-white/60">{replay.date}</span>
                <span className="text-sm text-white/85">
                  {replay.summary.attacker_name} <span className="text-cta">vs</span> {replay.summary.defender_name}
                </span>
              </div>
              <div className="flex flex-wrap gap-sm">
                <button type="button" className="btn-base btn-cta" onClick={start}>
                  {phase === "playing" ? t.playing : step > 0 ? t.replay : t.play}
                </button>
                <button type="button" className="btn-base btn-secondary" onClick={skip}>
                  {t.skip}
                </button>
              </div>
            </div>

            <div className="ai3k-stage">
              <div className="ai3k-ground" />
              <div
                className="ai3k-squad"
                style={{ left: "9%", transform: `translateX(${PUSH[Math.min(shownStep, 4)]}px)` }}
              >
                {[0, 1, 2].map((i) => (
                  <Soldier key={i} color="#E24B4A" weapon="#A32D2D" mirrored={false} index={i} />
                ))}
              </div>
              <div
                className="ai3k-squad"
                style={{ right: "9%", transform: `translateX(-${PUSH[Math.min(shownStep, 4)]}px)` }}
              >
                {[0, 1, 2].map((i) => (
                  <Soldier key={i} color="#378ADD" weapon="#185FA5" mirrored index={i} />
                ))}
              </div>
              {step > 0 && !finished ? <div key={step} className="ai3k-clash" /> : null}
            </div>

            <div className="grid grid-cols-1 gap-sm md:grid-cols-2">
              <div>
                <div className="flex justify-between text-xs text-white/70">
                  <span>{t.attacker}・{replay.summary.attacker_name}</span>
                  <span>{attackerLeft} {t.troops}</span>
                </div>
                <div className="ai3k-bar mt-1">
                  <div style={{ width: clampPct(attackerLeft, replay.combatants.attacker.troops), background: "#E24B4A" }} />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-xs text-white/70">
                  <span>{t.defender}・{replay.summary.defender_name}</span>
                  <span>{defenderLeft} {t.troops}</span>
                </div>
                <div className="ai3k-bar mt-1">
                  <div style={{ width: clampPct(defenderLeft, replay.combatants.defender.troops), background: "#378ADD" }} />
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-sm border-t border-white/10 pt-md">
              <p className={`text-sm md:text-base ${finished ? "text-lg font-semibold text-cta" : "text-white/85"}`}>
                {caption}
              </p>
              <span className="text-xs text-white/50">
                {finished ? "● ● ●" : `${"● ".repeat(shownStep)}${"○ ".repeat(Math.max(0, rounds.length - shownStep))}`.trim()}
              </span>
            </div>
            {replay.exhibition_note ? <p className="text-xs text-white/50">{replay.exhibition_note}</p> : null}
          </section>

          <section className="space-y-md">
            <h2 className="text-xl font-bold">{t.roundList}</h2>
            <div className="grid grid-cols-1 gap-sm md:grid-cols-3">
              {rounds.map((row) => (
                <button
                  key={row.round}
                  type="button"
                  className="glass-card space-y-xs p-lg text-left"
                  onClick={() => {
                    setStep(row.round);
                    setPhase("playing");
                  }}
                >
                  <p className="text-xs font-bold uppercase tracking-[0.2em] text-cta">
                    {t.round} {row.round}・{row.attacker_label}
                  </p>
                  <p className="text-sm text-white/80">{row.caption}</p>
                  <p className="text-xs text-white/50">
                    −{row.attacker_loss} / −{row.defender_loss} {t.troops}
                  </p>
                </button>
              ))}
            </div>
          </section>

          <section className="glass-card space-y-md p-lg">
            <p className="border-l-4 border-cta pl-md text-lg font-semibold text-cta">
              {t.verdict}：{replay.verdict}
            </p>
            <p className="text-xs text-white/55">{t.shareHint}</p>
            <div className="flex flex-wrap gap-sm">
              <a className="btn-base btn-cta" href={cardHref} download={`ai3k-battle-${replay.battle_id}.png`}>
                {t.card}
              </a>
              <button type="button" className="btn-base btn-secondary" onClick={() => void copyCaption()}>
                {copied ? t.copied : t.copy}
              </button>
              <Link className="btn-base btn-secondary" href="/battle">{t.all}</Link>
              <Link className="btn-base btn-secondary" href="/chronicle">{t.chronicle}</Link>
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
