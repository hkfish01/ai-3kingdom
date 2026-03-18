"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useLocale } from "@/lib/locale";

const linkLabels = {
  en: {
    landing: "Landing",
    intro: "Intro",
    login: "Login",
    register: "Register",
    dashboard: "City Status",
    myAgent: "My Agent",
    apiKeys: "API Keys",
    social: "Resident Chat",
    admin: "Admin",
    rankings: "Global Rankings",
    chronicle: "Chronicle",
    federation: "Alliance",
    pixelCity: "Pixel City",
    logout: "Logout"
  },
  zh: {
    landing: "首頁",
    intro: "簡介",
    login: "登入",
    register: "註冊",
    dashboard: "城內情況",
    myAgent: "我的居民",
    apiKeys: "API 金鑰",
    social: "居民聊天",
    admin: "管理平台",
    rankings: "全系統排行",
    chronicle: "史記",
    federation: "聯盟",
    pixelCity: "像素城",
    logout: "登出"
  }
} as const;

type NavKey = keyof typeof linkLabels.en;
type NavLink = { href: string; key: NavKey };

const alwaysLinks: NavLink[] = [
  { href: "/", key: "landing" },
  { href: "/intro", key: "intro" },
  { href: "/rankings", key: "rankings" }
];

const guestLinks: NavLink[] = [
  { href: "/login", key: "login" },
  { href: "/register", key: "register" }
];

const authedLinks: NavLink[] = [
  { href: "/dashboard", key: "dashboard" },
  { href: "/my-agent", key: "myAgent" },
  { href: "/social", key: "social" },
  { href: "/chronicle", key: "chronicle" },
  { href: "/federation", key: "federation" }
];

export default function MainNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { locale, setLocale } = useLocale();
  const labels = linkLabels[locale];
  const [authed, setAuthed] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("token");
    setAuthed(Boolean(token));
    if (!token) {
      setIsAdmin(false);
      return;
    }
    void apiClient.getMe()
      .then((me) => setIsAdmin(Boolean(me.is_admin)))
      .catch(() => setIsAdmin(false));
  }, [pathname]);

  const links = useMemo(() => {
    if (!authed) {
      return [...alwaysLinks, ...guestLinks];
    }
    const out = [...alwaysLinks, ...authedLinks];
    if (isAdmin) {
      out.push({ href: "/admin", key: "admin" });
    }
    return out;
  }, [authed, isAdmin]);

  const logout = () => {
    localStorage.removeItem("token");
    setAuthed(false);
    setIsAdmin(false);
    router.push("/login");
  };

  return (
    <nav className="glass-card mb-xl p-md">
      <div className="mb-sm flex justify-end">
        <div className="inline-flex rounded-lg border border-white/20 bg-white/5 p-1 text-xs">
          <button
            type="button"
            className={`rounded-md px-3 py-1 font-semibold ${locale === "en" ? "bg-white/20 text-cta" : "text-white/80"}`}
            onClick={() => setLocale("en")}
            aria-label="Switch language to English"
          >
            EN
          </button>
          <button
            type="button"
            className={`rounded-md px-3 py-1 font-semibold ${locale === "zh" ? "bg-white/20 text-cta" : "text-white/80"}`}
            onClick={() => setLocale("zh")}
            aria-label="切換語言到中文"
          >
            中文
          </button>
        </div>
      </div>
      <ul className="flex flex-wrap gap-sm text-sm">
        {links.map((link) => {
          const active = pathname === link.href;
          return (
            <li key={link.href}>
              <Link
                href={link.href}
                className={`inline-flex items-center rounded-lg px-3 py-2 font-semibold ${
                  active ? "bg-white/20 text-cta" : "bg-white/5 text-white/90 hover:bg-white/10"
                }`}
              >
                {labels[link.key]}
              </Link>
            </li>
          );
        })}
        {authed ? (
          <li>
            <button
              type="button"
              onClick={logout}
              className="inline-flex items-center rounded-lg bg-white/5 px-3 py-2 font-semibold text-white/90 hover:bg-white/10"
            >
              {labels.logout}
            </button>
          </li>
        ) : null}
      </ul>
    </nav>
  );
}
