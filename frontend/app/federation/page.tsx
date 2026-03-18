"use client";

import { useEffect, useState } from "react";
import { ArrowPathIcon, GlobeAltIcon, ShieldCheckIcon } from "@heroicons/react/24/outline";
import { apiClient } from "@/lib/api-client";
import { FederationPeer, FederationStatus } from "@/lib/types";
import { useLocale } from "@/lib/locale";

export default function FederationPage() {
  const { locale } = useLocale();
  const t = locale === "zh"
    ? {
        title: "聯邦",
        refresh: "刷新",
        loadFailed: "載入聯邦狀態失敗",
        city: "城池",
        protocolRule: "協議 / 規則",
        openMigration: "開放遷移",
        lastStatus: "最後狀態時間",
        trustedPeers: "可信節點",
        baseUrl: "基礎 URL",
        trust: "信任",
        protocol: "協議",
        lastSeen: "最後上線",
        noPeers: "目前沒有已連線節點。",
        yes: "是",
        no: "否",
        loginRequired: "請先登入以查看聯盟資料。",
        sessionExpired: "登入已超時，請重新登入。"
      }
    : {
        title: "Federation",
        refresh: "Refresh",
        loadFailed: "Failed to load federation status",
        city: "City",
        protocolRule: "Protocol / Rule",
        openMigration: "Open Migration",
        lastStatus: "Last Status Time",
        trustedPeers: "Trusted Peers",
        baseUrl: "Base URL",
        trust: "Trust",
        protocol: "Protocol",
        lastSeen: "Last Seen",
        noPeers: "No peers connected.",
        yes: "Yes",
        no: "No",
        loginRequired: "Please login first to view federation data.",
        sessionExpired: "Session expired. Please login again."
      };

  const [status, setStatus] = useState<FederationStatus | null>(null);
  const [peers, setPeers] = useState<FederationPeer[]>([]);
  const [error, setError] = useState("");
  const [authReady, setAuthReady] = useState(false);
  const [authMessage, setAuthMessage] = useState("");

  const logout = (hint: string) => {
    setAuthMessage(hint);
    alert(hint);
    localStorage.removeItem("token");
    window.location.href = "/login";
  };

  const handleAuthExpired = (err: unknown) => {
    const statusCode = (err as { status?: number }).status;
    const code = (err as { code?: string }).code;
    if (statusCode === 401 || code === "UNAUTHORIZED" || code === "USER_NOT_FOUND") {
      logout(t.sessionExpired);
      return true;
    }
    return false;
  };

  const load = async () => {
    setError("");
    try {
      const statusData = (await apiClient.federationStatus()) as FederationStatus;
      const peersData = (await apiClient.listPeers()) as { peers: FederationPeer[] };
      setStatus(statusData);
      setPeers(peersData.peers ?? []);
    } catch (err) {
      if (handleAuthExpired(err)) {
        return;
      }
      setError(err instanceof Error ? err.message : t.loadFailed);
    }
  };

  useEffect(() => {
    const token = typeof window === "undefined" ? null : localStorage.getItem("token");
    if (!token) {
      logout(t.loginRequired);
      return;
    }
    setAuthReady(true);
  }, [t.loginRequired]);

  useEffect(() => {
    if (authReady) {
      void load();
    }
  }, [authReady]);

  if (!authReady) {
    if (authMessage) {
      return (
        <main className="space-y-lg">
          <p className="rounded-lg bg-red-500/20 p-sm text-sm">{authMessage}</p>
        </main>
      );
    }
    return null;
  }

  return (
    <main className="space-y-lg">
      <header className="glass-card flex flex-wrap items-center justify-between gap-sm p-lg">
        <h1 className="flex items-center gap-sm text-3xl font-black">
          <GlobeAltIcon className="h-8 w-8 text-primary" /> {t.title}
        </h1>
        <button className="btn-base btn-secondary flex items-center gap-2" onClick={() => void load()}>
          <ArrowPathIcon className="h-5 w-5" /> {t.refresh}
        </button>
      </header>

      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}

      <section className="grid-auto">
        <article className="glass-card p-md">
          <p className="text-xs text-white/70">{t.city}</p>
          <p className="text-xl font-black text-cta">{status?.city_name ?? "-"}</p>
        </article>
        <article className="glass-card p-md">
          <p className="text-xs text-white/70">{t.protocolRule}</p>
          <p className="text-xl font-black">{status ? `${status.protocol_version} / ${status.rule_version}` : "-"}</p>
        </article>
        <article className="glass-card p-md">
          <p className="text-xs text-white/70">{t.openMigration}</p>
          <p className="text-xl font-black">{status?.open_for_migration ? t.yes : t.no}</p>
        </article>
        <article className="glass-card p-md">
          <p className="text-xs text-white/70">{t.lastStatus}</p>
          <p className="text-sm font-bold">{status ? new Date(status.timestamp).toLocaleString() : "-"}</p>
        </article>
      </section>

      <section className="glass-card p-lg">
        <h2 className="mb-md flex items-center gap-sm text-xl font-bold">
          <ShieldCheckIcon className="h-6 w-6 text-cta" /> {t.trustedPeers}
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/15 text-white/70">
                <th className="py-2">{t.city}</th>
                <th>{t.baseUrl}</th>
                <th>{t.trust}</th>
                <th>{t.protocol}</th>
                <th>{t.lastSeen}</th>
              </tr>
            </thead>
            <tbody>
              {peers.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-4 text-white/60">
                    {t.noPeers}
                  </td>
                </tr>
              ) : (
                peers.map((peer) => (
                  <tr key={peer.city_name} className="border-b border-white/10">
                    <td className="py-3 font-semibold">{peer.city_name}</td>
                    <td>{peer.base_url}</td>
                    <td>{peer.trust_status}</td>
                    <td>{peer.protocol_version}</td>
                    <td>{new Date(peer.last_seen_at).toLocaleString()}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
