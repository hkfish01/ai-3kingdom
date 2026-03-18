"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { ClipboardDocumentCheckIcon, KeyIcon, TrashIcon } from "@heroicons/react/24/outline";
import { useLocale } from "@/lib/locale";
import { apiClient } from "@/lib/api-client";
import { ApiKeyItem } from "@/lib/types";

export default function ApiKeysPage() {
  const { locale } = useLocale();
  const t = locale === "zh"
    ? {
        title: "API 金鑰管理",
        subtitle: "為居民整合建立、列出、複製與撤銷 API 金鑰。",
        createKey: "建立金鑰",
        keyName: "金鑰名稱",
        generate: "產生金鑰",
        total: "金鑰總數",
        current: "目前金鑰",
        empty: "目前尚無金鑰。",
        copied: "已複製",
        copy: "複製",
        revoke: "撤銷",
        created: "建立時間",
        revoked: "已撤銷",
        status: "狀態",
        active: "啟用中",
        oneTime: "新金鑰（只顯示一次）",
        createFailed: "建立 API 金鑰失敗",
        loadFailed: "載入 API 金鑰失敗",
        revokeFailed: "撤銷 API 金鑰失敗"
      }
    : {
        title: "API Key Management",
        subtitle: "Create, list, copy and revoke API keys for agent integrations.",
        createKey: "Create Key",
        keyName: "Key Name",
        generate: "Generate Key",
        total: "Total keys",
        current: "Current Keys",
        empty: "No keys yet.",
        copied: "Copied",
        copy: "Copy",
        revoke: "Revoke",
        created: "Created",
        revoked: "Revoked",
        status: "Status",
        active: "Active",
        oneTime: "New key (shown once)",
        createFailed: "Failed to create API key",
        loadFailed: "Failed to load API keys",
        revokeFailed: "Failed to revoke API key"
      };

  const [items, setItems] = useState<ApiKeyItem[]>([]);
  const [name, setName] = useState("OpenClaw Key");
  const [copiedId, setCopiedId] = useState("");
  const [error, setError] = useState("");
  const [newKey, setNewKey] = useState("");
  const [pending, setPending] = useState(false);

  const total = useMemo(() => items.length, [items]);

  const load = async () => {
    setError("");
    try {
      const data = await apiClient.listApiKeys();
      setItems(data.items ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.loadFailed);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const createKey = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const data = await apiClient.createApiKey({ name });
      setNewKey(data.key);
      setName("OpenClaw Key");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.createFailed);
    } finally {
      setPending(false);
    }
  };

  const revokeKey = async (id: number) => {
    setError("");
    try {
      await apiClient.revokeApiKey(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.revokeFailed);
    }
  };

  const copyText = async (id: string, value: string) => {
    await navigator.clipboard.writeText(value);
    setCopiedId(id);
    setTimeout(() => setCopiedId(""), 1200);
  };

  return (
    <main className="space-y-lg">
      <header className="glass-card p-lg">
        <h1 className="flex items-center gap-sm text-3xl font-black">
          <KeyIcon className="h-8 w-8 text-cta" /> {t.title}
        </h1>
        <p className="mt-xs text-sm text-white/75">{t.subtitle}</p>
      </header>

      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}

      {newKey ? (
        <section className="glass-card p-lg">
          <p className="text-sm font-semibold text-cta">{t.oneTime}</p>
          <p className="mt-xs break-all rounded-md bg-black/20 p-sm font-mono text-xs text-white/90">{newKey}</p>
          <button className="btn-base btn-secondary mt-sm text-xs" onClick={() => void copyText("new", newKey)}>
            <ClipboardDocumentCheckIcon className="mr-1 inline h-4 w-4" />
            {copiedId === "new" ? t.copied : t.copy}
          </button>
        </section>
      ) : null}

      <section className="grid gap-md md:grid-cols-[320px_1fr]">
        <article className="glass-card p-lg">
          <h2 className="mb-sm text-lg font-bold">{t.createKey}</h2>
          <form onSubmit={createKey} className="space-y-sm">
            <div>
              <label htmlFor="key-name">{t.keyName}</label>
              <input id="key-name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <button type="submit" className="btn-base btn-primary w-full" disabled={pending}>
              {pending ? "..." : t.generate}
            </button>
          </form>
          <p className="mt-md text-xs text-white/70">{t.total}: {total}</p>
        </article>

        <article className="glass-card p-lg">
          <h2 className="mb-sm text-lg font-bold">{t.current}</h2>
          {items.length === 0 ? (
            <p className="text-sm text-white/70">{t.empty}</p>
          ) : (
            <ul className="space-y-sm">
              {items.map((item) => (
                <li key={item.id} className="rounded-lg border border-white/15 bg-white/5 p-sm">
                  <p className="text-sm font-bold">{item.name}</p>
                  <p className="font-mono text-xs text-white/80">{item.key_preview}</p>
                  <p className="mt-xs text-xs text-white/60">
                    {t.created}: {new Date(item.created_at).toLocaleString()}
                  </p>
                  <p className="text-xs text-white/60">
                    {t.status}: {item.revoked ? t.revoked : t.active}
                  </p>
                  <div className="mt-sm flex gap-xs">
                    <button
                      className="btn-base btn-secondary text-xs"
                      onClick={() => void copyText(String(item.id), item.key_preview)}
                    >
                      <ClipboardDocumentCheckIcon className="mr-1 inline h-4 w-4" />
                      {copiedId === String(item.id) ? t.copied : t.copy}
                    </button>
                    <button
                      className="btn-base btn-cta text-xs"
                      onClick={() => void revokeKey(item.id)}
                      disabled={item.revoked}
                    >
                      <TrashIcon className="mr-1 inline h-4 w-4" /> {t.revoke}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </article>
      </section>
    </main>
  );
}
