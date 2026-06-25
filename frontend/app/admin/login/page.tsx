"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheckIcon, EyeIcon, EyeSlashIcon } from "@heroicons/react/24/outline";
import { adminApi } from "@/lib/admin-api";

export default function AdminLoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      await adminApi.login(username, password);
      router.push("/admin-dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登入失敗");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      <div className="w-full max-w-md px-6">
        {/* Logo */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-2xl bg-indigo-600">
            <ShieldCheckIcon className="h-12 w-12 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-white">AI DevOps</h1>
          <p className="mt-2 text-slate-400">三國世界管理系統</p>
        </div>

        {/* Login Form */}
        <form
          onSubmit={(e) => void handleLogin(e)}
          className="rounded-2xl bg-slate-800 p-8 shadow-2xl"
        >
          <div className="mb-6">
            <label
              htmlFor="username"
              className="mb-2 block text-sm font-medium text-slate-300"
            >
              帳號
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="輸入帳號"
              required
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-3 text-white placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
          </div>

          <div className="mb-6">
            <label
              htmlFor="password"
              className="mb-2 block text-sm font-medium text-slate-300"
            >
              密碼
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="輸入密碼"
                required
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-3 pr-12 text-white placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
              >
                {showPassword ? (
                  <EyeSlashIcon className="h-5 w-5" />
                ) : (
                  <EyeIcon className="h-5 w-5" />
                )}
              </button>
            </div>
          </div>

          {error && (
            <div className="mb-4 rounded-lg bg-red-500/20 p-3 text-sm text-red-400">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-indigo-600 py-3 font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
          >
            {loading ? "登入中..." : "登入"}
          </button>
        </form>

        {/* Footer */}
        <p className="mt-6 text-center text-sm text-slate-500">
          此系統僅供管理員使用
        </p>
      </div>
    </main>
  );
}
