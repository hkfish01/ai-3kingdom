"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ChartBarIcon,
  ChartPieIcon,
  CpuChipIcon,
  ShieldCheckIcon,
  UserGroupIcon,
  BellIcon,
  ArrowTrendingUpIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  XCircleIcon,
} from "@heroicons/react/24/outline";
import { adminApi } from "@/lib/admin-api";
import type { DevOpsReport } from "@/lib/types";

export default function AdminDashboardPage() {
  const router = useRouter();
  const [report, setReport] = useState<DevOpsReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [triggering, setTriggering] = useState(false);

  const checkAuth = async () => {
    try {
      await adminApi.getMe();
    } catch {
      router.push("/admin/login");
    }
  };

  const loadReport = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await adminApi.getDevOpsReport();
      setReport(data as DevOpsReport);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load report");
    } finally {
      setLoading(false);
    }
  };

  const triggerCheck = async () => {
    setTriggering(true);
    setError("");
    try {
      const result = await adminApi.triggerDevOpsCheck();
      await loadReport();
      alert(`Check completed: ${result.summary}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger check");
    } finally {
      setTriggering(false);
    }
  };

  useEffect(() => {
    void checkAuth();
    void loadReport();
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "healthy":
        return "text-emerald-400";
      case "warning":
        return "text-yellow-400";
      case "critical":
        return "text-red-400";
      default:
        return "text-gray-400";
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "healthy":
        return <CheckCircleIcon className="h-6 w-6 text-emerald-400" />;
      case "warning":
        return <ExclamationTriangleIcon className="h-6 w-6 text-yellow-400" />;
      case "critical":
        return <XCircleIcon className="h-6 w-6 text-red-400" />;
      default:
        return null;
    }
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-6">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="rounded-xl bg-indigo-600 p-3">
            <ShieldCheckIcon className="h-8 w-8 text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-white">AI DevOps Dashboard</h1>
            <p className="text-slate-400">三國世界 AI 代理系統監控中心</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <Link
            href="/admin/users"
            className="rounded-lg bg-slate-700 px-4 py-2 text-white transition hover:bg-slate-600"
          >
            用戶管理
          </Link>
          <Link
            href="/admin/agents"
            className="rounded-lg bg-slate-700 px-4 py-2 text-white transition hover:bg-slate-600"
          >
            居民管理
          </Link>
          <button
            onClick={() => {
              adminApi.logout();
              router.push("/admin/login");
            }}
            className="rounded-lg bg-red-600 px-4 py-2 text-white transition hover:bg-red-500"
          >
            登出
          </button>
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent"></div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="mb-6 rounded-lg bg-red-500/20 p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Main Content */}
      {!loading && report && (
        <>
          {/* Summary Cards */}
          <div className="mb-8 grid gap-6 md:grid-cols-4">
            {/* System Health */}
            <div className="rounded-xl bg-slate-800 p-6 shadow-lg">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-sm font-medium text-slate-400">系統狀態</h3>
                {getStatusIcon(report.health.status)}
              </div>
              <p className={`text-2xl font-bold ${getStatusColor(report.health.status)}`}>
                {report.health.status === "healthy"
                  ? "健康"
                  : report.health.status === "warning"
                  ? "警告"
                  : "危險"}
              </p>
            </div>

            {/* Active Agents */}
            <div className="rounded-xl bg-slate-800 p-6 shadow-lg">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-sm font-medium text-slate-400">活躍玩家</h3>
                <UserGroupIcon className="h-6 w-6 text-indigo-400" />
              </div>
              <p className="text-2xl font-bold text-white">
                {report.game_analysis.engagement.active_1d}
              </p>
              <p className="text-sm text-slate-400">
                / {report.game_analysis.engagement.total_agents} 總計
              </p>
            </div>

            {/* Retention */}
            <div className="rounded-xl bg-slate-800 p-6 shadow-lg">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-sm font-medium text-slate-400">日留存率</h3>
                <ArrowTrendingUpIcon className="h-6 w-6 text-emerald-400" />
              </div>
              <p className="text-2xl font-bold text-emerald-400">
                {report.game_analysis.engagement.retention_1d}
              </p>
            </div>

            {/* Planned Features */}
            <div className="rounded-xl bg-slate-800 p-6 shadow-lg">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-sm font-medium text-slate-400">建議改進</h3>
                <CpuChipIcon className="h-6 w-6 text-amber-400" />
              </div>
              <p className="text-2xl font-bold text-amber-400">
                {report.planned_features.length}
              </p>
              <p className="text-sm text-slate-400">功能計劃</p>
            </div>
          </div>

          {/* Two Column Layout */}
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Health Checks */}
            <div className="rounded-xl bg-slate-800 p-6 shadow-lg">
              <div className="mb-6 flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-xl font-bold text-white">
                  <ChartBarIcon className="h-6 w-6 text-indigo-400" />
                  健康檢查
                </h2>
                <button
                  onClick={() => void triggerCheck()}
                  disabled={triggering}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white transition hover:bg-indigo-500 disabled:opacity-50"
                >
                  {triggering ? "執行中..." : "手動觸發"}
                </button>
              </div>
              <div className="space-y-4">
                {Object.entries(report.health.checks).map(([key, check]) => (
                  <div
                    key={key}
                    className="flex items-center justify-between rounded-lg bg-slate-700/50 p-4"
                  >
                    <div>
                      <p className="font-medium text-white capitalize">
                        {key.replace(/_/g, " ")}
                      </p>
                      <p className="text-sm text-slate-400">
                        {((check as any).message ?? `Status: ${check.status}`) as string}
                      </p>
                    </div>
                    <div className="text-right">
                      {getStatusIcon(check.status)}
                      {key === "agent_activity" && (check as any).starving_agents !== undefined && (check as any).starving_agents > 0 && (
                        <p className="mt-1 text-xs text-yellow-400">
                          {(check as any).starving_agents} 飢餓
                        </p>
                      )}
                      {key === "battle_logs" && (check as any).attacker_win_rate && (
                        <p className="mt-1 text-xs text-slate-400">
                          攻方勝率: {(check as any).attacker_win_rate}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Recommendations */}
              <div className="mt-6">
                <h3 className="mb-3 text-lg font-semibold text-white">建議</h3>
                <div className="space-y-2">
                  {report.health.recommendations.map((rec, idx) => (
                    <p key={idx} className="text-sm text-slate-300">
                      {rec}
                    </p>
                  ))}
                </div>
              </div>
            </div>

            {/* Game Analysis */}
            <div className="rounded-xl bg-slate-800 p-6 shadow-lg">
              <h2 className="mb-6 flex items-center gap-2 text-xl font-bold text-white">
                <ChartPieIcon className="h-6 w-6 text-indigo-400" />
                遊戲數據分析
              </h2>

              {/* Engagement */}
              <div className="mb-6">
                <h3 className="mb-3 text-lg font-semibold text-white">參與度</h3>
                <div className="grid grid-cols-3 gap-4">
                  <div className="rounded-lg bg-slate-700/50 p-3 text-center">
                    <p className="text-2xl font-bold text-white">
                      {report.game_analysis.engagement.active_1d}
                    </p>
                    <p className="text-xs text-slate-400">24h 活躍</p>
                  </div>
                  <div className="rounded-lg bg-slate-700/50 p-3 text-center">
                    <p className="text-2xl font-bold text-white">
                      {report.game_analysis.engagement.active_7d}
                    </p>
                    <p className="text-xs text-slate-400">7d 活躍</p>
                  </div>
                  <div className="rounded-lg bg-slate-700/50 p-3 text-center">
                    <p className="text-2xl font-bold text-white">
                      {report.game_analysis.engagement.total_agents}
                    </p>
                    <p className="text-xs text-slate-400">總玩家</p>
                  </div>
                </div>
              </div>

              {/* Balance Issues */}
              {report.game_analysis.balance_issues.length > 0 && (
                <div className="mb-6">
                  <h3 className="mb-3 text-lg font-semibold text-white">平衡問題</h3>
                  <div className="space-y-2">
                    {report.game_analysis.balance_issues.map((issue, idx) => (
                      <div
                        key={idx}
                        className={`rounded-lg p-3 ${
                          issue.severity === "high"
                            ? "bg-red-500/20"
                            : "bg-yellow-500/20"
                        }`}
                      >
                        <p className="text-sm text-white">
                          <span className="font-medium capitalize">{issue.type.replace(/_/g, " ")}:</span>{" "}
                          {issue.detail}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Economy Issues */}
              {report.game_analysis.economy_issues.length > 0 && (
                <div className="mb-6">
                  <h3 className="mb-3 text-lg font-semibold text-white">經濟問題</h3>
                  <div className="space-y-2">
                    {report.game_analysis.economy_issues.map((issue, idx) => (
                      <div
                        key={idx}
                        className={`rounded-lg p-3 ${
                          issue.severity === "high"
                            ? "bg-red-500/20"
                            : "bg-yellow-500/20"
                        }`}
                      >
                        <p className="text-sm text-white">{issue.detail}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Suggestions */}
              <div>
                <h3 className="mb-3 text-lg font-semibold text-white">建議</h3>
                <div className="space-y-2">
                  {report.game_analysis.suggestions.map((suggestion, idx) => (
                    <p key={idx} className="text-sm text-slate-300">
                      {suggestion}
                    </p>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Planned Features */}
          {report.planned_features.length > 0 && (
            <div className="mt-6 rounded-xl bg-slate-800 p-6 shadow-lg">
              <h2 className="mb-6 flex items-center gap-2 text-xl font-bold text-white">
                <CpuChipIcon className="h-6 w-6 text-amber-400" />
                功能開發計劃
              </h2>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {report.planned_features.map((feature, idx) => (
                  <div
                    key={idx}
                    className="rounded-lg border border-slate-600 bg-slate-700/30 p-4"
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <span
                        className={`rounded-full px-2 py-1 text-xs font-medium ${
                          feature.priority === 1
                            ? "bg-red-500/20 text-red-400"
                            : feature.priority === 2
                            ? "bg-yellow-500/20 text-yellow-400"
                            : "bg-slate-500/20 text-slate-400"
                        }`}
                      >
                        {feature.priority === 1 ? "高" : feature.priority === 2 ? "中" : "低"}優先
                      </span>
                      <span className="rounded-full bg-indigo-500/20 px-2 py-1 text-xs text-indigo-400">
                        {feature.category}
                      </span>
                    </div>
                    <h3 className="mb-2 font-semibold text-white">{feature.title}</h3>
                    <p className="mb-3 text-sm text-slate-400">{feature.description}</p>
                    <div className="flex flex-wrap gap-1">
                      {feature.files.map((file, fidx) => (
                        <span
                          key={fidx}
                          className="rounded bg-slate-600 px-2 py-1 text-xs text-slate-300"
                        >
                          {file.split("/").pop()}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Report Meta */}
          <div className="mt-6 text-center text-sm text-slate-500">
            報告 ID: {report.report_id} | 生成時間:{" "}
            {new Date(report.timestamp).toLocaleString("zh-TW", { timeZone: "Asia/Taipei" })}
          </div>
        </>
      )}

      {/* No Report State */}
      {!loading && !report && !error && (
        <div className="flex flex-col items-center justify-center py-20">
          <BellIcon className="mb-4 h-16 w-16 text-slate-600" />
          <h2 className="mb-2 text-xl font-semibold text-white">尚無報告</h2>
          <p className="mb-6 text-slate-400">
            每日報告在 UTC 02:00 自動生成，或點擊手動觸發
          </p>
          <button
            onClick={() => void triggerCheck()}
            disabled={triggering}
            className="rounded-lg bg-indigo-600 px-6 py-3 text-white transition hover:bg-indigo-500 disabled:opacity-50"
          >
            {triggering ? "執行中..." : "立即生成報告"}
          </button>
        </div>
      )}
    </main>
  );
}
