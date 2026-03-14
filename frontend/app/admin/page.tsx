"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { ShieldCheckIcon } from "@heroicons/react/24/outline";
import { apiClient } from "@/lib/api-client";
import { AdminAgentRow, AdminUserRow } from "@/lib/types";
import { useLocale } from "@/lib/locale";

export default function AdminPage() {
  const { locale } = useLocale();
  const t = useMemo(() => (locale === "zh"
    ? {
        title: "管理平台",
        denied: "你不是管理員或尚未登入。",
        users: "用戶",
        agents: "代理",
        refresh: "刷新",
        delete: "刪除",
        resetPassword: "重設密碼",
        resetPasswordPlaceholder: "新密碼",
        loadFailed: "載入失敗",
        actionFailed: "操作失敗",
        done: "已完成"
      }
    : {
        title: "Admin Panel",
        denied: "You are not an admin or not logged in.",
        users: "Users",
        agents: "Agents",
        refresh: "Refresh",
        delete: "Delete",
        resetPassword: "Reset Password",
        resetPasswordPlaceholder: "New password",
        loadFailed: "Failed to load",
        actionFailed: "Action failed",
        done: "Done"
      }), [locale]);

  const [allowed, setAllowed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [agents, setAgents] = useState<AdminAgentRow[]>([]);
  const [resetPwdMap, setResetPwdMap] = useState<Record<number, string>>({});

  const load = async () => {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const me = await apiClient.getMe();
      if (!me.is_admin) {
        setAllowed(false);
        return;
      }
      setAllowed(true);
      const data = await apiClient.adminOverview();
      setUsers(data.users);
      setAgents(data.agents);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.loadFailed);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const onDeleteUser = async (userId: number) => {
    setError("");
    setMessage("");
    try {
      await apiClient.adminDeleteUser(userId);
      setMessage(t.done);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.actionFailed);
    }
  };

  const onDeleteAgent = async (agentId: number) => {
    setError("");
    setMessage("");
    try {
      await apiClient.adminDeleteAgent(agentId);
      setMessage(t.done);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.actionFailed);
    }
  };

  const onResetPassword = async (event: FormEvent<HTMLFormElement>, userId: number) => {
    event.preventDefault();
    const newPassword = resetPwdMap[userId] ?? "";
    if (!newPassword) {
      return;
    }
    setError("");
    setMessage("");
    try {
      await apiClient.adminResetUserPassword(userId, { new_password: newPassword });
      setMessage(t.done);
      setResetPwdMap((prev) => ({ ...prev, [userId]: "" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t.actionFailed);
    }
  };

  return (
    <main className="space-y-lg">
      <section className="glass-card p-lg">
        <div className="flex items-center justify-between gap-sm">
          <h1 className="flex items-center gap-sm text-3xl font-black">
            <ShieldCheckIcon className="h-8 w-8 text-cta" aria-hidden="true" />
            {t.title}
          </h1>
          <button className="btn-base btn-secondary" onClick={() => void load()}>{t.refresh}</button>
        </div>
      </section>

      {loading ? <p className="text-sm text-white/75">Loading...</p> : null}
      {!loading && !allowed ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{t.denied}</p> : null}
      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}
      {message ? <p className="rounded-lg bg-emerald-500/20 p-sm text-sm">{message}</p> : null}

      {allowed ? (
        <section className="grid gap-md xl:grid-cols-2">
          <article className="glass-card p-md">
            <h2 className="mb-sm text-xl font-bold text-primary">{t.users}</h2>
            <div className="space-y-sm">
              {users.map((u) => (
                <div key={u.id} className="rounded-lg border border-white/15 bg-white/5 p-sm text-sm">
                  <p className="font-semibold">#{u.id} {u.username} {u.is_admin ? "(admin)" : ""}</p>
                  <p className="text-white/80">{u.email}</p>
                  <p className="text-white/70">agents: {u.agent_count}</p>
                  <form className="mt-xs flex flex-wrap gap-xs" onSubmit={(e) => void onResetPassword(e, u.id)}>
                    <input
                      type="password"
                      value={resetPwdMap[u.id] ?? ""}
                      onChange={(e) => setResetPwdMap((prev) => ({ ...prev, [u.id]: e.target.value }))}
                      placeholder={t.resetPasswordPlaceholder}
                      minLength={8}
                      pattern="^[\\x21-\\x7E]+$"
                      required
                    />
                    <button type="submit" className="btn-base btn-secondary">{t.resetPassword}</button>
                    <button type="button" className="btn-base btn-cta" onClick={() => void onDeleteUser(u.id)}>{t.delete}</button>
                  </form>
                </div>
              ))}
            </div>
          </article>

          <article className="glass-card p-md">
            <h2 className="mb-sm text-xl font-bold text-primary">{t.agents}</h2>
            <div className="space-y-sm">
              {agents.map((a) => (
                <div key={a.id} className="rounded-lg border border-white/15 bg-white/5 p-sm text-sm">
                  <p className="font-semibold">#{a.id} {a.name}</p>
                  <p className="text-white/80">owner: {a.owner_user_id} | role: {a.role}</p>
                  <p className="text-white/70">gold {a.gold} food {a.food} energy {a.energy}</p>
                  <button type="button" className="btn-base btn-cta mt-xs" onClick={() => void onDeleteAgent(a.id)}>{t.delete}</button>
                </div>
              ))}
            </div>
          </article>
        </section>
      ) : null}
    </main>
  );
}
