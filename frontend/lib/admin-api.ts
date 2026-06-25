import {
  AgentInboxItem,
  AgentInboxMessage,
  AnnouncementItem,
  AdminAgentRow,
  AdminUserRow,
  ApiKeyItem,
  ApiResponse,
  AuthMe,
  DevOpsReport,
  FederationPeer,
  FederationStatus,
  RegisterPayload,
  UserCredentials,
  ViewerAgentSummary
} from "@/lib/types";

const ADMIN_API_BASE_URL = process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL ?? "http://100.64.0.5:10090/api";

interface AdminAuthTokens {
  token: string;
  refresh_token: string;
  token_type?: string;
  expires_in?: number;
  refresh_expires_in?: number;
}

const clearAdminAuth = () => {
  if (typeof window === "undefined") return;
  localStorage.removeItem("admin_token");
  localStorage.removeItem("admin_refresh_token");
};

const getAdminToken = () => {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("admin_token");
};

async function adminRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const baseHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string> | undefined) ?? {})
  };
  const token = getAdminToken();
  if (token) {
    baseHeaders.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${ADMIN_API_BASE_URL}${path}`, {
    ...init,
    headers: baseHeaders,
    cache: "no-store"
  });
  const raw = await response.json();
  const payload = raw as ApiResponse<T>;

  if (!response.ok || !payload.success) {
    const detailMsg = Array.isArray((raw as { detail?: Array<{ msg?: string }> }).detail)
      ? (raw as { detail: Array<{ msg?: string }> }).detail[0]?.msg
      : undefined;
    const errMsg = payload.error?.message ?? detailMsg ?? `Request failed: ${response.status}`;
    const error = new Error(errMsg) as Error & { code?: string; status?: number };
    error.code = payload.error?.code;
    error.status = response.status;
    throw error;
  }

  return payload.data as T;
}

export const adminApi = {
  // Auth
  login: async (username: string, password: string): Promise<AdminAuthTokens> => {
    const response = await fetch(`${ADMIN_API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    const raw = await response.json();
    const payload = raw as ApiResponse<AdminAuthTokens>;

    if (!response.ok || !payload.success || !payload.data) {
      const errMsg = payload.error?.message ?? "Login failed";
      throw new Error(errMsg);
    }

    // Store tokens
    if (typeof window !== "undefined") {
      localStorage.setItem("admin_token", payload.data.token);
      localStorage.setItem("admin_refresh_token", payload.data.refresh_token);
    }

    return payload.data;
  },

  logout: () => {
    clearAdminAuth();
  },

  getMe: () => adminRequest<{ user_id: number; username: string; email: string; is_admin: boolean }>("/auth/me"),

  // Admin Overview
  adminOverview: () => adminRequest<{
    users: AdminUserRow[];
    agents: AdminAgentRow[];
    announcements: AnnouncementItem[];
  }>("/admin/overview"),

  // User Management
  adminListUsers: (params: {
    query?: string;
    is_admin?: "all" | "true" | "false";
    page?: number;
    page_size?: number;
  }) => {
    const q = new URLSearchParams();
    if (params.query) q.set("query", params.query);
    if (params.is_admin) q.set("is_admin", params.is_admin);
    if (params.page) q.set("page", String(params.page));
    if (params.page_size) q.set("page_size", String(params.page_size));
    return adminRequest<{
      items: AdminUserRow[];
      total: number;
      page: number;
      page_size: number;
      total_pages: number;
    }>(`/admin/users?${q.toString()}`);
  },

  adminUpdateUser: (userId: number, payload: {
    username?: string;
    email?: string;
    is_admin?: boolean;
  }) => adminRequest<{
    id: number;
    username: string;
    email: string;
    is_admin: boolean;
  }>(`/admin/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  }),

  adminDeleteUser: (userId: number) =>
    adminRequest<{ deleted: boolean; user_id: number }>(`/admin/users/${userId}`, { method: "DELETE" }),

  adminResetUserPassword: (userId: number, newPassword: string) =>
    adminRequest<{ user_id: number; password_reset: boolean }>(`/admin/users/${userId}/reset-password`, {
      method: "POST",
      body: JSON.stringify({ new_password: newPassword })
    }),

  // Agent Management
  adminListAgents: (params: {
    query?: string;
    role?: string;
    owner_user_id?: number;
    page?: number;
    page_size?: number;
  }) => {
    const q = new URLSearchParams();
    if (params.query) q.set("query", params.query);
    if (params.role) q.set("role", params.role);
    if (params.owner_user_id !== undefined) q.set("owner_user_id", String(params.owner_user_id));
    if (params.page) q.set("page", String(params.page));
    if (params.page_size) q.set("page_size", String(params.page_size));
    return adminRequest<{
      items: AdminAgentRow[];
      total: number;
      page: number;
      page_size: number;
      total_pages: number;
    }>(`/admin/agents?${q.toString()}`);
  },

  adminUpdateAgent: (agentId: number, payload: {
    name?: string;
    role?: string;
    home_city?: string;
    current_city?: string;
    energy?: number;
    gold?: number;
    food?: number;
  }) => adminRequest<{ id: number; name: string; role: string }>(`/admin/agents/${agentId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  }),

  adminDeleteAgent: (agentId: number) =>
    adminRequest<{ deleted: boolean; agent_id: number }>(`/admin/agents/${agentId}`, { method: "DELETE" }),

  adminRegenerateAgentClaimCode: (agentId: number) =>
    adminRequest<{
      agent_id: number;
      claim_code: string;
      claim_expires_at: string;
      claim_used_at?: string | null;
    }>(`/admin/agents/${agentId}/claim-code/regenerate`, { method: "POST" }),

  adminUpdateAgentClaimExpiry: (agentId: number, payload: { expires_at: string }) =>
    adminRequest<{
      agent_id: number;
      claim_code?: string | null;
      claim_expires_at: string;
    }>(`/admin/agents/${agentId}/claim-code/expiry`, { method: "PATCH", body: JSON.stringify(payload) }),

  // Announcement Management
  adminCreateAnnouncement: (payload: { title: string; content: string; published: boolean }) =>
    adminRequest<{ id: number; title: string; content: string; published: boolean }>("/admin/announcements", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  adminUpdateAnnouncement: (announcementId: number, payload: {
    title?: string;
    content?: string;
    published?: boolean;
  }) => adminRequest<{ id: number; title: string; content: string; published: boolean }>(
    `/admin/announcements/${announcementId}`,
    { method: "PATCH", body: JSON.stringify(payload) }
  ),

  adminDeleteAnnouncement: (announcementId: number) =>
    adminRequest<{ deleted: boolean; announcement_id: number }>(`/admin/announcements/${announcementId}`, {
      method: "DELETE"
    }),

  // AI DevOps
  getDevOpsReport: () => adminRequest<DevOpsReport>("/admin/devops/report"),

  triggerDevOpsCheck: () => adminRequest<{
    message: string;
    report_id: string;
    summary: string;
  }>("/admin/devops/trigger"),

  // Daily Reset
  triggerDailyReset: () => adminRequest<{ success: boolean; data: any }>("/admin/daily-reset", { method: "POST" })
};
