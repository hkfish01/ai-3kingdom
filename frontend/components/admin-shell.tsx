"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { adminApi } from "@/lib/admin-api";
import {
  ChartBarIcon,
  UserGroupIcon,
  ShieldCheckIcon,
} from "@heroicons/react/24/outline";

const adminNavLinks = [
  { href: "/admin-dashboard", key: "dashboard", icon: ChartBarIcon, label: "AI DevOps" },
  { href: "/admin", key: "overview", icon: ShieldCheckIcon, label: "管理首頁" },
  { href: "/admin/users", key: "users", icon: UserGroupIcon, label: "用戶管理" },
  { href: "/admin/agents", key: "agents", icon: UserGroupIcon, label: "居民管理" },
] as const;

function AdminTopNav() {
  const pathname = usePathname();
  return (
    <nav className="mb-6 rounded-xl bg-slate-800 p-3 shadow-lg">
      <div className="flex flex-wrap items-center gap-2">
        {adminNavLinks.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold transition ${
                active
                  ? "bg-indigo-600 text-white"
                  : "bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white"
              }`}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {item.label}
            </Link>
          );
        })}
        <div className="ml-auto">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 rounded-lg bg-white/5 px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-white/10 hover:text-white transition"
          >
            回到遊戲
          </Link>
        </div>
      </div>
    </nav>
  );
}

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
        <AdminTopNav />
        {children}
      </div>
    </main>
  );
}
