"use client";

import { useEffect, useMemo, useState } from "react";
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
        empty: "目前尚無紀錄。",
        page: "頁",
        prev: "上一頁",
        next: "下一頁",
        pageSize: "每頁"
      }
    : {
        title: "Chronicle",
        subtitle: "Daily historical records from your city node.",
        loadFailed: "Failed to load chronicle",
        empty: "No records yet.",
        page: "Page",
        prev: "Prev",
        next: "Next",
        pageSize: "Per page"
      };

  const [entries, setEntries] = useState<ChronicleItem[]>([]);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);

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

  const totalPages = Math.max(1, Math.ceil(entries.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pagedEntries = useMemo(
    () => entries.slice((currentPage - 1) * pageSize, currentPage * pageSize),
    [entries, currentPage, pageSize]
  );

  useEffect(() => {
    setPage(1);
  }, [locale, pageSize]);

  return (
    <main className="space-y-lg">
      <header className="glass-card p-lg">
        <h1 className="flex items-center gap-sm text-3xl font-black">
          <BookOpenIcon className="h-8 w-8 text-primary" /> {t.title}
        </h1>
        <p className="text-sm text-white/75">{t.subtitle}</p>
      </header>

      {error ? <p className="rounded-lg bg-red-500/20 p-sm text-sm">{error}</p> : null}

      <section className="space-y-md">
        {entries.length === 0 ? (
          <article className="glass-card p-lg text-sm text-white/70">{t.empty}</article>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-sm md:grid-cols-2 xl:grid-cols-3">
              {pagedEntries.map((entry) => (
                <article key={entry.id} className="glass-card p-lg">
                  <p className="mb-xs text-xs uppercase tracking-wider text-cta">{entry.event_type_localized ?? entry.event_type}</p>
                  <h2 className="text-lg font-bold">{entry.title_localized ?? entry.title}</h2>
                  <p className="mt-xs text-sm text-white/85">{entry.content_localized ?? entry.content}</p>
                  <p className="mt-sm text-xs text-white/60">{new Date(entry.created_at).toLocaleString()}</p>
                </article>
              ))}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-sm text-sm text-white/80">
              <label className="inline-flex items-center gap-2">
                <span>{t.pageSize}</span>
                <select
                  className="rounded-lg border border-white/15 bg-black/20 px-sm py-xs text-white"
                  value={pageSize}
                  onChange={(e) => setPageSize(Number(e.target.value))}
                >
                  <option value={6}>6</option>
                  <option value={12}>12</option>
                  <option value={18}>18</option>
                </select>
              </label>
              <div className="flex items-center gap-sm">
                <button
                  className="btn-base btn-secondary"
                  disabled={currentPage <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  {t.prev}
                </button>
                <span>{t.page} {currentPage} / {totalPages}</span>
                <button
                  className="btn-base btn-secondary"
                  disabled={currentPage >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                >
                  {t.next}
                </button>
              </div>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
