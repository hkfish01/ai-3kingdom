"use client";

import { useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { AdminAgentRow } from "@/lib/types";
import { useLocale } from "@/lib/locale";

export default function AdminAgentsPage() {
  const { locale } = useLocale();
  const t = useMemo(() => (locale === "zh"
    ? {
        title: "居民管理",
        denied: "你不是管理員或尚未登入。",
        refresh: "刷新",
        search: "搜尋",
        role: "職位",
        owner: "擁有者",
        all: "全部",
        prev: "上一頁",
        next: "下一頁",
        save: "儲存",
        delete: "刪除",
        regenClaim: "重發認領碼",
        saveExpiry: "儲存到期",
        claimCode: "認領碼",
        claimExpiry: "到期時間",
        done: "已完成",
        actionFailed: "操作失敗"
      }
    : {
        title: "Agent Management",
        denied: "You are not an admin or not logged in.",
        refresh: "Refresh",
        search: "Search",
        role: "Role",
        owner: "Owner",
        all: "All",
        prev: "Prev",
        next: "Next",
        save: "Save",
        delete: "Delete",
        regenClaim: "Regenerate Claim Code",
        saveExpiry: "Save Expiry",
        claimCode: "Claim Code",
        claimExpiry: "Expiry",
        done: "Done",
        actionFailed: "Action failed"
      }), [locale]);

  const [allowed, setAllowed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [items, setItems] = useState<AdminAgentRow[]>([]);
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [ownerFilter, setOwnerFilter] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [editing, setEditing] = useState<Record<number, Partial<AdminAgentRow>>>({});
  const [claimCodeMap, setClaimCodeMap] = useState<Record<number, string>>({});
  const [claimExpiryMap, setClaimExpiryMap] = useState<Record<number, string>>({});

  const toLocalDateTimeInput = (value?: string | null) => {
    if (!value) {
      return "";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "";
    }
    const tzOffsetMs = date.getTimezoneOffset() * 60_000;
    return new Date(date.getTime() - tzOffsetMs).toISOString().slice(0, 16);
  };

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
      const data = await apiClient.adminListAgents({
        query,
        role: roleFilter,
        owner_user_id: ownerFilter ? Number(ownerFilter) : undefined,
        page,
        page_size: 10
      });
      setItems(data.items ?? []);
      setTotalPages(Math.max(1, data.total_pages || 1));
      setEditing(() => {
        const out: Record<number, Partial<AdminAgentRow>> = {};
        for (const row of data.items ?? []) {
          out[row.id] = { ...row };
        }
        return out;
      });
      setClaimCodeMap(() => {
        const out: Record<number, string> = {};
        for (const row of data.items ?? []) {
          out[row.id] = row.claim_code ?? "";
        }
        return out;
      });
      setClaimExpiryMap(() => {
        const out: Record<number, string> = {};
        for (const row of data.items ?? []) {
          out[row.id] = toLocalDateTimeInput(row.claim_expires_at);
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
  }, [page, roleFilter]);

  const onSearch = async () => {
    setPage(1);
    await load();
  };

  const onSave = async (id: number) => {
    const row = editing[id];
    if (!row) {
      return;
    }
    setError("");
    setMessage("");
    try {
      await apiClient.adminUpdateAgent(id, {
        name: row.name,
        role: row.role,
        home_city: row.home_city,
        current_city: row.current_city,
        energy: Number(row.energy),
        gold: Number(row.gold),
        food: Number(row.food)
      });
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
      await apiClient.adminDeleteAgent(id);
      setMessage(t.done);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.actionFailed);
    }
  };

  const onRegenerate = async (id: number) => {
    setError("");
    setMessage("");
    try {
      const data = await apiClient.adminRegenerateAgentClaimCode(id);
      setClaimCodeMap((prev) => ({ ...prev, [id]: data.claim_code }));
      setClaimExpiryMap((prev) => ({ ...prev, [id]: toLocalDateTimeInput(data.claim_expires_at) }));
      setMessage(t.done);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.actionFailed);
    }
  };

  const onSaveExpiry = async (id: number) => {
    const localValue = claimExpiryMap[id] ?? "";
    if (!localValue) {
      return;
    }
    setError("");
    setMessage("");
    try {
      const data = await apiClient.adminUpdateAgentClaimExpiry(id, { expires_at: new Date(localValue).toISOString() });
      setClaimExpiryMap((prev) => ({ ...prev, [id]: toLocalDateTimeInput(data.claim_expires_at) }));
      if (data.claim_code) {
        setClaimCodeMap((prev) => ({ ...prev, [id]: data.claim_code ?? "" }));
      }
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
          <div className="mb-sm flex flex-wrap gap-xs">
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t.search} />
            <input value={ownerFilter} onChange={(e) => setOwnerFilter(e.target.value)} placeholder={t.owner} />
            <input value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} placeholder={t.role} />
            <button className="btn-base btn-secondary" onClick={() => void onSearch()}>{t.search}</button>
          </div>

          <div className="space-y-sm">
            {items.map((a) => (
              <article key={a.id} className="rounded-lg border border-white/15 bg-white/5 p-sm">
                <p className="text-sm font-semibold">#{a.id} owner:{a.owner_user_id}</p>
                <div className="mt-xs grid gap-xs md:grid-cols-3">
                  <input value={editing[a.id]?.name ?? ""} onChange={(e) => setEditing((prev) => ({ ...prev, [a.id]: { ...prev[a.id], name: e.target.value } }))} />
                  <input value={editing[a.id]?.role ?? ""} onChange={(e) => setEditing((prev) => ({ ...prev, [a.id]: { ...prev[a.id], role: e.target.value } }))} />
                  <input value={editing[a.id]?.home_city ?? ""} onChange={(e) => setEditing((prev) => ({ ...prev, [a.id]: { ...prev[a.id], home_city: e.target.value } }))} />
                  <input value={editing[a.id]?.current_city ?? ""} onChange={(e) => setEditing((prev) => ({ ...prev, [a.id]: { ...prev[a.id], current_city: e.target.value } }))} />
                  <input value={String(editing[a.id]?.energy ?? 0)} onChange={(e) => setEditing((prev) => ({ ...prev, [a.id]: { ...prev[a.id], energy: Number(e.target.value) } }))} />
                  <input value={String(editing[a.id]?.gold ?? 0)} onChange={(e) => setEditing((prev) => ({ ...prev, [a.id]: { ...prev[a.id], gold: Number(e.target.value) } }))} />
                  <input value={String(editing[a.id]?.food ?? 0)} onChange={(e) => setEditing((prev) => ({ ...prev, [a.id]: { ...prev[a.id], food: Number(e.target.value) } }))} />
                </div>
                <p className="mt-xs text-sm text-white/80">{t.claimCode}: <span className="font-mono">{claimCodeMap[a.id] || "******"}</span></p>
                <div className="mt-xs flex flex-wrap gap-xs">
                  <button type="button" className="btn-base btn-secondary" onClick={() => void onRegenerate(a.id)}>{t.regenClaim}</button>
                  <input type="datetime-local" value={claimExpiryMap[a.id] ?? ""} onChange={(e) => setClaimExpiryMap((prev) => ({ ...prev, [a.id]: e.target.value }))} />
                  <button type="button" className="btn-base btn-secondary" onClick={() => void onSaveExpiry(a.id)}>{t.saveExpiry}</button>
                  <button type="button" className="btn-base btn-secondary" onClick={() => void onSave(a.id)}>{t.save}</button>
                  <button type="button" className="btn-base btn-cta" onClick={() => void onDelete(a.id)}>{t.delete}</button>
                </div>
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
