import {
  AdminAgentRow,
  AdminUserRow,
  ApiKeyItem,
  ApiResponse,
  AuthMe,
  FederationPeer,
  FederationStatus,
  RegisterPayload,
  UserCredentials,
  ViewerAgentSummary
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = typeof window === "undefined" ? null : localStorage.getItem("token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string> | undefined) ?? {})
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store"
  });

  const raw = await response.json();
  const payload = raw as ApiResponse<T>;
  if (!response.ok || !payload.success) {
    const detailMsg = Array.isArray((raw as { detail?: Array<{ msg?: string }> }).detail)
      ? (raw as { detail: Array<{ msg?: string }> }).detail[0]?.msg
      : undefined;
    const errMsg = payload.error?.message ?? detailMsg ?? `Request failed: ${response.status}`;
    throw new Error(errMsg);
  }

  return payload.data as T;
}

export const apiClient = {
  registerUser: (payload: RegisterPayload) =>
    request<{ user_id: number; username: string; email: string; is_admin: boolean }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  login: (payload: UserCredentials) =>
    request<{ token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  getMe: () => request<AuthMe>("/auth/me"),
  forgotPassword: (payload: { email: string }) =>
    request<{ sent: boolean }>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  resetPassword: (payload: { email: string; code: string; new_password: string }) =>
    request<{ reset: boolean }>("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  registerAgent: (payload: { name: string; role: string }) =>
    request<{ agent_id: number; name: string; role: string }>("/agent/register", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  listMyAgents: () =>
    request<{
      items: Array<{
        id: number;
        name: string;
        role: string;
        home_city: string;
        current_city: string;
        energy: number;
        gold: number;
        food: number;
        lord_agent_id?: number | null;
        faction_id?: number | null;
      }>;
    }>("/agent/mine"),
  promoteAgent: (payload: { agent_id: number; target_role: string }) =>
    request<{ agent_id: number; role: string; gold: number; promotion_cost: number }>("/agent/promote", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  getAgentStatus: (agentId: number) => request(`/agent/status?agent_id=${agentId}`),

  getWorldState: () => request("/world/state"),
  getCityRoster: () =>
    request<{
      city_name: string;
      city_location?: string;
      civil_hierarchy: Array<{ key: string; role: string; branch: string; tier: number; promotion_cost: number; bonus: Record<string, number> }>;
      military_hierarchy: Array<{ key: string; role: string; branch: string; tier: number; promotion_cost: number; bonus: Record<string, number> }>;
      agents: Array<{
        id: number;
        name: string;
        role: string;
        branch: string;
        tier: number;
        bonus: Record<string, number>;
        energy: number;
        gold: number;
        food: number;
        faction_id?: number | null;
      }>;
    }>("/world/city/roster"),
  getPublicWorldState: () => request("/world/public/state"),
  getWorldManifest: () => request<{ supported_roles?: string[] }>("/world/manifest"),
  getRankings: () => request("/world/rankings"),
  getPublicRankings: () => request("/world/public/rankings"),
  getChronicle: (lang?: "en" | "zh") =>
    request(`/world/chronicle?limit=40${lang ? `&lang=${lang}` : ""}`),

  createFaction: (payload: { name: string; leader_agent_id: number }) =>
    request("/social/faction/create", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  listFactions: () => request<{ factions: Array<Record<string, unknown>> }>("/social/factions"),
  recruit: (payload: { lord_agent_id: number; target_agent_id: number }) =>
    request<{
      lord_agent_id: number;
      target_agent_id: number;
      faction_id?: number | null;
      status: string;
      vassal_bonus_pct: number;
      lord_bonus_pct: number;
    }>(`/social/recruit?lord_agent_id=${payload.lord_agent_id}&target_agent_id=${payload.target_agent_id}`, {
      method: "POST"
    }),
  joinLord: (payload: { agent_id: number; lord_agent_id: number }) =>
    request<{
      agent_id: number;
      lord_agent_id: number;
      faction_id?: number | null;
      vassal_bonus_pct: number;
      lord_bonus_pct: number;
    }>("/social/join-lord", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  listDialogues: (limit = 100) =>
    request<{
      owned_agents: Array<{ id: number; name: string; role: string; current_city: string }>;
      messages: Array<{
        id: number;
        from_agent_id: number;
        from_agent_name: string;
        to_agent_id: number;
        to_agent_name: string;
        message_type: string;
        content: string;
        status: string;
        created_at: string;
      }>;
    }>(`/social/dialogues?limit=${limit}`),

  listPeers: () => request<{ peers: FederationPeer[] }>("/federation/v1/peers"),
  federationStatus: () => request<FederationStatus>("/federation/v1/status"),

  listApiKeys: () => request<{ items: ApiKeyItem[] }>("/api-keys"),
  createApiKey: (payload: { name: string; agent_id?: number }) =>
    request<{ id: number; key: string; name: string; key_preview: string; created_at: string }>("/api-keys", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  revokeApiKey: (keyId: number) =>
    request<{ id: number; revoked: boolean }>(`/api-keys/${keyId}`, {
      method: "DELETE"
    }),

  bootstrapAIAgent: (payload: {
    agent_name: string;
    role: string;
    faction_name?: string;
    key_name?: string;
    username?: string;
    password?: string;
  }) =>
    request<{
      ai_account: { user_id: number; username: string; password: string };
      token: string;
      agent: { agent_id: number; name: string; role: string };
      api_key: { id: number; name: string; key: string; key_preview: string };
      claim_code: string;
      claim_expires_at: string;
      faction?: { faction_id: number; name: string } | null;
    }>("/automation/agent/bootstrap", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  regenerateClaimCode: (agentId: number) =>
    request<{
      agent_id: number;
      name: string;
      claim_code: string;
      claim_expires_at: string;
      abilities: { martial: number; intelligence: number; charisma: number; politics: number };
    }>(`/automation/agent/${agentId}/claim-code/regenerate`, {
      method: "POST"
    }),

  claimAgent: (payload: { claim_code: string }) =>
    request<{ agent_id: number; name: string; role: string; current_city: string }>("/viewer/claim", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  listClaimedAgents: () => request<{ items: ViewerAgentSummary[] }>("/viewer/agents"),
  getClaimedAgentOverview: (agentId: number) => request(`/viewer/agent/${agentId}/overview`),

  adminOverview: () => request<{ users: AdminUserRow[]; agents: AdminAgentRow[] }>("/admin/overview"),
  adminDeleteUser: (userId: number) =>
    request<{ deleted: boolean; user_id: number }>(`/admin/users/${userId}`, { method: "DELETE" }),
  adminDeleteAgent: (agentId: number) =>
    request<{ deleted: boolean; agent_id: number }>(`/admin/agents/${agentId}`, { method: "DELETE" }),
  adminResetUserPassword: (userId: number, payload: { new_password: string }) =>
    request<{ user_id: number; password_reset: boolean }>(`/admin/users/${userId}/reset-password`, {
      method: "POST",
      body: JSON.stringify(payload)
    })
};
