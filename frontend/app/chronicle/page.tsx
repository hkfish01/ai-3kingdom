"use client";

import { useEffect, useState } from "react";
import { BookOpenIcon } from "@heroicons/react/24/outline";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";

interface ChronicleItem {
  id: number;
  event_type: string;
  event_type_localized?: string;
  title: string;
  title_localized?: string;
  content: string;
  content_localized?: string;
  created_at: string;
}

export default function ChroniclePage() {
  const { locale } = useLocale();
  const t = locale === "zh"
    ? {
        title: "史記",
        subtitle: "來自你的城池節點的每日歷史紀錄。",
        loadFailed: "載入史記失敗",
        empty: "目前尚無紀錄。"
      }
    : {
        title: "Chronicle",
        subtitle: "Daily historical records from your city node.",
        loadFailed: "Failed to load chronicle",
        empty: "No records yet."
      };

  const [entries, setEntries] = useState<ChronicleItem[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const data = (await apiClient.getChronicle(locale)) as { entries: ChronicleItem[] };
        setEntries(data.entries ?? []);
      } catch (err) {
        setError(err instanceof Error ? err.message : t.loadFailed);
      }
    };

    void load();
  }, [locale]);

  return (
    <main className="space-y-lg">
      <header className="glass-card p-lg">
        <h1 className="flex items-center gap-sm text-3xl font-black">
          <BookOpenIcon className="h-8 w-8 text-primary" /> {t.title}
        </h1>
        <p className="text-sm text-white/75">{t.subtitle}</p>
      </header>

      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}

      <section className="space-y-sm">
        {entries.length === 0 ? (
          <article className="glass-card p-lg text-sm text-white/70">{t.empty}</article>
        ) : (
          entries.map((entry) => (
            <article key={entry.id} className="glass-card p-lg">
              <p className="mb-xs text-xs uppercase tracking-wider text-cta">{entry.event_type_localized ?? entry.event_type}</p>
              <h2 className="text-lg font-bold">{entry.title_localized ?? entry.title}</h2>
              <p className="mt-xs text-sm text-white/85">{entry.content_localized ?? entry.content}</p>
              <p className="mt-sm text-xs text-white/60">{new Date(entry.created_at).toLocaleString()}</p>
            </article>
          ))
        )}
      </section>
    </main>
  );
}
