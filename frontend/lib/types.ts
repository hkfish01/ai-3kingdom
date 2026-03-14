export interface ApiErrorPayload {
  code: string;
  message: string;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: ApiErrorPayload;
}

export interface UserCredentials {
  username: string;
  password: string;
}

export interface RegisterPayload extends UserCredentials {
  email: string;
}

export interface AgentSummary {
  id: number;
  name: string;
  role: string;
  energy: number;
  gold: number;
  food: number;
  current_city: string;
  home_city: string;
  faction_id?: number | null;
  lord_agent_id?: number | null;
}

export interface WorldState {
  city: string;
  agent_count: number;
  prosperity: number;
  defense_power: number;
  treasury: {
    gold: number;
    food: number;
  };
}

export interface FederationPeer {
  city_name: string;
  base_url: string;
  trust_status: string;
  protocol_version: string;
  rule_version: string;
  last_seen_at: string;
}

export interface FederationStatus {
  city_name: string;
  protocol_version: string;
  rule_version: string;
  agent_count: number;
  prosperity: number;
  open_for_migration: boolean;
  timestamp: string;
}

export interface ApiKeyItem {
  id: number;
  name: string;
  agent_id?: number | null;
  key_preview: string;
  revoked: boolean;
  created_at: string;
  last_used_at?: string | null;
}

export interface ViewerAgentSummary {
  agent_id: number;
  name: string;
  role: string;
  home_city: string;
  current_city: string;
  energy: number;
  gold: number;
  food: number;
  faction_id?: number | null;
  claimed_at: string;
}

export interface AuthMe {
  user_id: number;
  username: string;
  email: string;
  is_admin: boolean;
}

export interface AdminUserRow {
  id: number;
  username: string;
  email: string;
  is_admin: boolean;
  created_at: string;
  agent_count: number;
}

export interface AdminAgentRow {
  id: number;
  name: string;
  owner_user_id: number;
  role: string;
  home_city: string;
  current_city: string;
  energy: number;
  gold: number;
  food: number;
  created_at: string;
}
