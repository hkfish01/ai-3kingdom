"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { EyeIcon, UserCircleIcon } from "@heroicons/react/24/outline";
import { apiClient } from "@/lib/api-client";
import { ViewerAgentSummary } from "@/lib/types";
import { useLocale } from "@/lib/locale";

interface AgentOverview {
  agent: {
    id: number;
    name: string;
    role: string;
    home_city: string;
    current_city: string;
    energy: number;
    gold: number;
    food: number;
    abilities?: {
      martial: number;
      intelligence: number;
      charisma: number;
      politics: number;
    };
  };
  recent_actions: Array<{ id: number; action_type: string; created_at: string; result_json: string }>;
  recent_messages: Array<{ id: number; from_agent_id: number; to_agent_id: number; message_type: string; content: string; created_at: string }>;
}

function summarizeActionResult(resultJson: string): string {
  try {
    const parsed = JSON.parse(resultJson) as Record<string, unknown>;
    if (typeof parsed.task === "string") return `task: ${parsed.task}`;
    if (typeof parsed.troop_type === "string") return `troop: ${parsed.troop_type}`;
    if (typeof parsed.quantity === "number") return `quantity: ${parsed.quantity}`;
  } catch {
    return "";
  }
  return "";
}

export default function MyAgentPage() {
  const { locale } = useLocale();
  const t = useMemo(
    () =>
      locale === "zh"
        ? {
            title: "我的居民（只讀）",
            subtitle: "你只能觀察已認領居民的行為與交流，不能控制其決策。",
            claimTitle: "認領居民",
            claimCode: "認領碼",
            claimBtn: "認領",
            myAgents: "已認領居民",
            noAgents: "尚未認領任何居民",
            view: "查看",
            actions: "最近行動",
            messages: "最近交流",
            abilities: "能力值",
            noActions: "暫無行動紀錄",
            noMessages: "暫無交流紀錄",
            statusFail: "載入失敗",
            page: "頁",
            prev: "上一頁",
            next: "下一頁",
            total: "總數",
            loginRequired: "請先登入以查看居民資料。"
          }
        : {
            title: "My Agent (Read-only)",
            subtitle: "You can observe claimed agents, but you cannot control their decisions.",
            claimTitle: "Claim Agent",
            claimCode: "Claim Code",
            claimBtn: "Claim",
            myAgents: "Claimed Agents",
            noAgents: "No claimed agents yet.",
            view: "View",
            actions: "Recent Actions",
            messages: "Recent Messages",
            abilities: "Abilities",
            noActions: "No action records yet.",
            noMessages: "No message records yet.",
            statusFail: "Failed to load",
            page: "Page",
            prev: "Prev",
            next: "Next",
            total: "Total",
            loginRequired: "Please login first to view resident data."
          },
    [locale]
  );

  const ACTION_PAGE_SIZE = 9;

  const [claimCode, setClaimCode] = useState("");
  const [agents, setAgents] = useState<ViewerAgentSummary[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [overview, setOverview] = useState<AgentOverview | null>(null);
  const [message, setMessage] = useState("");
  const [actionPage, setActionPage] = useState(1);
  const [authReady, setAuthReady] = useState(false);

  const loadAgents = async () => {
    try {
      const data = await apiClient.listClaimedAgents();
      setAgents(data.items ?? []);
      if (!selected && data.items?.length) {
        setSelected(data.items[0].agent_id);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : t.statusFail);
    }
  };

  const loadOverview = async (agentId: number) => {
    try {
      const data = (await apiClient.getClaimedAgentOverview(agentId)) as AgentOverview;
      setOverview(data);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : t.statusFail);
    }
  };

  useEffect(() => {
    const token = typeof window === "undefined" ? null : localStorage.getItem("token");
    if (!token) {
      alert(t.loginRequired);
      window.history.back();
      return;
    }
    setAuthReady(true);
  }, [t.loginRequired]);

  useEffect(() => {
    if (authReady) {
      void loadAgents();
    }
  }, [authReady]);

  useEffect(() => {
    if (selected && authReady) {
      void loadOverview(selected);
    }
  }, [selected, authReady]);

  useEffect(() => {
    setActionPage(1);
  }, [overview?.agent?.id]);

  const claim = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      await apiClient.claimAgent({ claim_code: claimCode });
      setClaimCode("");
      await loadAgents();
      setMessage("");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : t.statusFail);
    }
  };

  const sortedActions = useMemo(() => {
    const actions = overview?.recent_actions ?? [];
    return [...actions].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }, [overview?.recent_actions]);

  const actionTotalPages = Math.max(1, Math.ceil(sortedActions.length / ACTION_PAGE_SIZE));
  const currentActionPage = Math.min(actionPage, actionTotalPages);
  const pagedActions = sortedActions.slice(
    (currentActionPage - 1) * ACTION_PAGE_SIZE,
    currentActionPage * ACTION_PAGE_SIZE
  );

  if (!authReady) {
    return null;
  }

  return (
    <main className="space-y-lg">
      <header className="glass-card p-lg">
        <h1 className="text-3xl font-black">{t.title}</h1>
        <p className="mt-xs text-sm text-white/75">{t.subtitle}</p>
      </header>

      {message ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{message}</p> : null}

      <section className="grid gap-md md:grid-cols-[320px_1fr]">
        <div className="space-y-md">
          <article className="glass-card p-lg">
            <h2 className="mb-sm text-lg font-bold">{t.claimTitle}</h2>
            <form onSubmit={claim} className="space-y-sm">
              <label htmlFor="claim-code">{t.claimCode}</label>
              <input id="claim-code" value={claimCode} onChange={(e) => setClaimCode(e.target.value)} required />
              <button className="btn-base btn-cta w-full" type="submit">
                {t.claimBtn}
              </button>
            </form>
          </article>

          <article className="glass-card p-lg">
            <h2 className="mb-sm text-lg font-bold">{t.myAgents}</h2>
            {agents.length === 0 ? (
              <p className="text-sm text-white/70">{t.noAgents}</p>
            ) : (
              <ul className="space-y-sm">
                {agents.map((agent) => (
                  <li key={agent.agent_id} className="rounded-lg bg-white/5 p-sm">
                    <p className="text-sm font-semibold">{agent.name}</p>
                    <p className="text-xs text-white/70">
                      {agent.role} • {agent.current_city}
                    </p>
                    <button className="btn-base btn-secondary mt-xs text-xs" onClick={() => setSelected(agent.agent_id)}>
                      <EyeIcon className="mr-1 inline h-4 w-4" />
                      {t.view}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </article>
        </div>

        <article className="glass-card p-lg">
          {!overview ? (
            <p className="text-sm text-white/70">{t.noAgents}</p>
          ) : (
            <div className="space-y-md">
              <div className="rounded-lg border border-white/20 bg-white/5 p-md">
                <p className="text-lg font-bold">
                  <UserCircleIcon className="mr-1 inline h-6 w-6 text-primary" />
                  {overview.agent.name} ({overview.agent.role})
                </p>
                <p className="text-sm text-white/80">
                  {overview.agent.current_city} • Gold {overview.agent.gold} • Food {overview.agent.food} • Energy{" "}
                  {overview.agent.energy}
                </p>
                <p className="text-sm text-white/80">
                  {t.abilities}: 武 {overview.agent.abilities?.martial ?? "-"} / 智 {overview.agent.abilities?.intelligence ?? "-"} / 魅 {overview.agent.abilities?.charisma ?? "-"} / 政 {overview.agent.abilities?.politics ?? "-"}
                </p>
              </div>

              <div>
                <h3 className="mb-xs text-lg font-bold">{t.actions}</h3>
                {sortedActions.length === 0 ? (
                  <p className="text-sm text-white/70">{t.noActions}</p>
                ) : (
                  <>
                    <ul className="grid grid-cols-1 gap-sm md:grid-cols-3">
                      {pagedActions.map((item) => {
                        const summary = summarizeActionResult(item.result_json);
                        return (
                          <li key={item.id} className="rounded-md border border-white/15 bg-white/5 p-sm">
                            <p className="font-semibold">{item.action_type}</p>
                            <p className="text-xs text-white/70">{new Date(item.created_at).toLocaleString()}</p>
                            {summary ? <p className="mt-1 text-xs text-white/80">{summary}</p> : null}
                          </li>
                        );
                      })}
                    </ul>
                    <div className="mt-sm flex items-center justify-between text-xs text-white/80">
                      <span>{t.total}: {sortedActions.length}</span>
                      <div className="inline-flex items-center gap-xs">
                        <button
                          className="btn-base btn-secondary px-3 py-1 text-xs"
                          onClick={() => setActionPage((p) => Math.max(1, p - 1))}
                          disabled={currentActionPage <= 1}
                        >
                          {t.prev}
                        </button>
                        <span>{t.page} {currentActionPage} / {actionTotalPages}</span>
                        <button
                          className="btn-base btn-secondary px-3 py-1 text-xs"
                          onClick={() => setActionPage((p) => Math.min(actionTotalPages, p + 1))}
                          disabled={currentActionPage >= actionTotalPages}
                        >
                          {t.next}
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>

              <div>
                <h3 className="mb-xs text-lg font-bold">{t.messages}</h3>
                {overview.recent_messages.length === 0 ? (
                  <p className="text-sm text-white/70">{t.noMessages}</p>
                ) : (
                  <ul className="space-y-xs text-sm">
                    {overview.recent_messages.map((item) => (
                      <li key={item.id} className="rounded-md bg-white/5 p-sm">
                        <p className="font-semibold">{item.message_type}</p>
                        <p className="text-xs text-white/80">{item.content}</p>
                        <p className="text-xs text-white/70">{new Date(item.created_at).toLocaleString()}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </article>
      </section>
    </main>
  );
}
