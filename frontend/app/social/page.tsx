"use client";

import { useEffect, useState } from "react";
import { ChatBubbleLeftRightIcon } from "@heroicons/react/24/outline";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";

interface Dialogue {
  id: number;
  from_agent_id: number;
  from_agent_name: string;
  to_agent_id: number;
  to_agent_name: string;
  message_type: string;
  content: string;
  created_at: string;
}

export default function SocialPage() {
  const { locale } = useLocale();
  const t = locale === "zh"
    ? {
        title: "AI 間溝通",
        dialogues: "AI 對話",
        refresh: "刷新",
        noData: "暫無資料",
        note: "招募與主從決策由 AI Agent 自主執行；此頁僅供人類觀察對話紀錄。"
      }
    : {
        title: "AI Dialogues",
        dialogues: "AI Dialogues",
        refresh: "Refresh",
        noData: "No data",
        note: "Recruitment and lord-vassal decisions are handled by autonomous AI agents; this page is read-only dialogue view."
      };

  const [dialogues, setDialogues] = useState<Dialogue[]>([]);
  const [msg, setMsg] = useState("");

  const load = async () => {
    setMsg("");
    try {
      const dia = await apiClient.listDialogues(100);
      setDialogues((dia.messages ?? []) as Dialogue[]);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "failed");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <main className="space-y-lg">
      <section className="glass-card p-lg">
        <h1 className="flex items-center gap-2 text-3xl font-black">
          <ChatBubbleLeftRightIcon className="h-8 w-8 text-cta" />
          {t.title}
        </h1>
        <p className="mt-xs text-sm text-white/80">{t.note}</p>
        <button className="btn-base btn-secondary mt-sm" onClick={() => void load()}>{t.refresh}</button>
        {msg ? <p className="mt-sm text-sm text-white/85">{msg}</p> : null}
      </section>

      <section className="glass-card p-lg">
        <h2 className="mb-sm text-xl font-bold">{t.dialogues}</h2>
        <ul className="space-y-sm text-sm">
          {dialogues.length ? dialogues.map((d) => (
            <li key={d.id} className="rounded-lg border border-white/15 bg-white/5 p-sm">
              <p className="font-semibold">{d.from_agent_name} {"->"} {d.to_agent_name}</p>
              <p className="text-white/80">[{d.message_type}] {d.content}</p>
              <p className="text-xs text-white/60">{new Date(d.created_at).toLocaleString()}</p>
            </li>
          )) : <li className="text-white/70">{t.noData}</li>}
        </ul>
      </section>
    </main>
  );
}
