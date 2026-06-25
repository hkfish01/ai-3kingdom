"use client";

import { useEffect, useState } from "react";
import {
  ChartBarIcon,
  ChartPieIcon,
  CpuChipIcon,
  BellIcon,
  ArrowTrendingUpIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  XCircleIcon,
  UserGroupIcon,
} from "@heroicons/react/24/outline";
import { adminApi } from "@/lib/admin-api";
import type { DevOpsReport, DevOpsReportHistoryItem } from "@/lib/types";
import AdminShell from "@/components/admin-shell";

export default function AdminDashboardPage() {
  const [report, setReport] = useState<DevOpsReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [triggering, setTriggering] = useState(false);
  const [history, setHistory] = useState<DevOpsReportHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);

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

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const data = await adminApi.getDevOpsReportHistory();
      setHistory(data);
    } catch {
      // silent fail for history
    } finally {
      setHistoryLoading(false);
    }
  };

  const triggerCheck = async () => {
    setTriggering(true);
    setError("");
    setSuccess("");
    try {
      const result = await adminApi.triggerDevOpsCheck();
      await loadReport();
      setSuccess(result.summary ?? "生成完成");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger check");
    } finally {
      setTriggering(false);
    }
  };

  useEffect(() => {
    void loadReport();
    void loadHistory();
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
    <AdminShell>
      {/* Loading State */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="h-12 w-12 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="mb-4 rounded-lg bg-red-500/20 p-4 text-red-400">
            {error}
          </div>
        )}

        {/* Success State */}
        {success && (
          <div className="mb-4 rounded-lg bg-emerald-500/20 p-4 text-emerald-400">
            {success}
          </div>
        )}

        {/* Report History */}
        {!loading && (
          <div className="mb-6 rounded-xl bg-slate-800 p-4 shadow-lg">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-bold text-white">報告歷史</h2>
              <button
                onClick={() => void loadHistory()}
                disabled={historyLoading}
                className="text-xs text-slate-400 hover:text-white disabled:opacity-50"
              >
                {historyLoading ? "載入中..." : "刷新"}
              </button>
            </div>
            {historyLoading ? (
              <div className="flex items-center justify-center py-4">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
              </div>
            ) : history.length === 0 ? (
              <p className="text-sm text-slate-500">暫無歷史報告</p>
            ) : (
              <div className="flex gap-2 overflow-x-auto pb-1">
                {history.map((item) => {
                  const isActive = item.report_id === report?.report_id;
                  return (
                    <button
                      key={item.report_id}
                      onClick={() => setSelectedReportId(item.report_id)}
                      className={`min-w-[160px] flex-shrink-0 rounded-lg border p-3 text-left text-xs transition ${
                        isActive
                          ? "border-indigo-500 bg-indigo-500/20 text-white"
                          : "border-slate-600 bg-slate-700/50 text-slate-300 hover:border-slate-500 hover:bg-slate-700"
                      }`}
                    >
                      <div className="mb-1 flex items-center gap-1">
                        <span className={`h-2 w-2 rounded-full ${
                          item.health_status === "healthy" ? "bg-emerald-400"
                          : item.health_status === "warning" ? "bg-yellow-400"
                          : "bg-red-400"
                        }`} />
                        <span className="font-semibold">{item.health_status === "healthy" ? "健康" : item.health_status === "warning" ? "警告" : "危險"}</span>
                      </div>
                      <p className="truncate text-slate-400">
                        {new Date(item.timestamp).toLocaleString("zh-TW", {
                          timeZone: "Asia/Taipei",
                          month: "numeric",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </p>
                      <p className="mt-1 line-clamp-2 leading-tight text-slate-400">
                        {item.summary.replace(/\|/g, " ")}
                      </p>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Main Content */}
        {!loading && report && report.health && report.game_analysis && (
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
                  {report.game_analysis.engagement_metrics.active_1d}
                </p>
                <p className="text-sm text-slate-400">
                  / {report.game_analysis.engagement_metrics.total_agents} 總計
                </p>
              </div>

              {/* Retention */}
              <div className="rounded-xl bg-slate-800 p-6 shadow-lg">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="text-sm font-medium text-slate-400">日留存率</h3>
                  <ArrowTrendingUpIcon className="h-6 w-6 text-emerald-400" />
                </div>
                <p className="text-2xl font-bold text-emerald-400">
                  {report.game_analysis.engagement_metrics.retention_1d}
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
                        {report.game_analysis.engagement_metrics.active_1d}
                      </p>
                      <p className="text-xs text-slate-400">24h 活躍</p>
                    </div>
                    <div className="rounded-lg bg-slate-700/50 p-3 text-center">
                      <p className="text-2xl font-bold text-white">
                        {report.game_analysis.engagement_metrics.active_7d}
                      </p>
                      <p className="text-xs text-slate-400">7d 活躍</p>
                    </div>
                    <div className="rounded-lg bg-slate-700/50 p-3 text-center">
                      <p className="text-2xl font-bold text-white">
                        {report.game_analysis.engagement_metrics.total_agents}
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
        {!loading && (!report || !report.health) && !error && (
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
    </AdminShell>
  );
}
