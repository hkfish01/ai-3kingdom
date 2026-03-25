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
  claim_code?: string | null;
  claim_expires_at?: string | null;
  claim_used_at?: string | null;
}

export interface AgentInboxItem {
  peer_agent_id: number;
  peer_agent_name: string;
  peer_agent_role: string;
  latest_message_id: number;
  latest_message_type: string;
  latest_content: string;
  latest_from_agent_id: number;
  latest_to_agent_id: number;
  latest_at: string;
  unread_count: number;
  unreplied_count: number;
  pending_count: number;
  thread_status: "unreplied" | "unread" | "synced";
}

export interface AgentInboxMessage {
  id: number;
  from_agent_id: number;
  to_agent_id: number;
  message_type: string;
  content: string;
  status: string;
  read_at?: string | null;
  replied_at?: string | null;
  created_at: string;
}

export interface AnnouncementItem {
  id: number;
  title: string;
  content: string;
  published: boolean;
  created_by_user_id?: number;
  created_at: string;
  updated_at: string;
}
