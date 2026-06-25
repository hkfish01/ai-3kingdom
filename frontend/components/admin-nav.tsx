"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo } from "react";
import { useLocale } from "@/lib/locale";
import {
  ChartBarIcon,
  UserGroupIcon,
  UserIcon,
  ShieldCheckIcon,
  ArrowLeftOnRectangleIcon,
} from "@heroicons/react/24/outline";

const links = [
  { href: "/admin-dashboard", key: "dashboard", icon: ChartBarIcon },
  { href: "/admin/users", key: "users", icon: UserGroupIcon },
  { href: "/admin/agents", key: "agents", icon: UserIcon },
] as const;

export default function AdminNav() {
  const pathname = usePathname();
  const { locale } = useLocale();
  const labels = useMemo(
    () =>
      locale === "zh"
        ? {
            title: "管理平台",
            dashboard: "系統總覽",
            users: "用戶管理",
            agents: "居民管理",
            logout: "登出",
            backToSite: "回到網站",
          }
        : {
            title: "Admin",
            dashboard: "Dashboard",
            users: "Users",
            agents: "Agents",
            logout: "Logout",
            backToSite: "Back to site",
          },
    [locale]
  );

  return (
    <nav className="glass-card mb-lg p-md">
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <div className="flex items-center gap-sm">
          <ShieldCheckIcon className="h-6 w-6 text-cta" aria-hidden="true" />
          <span className="text-lg font-bold">{labels.title}</span>
        </div>
        <div className="flex flex-wrap items-center gap-xs text-sm">
          {links.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`inline-flex items-center gap-xs rounded-lg px-3 py-2 font-semibold ${
                  active ? "bg-white/20 text-cta" : "bg-white/5 text-white/90 hover:bg-white/10"
                }`}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {labels[item.key]}
              </Link>
            );
          })}
          <Link
            href="/"
            className="inline-flex items-center gap-xs rounded-lg bg-white/5 px-3 py-2 font-semibold text-white/90 hover:bg-white/10"
          >
            {labels.backToSite}
          </Link>
          <button
            type="button"
            onClick={() => {
              localStorage.removeItem("admin_token");
              localStorage.removeItem("admin_refresh_token");
              window.location.href = "/admin/login";
            }}
            className="inline-flex items-center gap-xs rounded-lg bg-white/5 px-3 py-2 font-semibold text-white/90 hover:bg-white/10"
          >
            <ArrowLeftOnRectangleIcon className="h-4 w-4" aria-hidden="true" />
            {labels.logout}
          </button>
        </div>
      </div>
    </nav>
  );
}
