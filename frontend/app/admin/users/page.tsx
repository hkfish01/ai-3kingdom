"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { AdminUserRow } from "@/lib/types";
import { useLocale } from "@/lib/locale";

export default function AdminUsersPage() {
  const { locale } = useLocale();
  const t = useMemo(() => (locale === "zh"
    ? {
        title: "用戶管理",
        denied: "你不是管理員或尚未登入。",
        refresh: "刷新",
        search: "搜尋",
        adminFilter: "管理員",
        all: "全部",
        yes: "是",
        no: "否",
        prev: "上一頁",
        next: "下一頁",
        save: "儲存",
        delete: "刪除",
        resetPassword: "重設密碼",
        done: "已完成",
        actionFailed: "操作失敗"
      }
    : {
        title: "User Management",
        denied: "You are not an admin or not logged in.",
        refresh: "Refresh",
        search: "Search",
        adminFilter: "Admin",
        all: "All",
        yes: "Yes",
        no: "No",
        prev: "Prev",
        next: "Next",
        save: "Save",
        delete: "Delete",
        resetPassword: "Reset Password",
        done: "Done",
        actionFailed: "Action failed"
      }), [locale]);

  const [allowed, setAllowed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [items, setItems] = useState<AdminUserRow[]>([]);
  const [query, setQuery] = useState("");
  const [isAdminFilter, setIsAdminFilter] = useState<"all" | "true" | "false">("all");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [editing, setEditing] = useState<Record<number, { username: string; email: string; is_admin: boolean }>>({});
  const [resetPwdMap, setResetPwdMap] = useState<Record<number, string>>({});

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const me = await apiClient.getMe();
      if (!me.is_admin) {
        setAllowed(false);
        return;
      }
      setAllowed(true);
      const data = await apiClient.adminListUsers({ query, is_admin: isAdminFilter, page, page_size: 10 });
      setItems(data.items ?? []);
      setTotalPages(Math.max(1, data.total_pages || 1));
      setEditing(() => {
        const out: Record<number, { username: string; email: string; is_admin: boolean }> = {};
        for (const row of data.items ?? []) {
          out[row.id] = { username: row.username, email: row.email, is_admin: row.is_admin };
        }
        return out;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t.actionFailed);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [page, isAdminFilter]);

  const onSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPage(1);
    await load();
  };

  const onSave = async (id: number) => {
    setError("");
    setMessage("");
    try {
      await apiClient.adminUpdateUser(id, editing[id]);
      setMessage(t.done);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.actionFailed);
    }
  };

  const onDelete = async (id: number) => {
    setError("");
    setMessage("");
    try {
      await apiClient.adminDeleteUser(id);
      setMessage(t.done);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.actionFailed);
    }
  };

  const onReset = async (event: FormEvent<HTMLFormElement>, id: number) => {
    event.preventDefault();
    const pwd = resetPwdMap[id] ?? "";
    if (!pwd) {
      return;
    }
    setError("");
    setMessage("");
    try {
      await apiClient.adminResetUserPassword(id, { new_password: pwd });
      setResetPwdMap((prev) => ({ ...prev, [id]: "" }));
      setMessage(t.done);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.actionFailed);
    }
  };

  return (
    <main className="space-y-md">
      <section className="glass-card p-md">
        <div className="flex flex-wrap items-center justify-between gap-sm">
          <h1 className="text-2xl font-bold">{t.title}</h1>
          <button className="btn-base btn-secondary" onClick={() => void load()}>{t.refresh}</button>
        </div>
      </section>

      {!loading && !allowed ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{t.denied}</p> : null}
      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}
      {message ? <p className="rounded-lg bg-emerald-500/20 p-sm text-sm">{message}</p> : null}

      {allowed ? (
        <section className="glass-card p-md">
          <form className="mb-sm flex flex-wrap gap-xs" onSubmit={(e) => void onSearch(e)}>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t.search} />
            <select value={isAdminFilter} onChange={(e) => setIsAdminFilter(e.target.value as "all" | "true" | "false")}>
              <option value="all">{t.adminFilter}: {t.all}</option>
              <option value="true">{t.adminFilter}: {t.yes}</option>
              <option value="false">{t.adminFilter}: {t.no}</option>
            </select>
            <button type="submit" className="btn-base btn-secondary">{t.search}</button>
          </form>

          <div className="space-y-sm">
            {items.map((u) => (
              <article key={u.id} className="rounded-lg border border-white/15 bg-white/5 p-sm">
                <p className="text-sm font-semibold">#{u.id}</p>
                <div className="mt-xs grid gap-xs md:grid-cols-3">
                  <input
                    value={editing[u.id]?.username ?? ""}
                    onChange={(e) => setEditing((prev) => ({ ...prev, [u.id]: { ...prev[u.id], username: e.target.value } }))}
                  />
                  <input
                    value={editing[u.id]?.email ?? ""}
                    onChange={(e) => setEditing((prev) => ({ ...prev, [u.id]: { ...prev[u.id], email: e.target.value } }))}
                  />
                  <label className="flex items-center gap-xs text-sm text-white/80">
                    <input
                      type="checkbox"
                      checked={Boolean(editing[u.id]?.is_admin)}
                      onChange={(e) => setEditing((prev) => ({ ...prev, [u.id]: { ...prev[u.id], is_admin: e.target.checked } }))}
                    />
                    {t.adminFilter}
                  </label>
                </div>
                <form className="mt-xs flex flex-wrap gap-xs" onSubmit={(e) => void onReset(e, u.id)}>
                  <input
                    type="password"
                    value={resetPwdMap[u.id] ?? ""}
                    onChange={(e) => setResetPwdMap((prev) => ({ ...prev, [u.id]: e.target.value }))}
                    placeholder={t.resetPassword}
                  />
                  <button type="submit" className="btn-base btn-secondary">{t.resetPassword}</button>
                  <button type="button" className="btn-base btn-secondary" onClick={() => void onSave(u.id)}>{t.save}</button>
                  <button type="button" className="btn-base btn-cta" onClick={() => void onDelete(u.id)}>{t.delete}</button>
                </form>
              </article>
            ))}
          </div>

          <div className="mt-sm flex items-center justify-end gap-xs">
            <button className="btn-base btn-secondary" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>{t.prev}</button>
            <span className="text-sm text-white/80">{page} / {totalPages}</span>
            <button className="btn-base btn-secondary" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>{t.next}</button>
          </div>
        </section>
      ) : null}
    </main>
  );
}
