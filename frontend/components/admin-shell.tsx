"use client";

import { useEffect, useMemo, useState } from "react";
import { adminApi } from "@/lib/admin-api";
import AdminNav from "@/components/admin-nav";

export default function AdminShell({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        await adminApi.getMe();
        if (!active) return;
        setAuthed(true);
      } catch {
        if (!active) return;
        setAuthed(false);
      } finally {
        if (active) setReady(true);
      }
    };
    void check();
    return () => {
      active = false;
    };
  }, []);

  const fallback = useMemo(
    () => (
      <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
      </main>
    ),
    []
  );

  if (!ready) {
    return fallback;
  }

  if (!authed) {
    if (typeof window !== "undefined") {
      window.location.href = "/admin/login";
    }
    return null;
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-md">
      <div className="mx-auto max-w-6xl">
        <AdminNav />
        {children}
      </div>
    </main>
  );
}
