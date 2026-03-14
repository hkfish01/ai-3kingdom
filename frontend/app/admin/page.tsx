"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { ShieldCheckIcon } from "@heroicons/react/24/outline";
import { apiClient } from "@/lib/api-client";
import { AnnouncementItem } from "@/lib/types";
import { useLocale } from "@/lib/locale";

export default function AdminPage() {
  const { locale } = useLocale();
  const t = useMemo(() => (locale === "zh"
    ? {
        title: "管理平台",
        denied: "你不是管理員或尚未登入。",
        refresh: "刷新",
        done: "已完成",
        actionFailed: "操作失敗",
        users: "用戶管理",
        agents: "代理管理",
        announcements: "公告管理",
        createAnnouncement: "新增公告",
        announcementTitle: "標題",
        announcementContent: "內容",
        published: "已發佈",
        delete: "刪除",
        publish: "發佈",
        unpublish: "下架"
      }
    : {
        title: "Admin Panel",
        denied: "You are not an admin or not logged in.",
        refresh: "Refresh",
        done: "Done",
        actionFailed: "Action failed",
        users: "User Management",
        agents: "Agent Management",
        announcements: "Announcement Management",
        createAnnouncement: "Create Announcement",
        announcementTitle: "Title",
        announcementContent: "Content",
        published: "Published",
        delete: "Delete",
        publish: "Publish",
        unpublish: "Unpublish"
      }), [locale]);

  const [allowed, setAllowed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [announcements, setAnnouncements] = useState<AnnouncementItem[]>([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [published, setPublished] = useState(true);

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
      setAnnouncements(data.announcements ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : t.actionFailed);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const onCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!title.trim() || !content.trim()) {
      return;
    }
    setError("");
    setMessage("");
    try {
      await apiClient.adminCreateAnnouncement({ title: title.trim(), content: content.trim(), published });
      setTitle("");
      setContent("");
      setPublished(true);
      setMessage(t.done);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t.actionFailed);
    }
  };

  const onToggle = async (item: AnnouncementItem) => {
    setError("");
    setMessage("");
    try {
      await apiClient.adminUpdateAnnouncement(item.id, { published: !item.published });
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
      await apiClient.adminDeleteAnnouncement(id);
      setMessage(t.done);
      await load();
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
        <section className="grid gap-md md:grid-cols-2">
          <Link href="/admin/users" className="glass-card p-lg hover:bg-white/10">
            <h2 className="text-xl font-bold text-primary">{t.users}</h2>
          </Link>
          <Link href="/admin/agents" className="glass-card p-lg hover:bg-white/10">
            <h2 className="text-xl font-bold text-primary">{t.agents}</h2>
          </Link>
        </section>
      ) : null}

      {allowed ? (
        <section className="glass-card p-md">
          <h2 className="mb-sm text-xl font-bold text-primary">{t.announcements}</h2>
          <form className="space-y-sm rounded-lg border border-white/15 bg-white/5 p-sm" onSubmit={(e) => void onCreate(e)}>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t.announcementTitle} required />
            <textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder={t.announcementContent} rows={3} required />
            <label className="flex items-center gap-xs text-sm text-white/80">
              <input type="checkbox" checked={published} onChange={(e) => setPublished(e.target.checked)} />
              {t.published}
            </label>
            <button type="submit" className="btn-base btn-secondary">{t.createAnnouncement}</button>
          </form>
          <div className="mt-sm space-y-sm">
            {announcements.map((a) => (
              <div key={a.id} className="rounded-lg border border-white/15 bg-white/5 p-sm">
                <p className="font-semibold">#{a.id} {a.title}</p>
                <p className="mt-xs text-sm text-white/85">{a.content}</p>
                <div className="mt-xs flex flex-wrap gap-xs">
                  <button type="button" className="btn-base btn-secondary" onClick={() => void onToggle(a)}>
                    {a.published ? t.unpublish : t.publish}
                  </button>
                  <button type="button" className="btn-base btn-cta" onClick={() => void onDelete(a.id)}>{t.delete}</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </main>
  );
}
