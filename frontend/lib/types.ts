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

// AI DevOps Report Types
export interface DevOpsHealthCheck {
  status: "healthy" | "warning" | "critical";
  checks: {
    database: { status: string; user_count?: number; agent_count?: number; message?: string };
    api_health: { status: string; response_time_ms?: number; message?: string };
    recent_errors: { status: string; failed_events_24h?: number; message?: string };
    agent_activity: { status: string; total_agents?: number; active_agents_7d?: number; starving_agents?: number; activity_rate?: string; message?: string };
    battle_logs: { status: string; battle_count_7d?: number; attacker_win_rate?: string; message?: string };
    federation_health: { status: string; total_peers?: number; active_peers_1h?: number; message?: string };
  };
  recommendations: string[];
}

export interface DevOpsPlannedFeature {
  title: string;
  description: string;
  priority: number;
  category: string;
  files: string[];
}

export interface DevOpsReport {
  report_id: string;
  timestamp: string;
  health: DevOpsHealthCheck;
  game_analysis: {
    balance_issues: Array<{ type: string; severity: string; detail: string; data?: any }>;
    economy_issues: Array<{ type: string; severity: string; detail: string; data?: any }>;
    engagement_metrics: {
      total_agents: number;
      active_1d: number;
      active_7d: number;
      active_30d: number;
      retention_1d: string;
      retention_7d: string;
      actions_per_day_7d: string;
      health: string;
    };
    suggestions: string[];
  };
  planned_features: DevOpsPlannedFeature[];
  summary: string;
}

export interface DevOpsReportHistoryItem {
  report_id: string;
  timestamp: string;
  health_status: string;
  summary: string;
}

/** 每日史記敘事層（免登入公開） */
export interface ChronicleStory {
  date: string;
  lang: string;
  city: string;
  headline: string;
  lines: string[];
  quotes: Array<{ name: string; text: string }>;
  aphorism: string;
  share_text: string;
  stats: Record<string, number>;
}

export interface ChronicleEntryItem {
  id: number;
  event_type: string;
  event_type_localized?: string;
  title: string;
  title_localized?: string;
  content: string;
  content_localized?: string;
  created_at: string;
}

export interface WorldEventItem {
  id: string;
  title: string;
  description: string;
  status: string;
  irreversible: boolean;
  timed: boolean;
  progress: string;
  deadline_utc?: string;
  opened_at?: string;
  outcome?: string | null;
  active_pacts?: number;
  betrayals?: number;
}

/** 每日 08:00 HKT 自動備妥的社群發文包（免登入公開） */
export interface ChroniclePostPackage {
  date: string;
  lang: string;
  headline: string;
  caption: string;
  caption_long: string;
  hashtags: string;
  image_url: string;
  link: string;
  share_text: string;
  battle?: BattleReportItem | null;
  battle_link?: string;
  battle_image_url?: string;
}

export interface PublicChronicleFeed {
  story: ChronicleStory | null;
  city: string;
  entries: ChronicleEntryItem[];
  events?: WorldEventItem[];
}

/** 三回合戰報回放（免登入公開） */
export interface BattleReportItem {
  battle_id: string;
  mode: "arena" | "pve" | "pvp";
  exhibition: boolean;
  created_at: string;
  attacker_name: string;
  defender_name: string;
  attacker_city: string;
  defender_city: string;
  attacker_power: number;
  defender_power: number;
  outcome: string;
  spoils: { gold: number; food: number };
  replay_url: string;
  api_url: string;
}

export interface BattleRound {
  round: number;
  attacker_action: string;
  defender_action: string;
  attacker_label: string;
  defender_label: string;
  casualties: {
    attacker: Record<string, number>;
    defender: Record<string, number>;
  };
  attacker_loss: number;
  defender_loss: number;
  attacker_remaining: number;
  defender_remaining: number;
  caption: string;
}

export interface BattleReplay {
  battle_id: string;
  mode: "arena" | "pve" | "pvp";
  lang: string;
  exhibition: boolean;
  exhibition_note: string;
  date: string;
  created_at: string;
  summary: {
    attacker_name: string;
    defender_name: string;
    attacker_city: string;
    defender_city: string;
    attacker_power: number;
    defender_power: number;
    outcome: string;
    spoils: { gold: number; food: number };
  };
  combatants: {
    attacker: { name: string; troops: number };
    defender: { name: string; troops: number };
  };
  rounds: BattleRound[];
  verdict: string;
  links: { replay: string; card_png: string; card_svg: string };
}

export interface BattlePostPackage {
  type: string;
  date: string;
  lang: string;
  battle_id: string;
  headline: string;
  caption: string;
  caption_long: string;
  verdict: string;
  hashtags: string;
  image_url: string;
  link: string;
  exhibition: boolean;
}

/** 十四日賽季（免登入公開） */
export interface SeasonLeaderRow {
  agent_id: number;
  name: string;
  city: string;
  role: string;
  reputation: number;
  troops: number;
  gold: number;
  food: number;
  wins: number;
  faction: boolean;
  breakdown: {
    reputation: number;
    troops: number;
    gold: number;
    food: number;
    wins: number;
    faction: number;
  };
  score: number;
  rank: number;
  total: number;
  title_zh: string;
  title_en: string;
  ending_zh: string;
  ending_en: string;
}

export interface SeasonRules {
  length_days: number;
  score_formula_zh: string;
  score_formula_en: string;
  winner_zh: string;
  winner_en: string;
  exclusions_zh: string;
  exclusions_en: string;
}

export interface SeasonHistoryItem {
  season_id: string;
  index: number;
  start_date: string;
  end_date: string;
  total_agents: number;
  winner_name: string | null;
  winner_score: number;
  aphorism_zh: string;
  aphorism_en: string;
  chronicle?: string;
}

export interface SeasonSummary {
  enabled: boolean;
  season: {
    season_id: string;
    index: number;
    start_date: string;
    end_date: string;
    status: string;
    opened_at: string;
  } | null;
  days_left: number | null;
  total_agents: number;
  leaderboard: SeasonLeaderRow[];
  rules: SeasonRules;
  previous: SeasonHistoryItem | null;
  history_count: number;
  note: string;
}

export interface SeasonArchive {
  season_id: string;
  index: number;
  start_date: string;
  end_date: string;
  closed_at: string;
  total_agents: number;
  winner: SeasonLeaderRow | null;
  standings: SeasonLeaderRow[];
  chronicle: string;
  aphorism: string;
}

export interface SeasonPostPackage {
  type: string;
  date: string;
  lang: string;
  season_id: string;
  closed: boolean;
  headline: string;
  caption: string;
  caption_long: string;
  image_url: string;
  link: string;
  hashtags: string;
  agent: {
    agent_id: number;
    name: string;
    rank: number;
    score: number;
    title: string;
  } | null;
}

export interface AudienceAgent {
  agent_id: number;
  name: string;
  city: string;
  troops: number;
}

export interface AudienceStanding extends AudienceAgent {
  cheers: number;
}

export interface AudienceMorale {
  challenger_votes: number;
  defender_votes: number;
  total_votes: number;
  boost: number;
  boost_pct: number;
  applied: boolean;
  cap_pct: number;
  min_votes: number;
}

export interface AudienceRules {
  one_per_day_zh: string;
  one_per_day_en: string;
  target_zh: string;
  target_en: string;
  min_votes: number;
  boost_cap_pct: number;
  full_participation_votes: number;
  exclusions_zh: string;
  exclusions_en: string;
  note: string;
}

export interface AudienceToday {
  enabled: boolean;
  date: string;
  target_date: string;
  target_hour_hkt: number;
  already_cheered: boolean;
  already_voted: boolean;
  cheer_total: number;
  cheer_standings: AudienceStanding[];
  votes: { challenger: number; defender: number };
  morale: AudienceMorale;
  agents: AudienceAgent[];
  rules: AudienceRules;
  note: string;
}

export interface AudienceActionResult {
  recorded: boolean;
  reason: string | null;
  target_date: string;
  side?: string;
}

export interface AudiencePostPackage {
  type: string;
  date: string;
  target_date: string;
  lang: string;
  headline: string;
  caption: string;
  caption_long: string;
  hashtags: string;
  image_url: string;
  link: string;
  share_text: string;
  cheer_total: number;
  standings: AudienceStanding[];
  votes: { challenger: number; defender: number };
  morale: AudienceMorale;
}

export interface TrackedChannelLink {
  code: string;
  url: string;
  label: string;
  target: string;
  clicks: number;
  human_clicks: number;
  caption: string;
  caption_long: string;
}

export interface LinkToday {
  date: string;
  lang: string;
  links: Record<string, TrackedChannelLink>;
  share_url: string;
  headline: string;
  image_url: string;
  note: string;
}

export interface LinkStatsDay {
  date: string;
  clicks: number;
  human_clicks: number;
  by_channel: Record<string, number>;
}

export interface LinkStats {
  days: number;
  total_clicks: number;
  total_human_clicks: number;
  by_channel: Record<string, number>;
  per_day: LinkStatsDay[];
  note: string;
}

export interface OutboxItem {
  date: string;
  status: string;
  provisional?: boolean;
  channel?: string;
  headline?: string;
  caption?: string;
  caption_long?: string;
  image_url?: string;
  share_url?: string;
  links?: Record<string, TrackedChannelLink>;
}

export interface LinkOutbox {
  days: number;
  items: OutboxItem[];
  count: number;
}

export interface QuestRow {
  id: number;
  agent_id: number;
  agent_name: string;
  type: string;
  target: number;
  current_progress: number;
  is_completed: boolean;
  is_claimed: boolean;
  description: string;
  reward_gold: number;
  reward_food: number;
  reward_reputation: number;
}

export interface QuestClaimResult {
  quest_type: string;
  reward_gold: number;
  reward_food: number;
  reward_reputation: number;
  new_gold: number;
  new_food: number;
  new_reputation: number;
}

export interface MarketItem {
  item_id: string;
  name: string;
  description: string;
  unit_price_gold: number;
  food_per_unit: number;
  energy_per_unit: number;
}

export interface MarketCatalog {
  items: MarketItem[];
  max_quantity_per_purchase: number;
  currency: string;
  how_to_buy: {
    method: string;
    path: string;
    auth: string;
    body: { action_type: string; payload: { item: string; quantity: number } };
  };
  note_zh: string;
  note_en: string;
}

export interface UpdateItem {
  date: string;
  version: string;
  title: string;
  detail: string;
  tags: string[];
  docs: string[];
}

export interface SystemUpdates {
  revision: string;
  app_version: string;
  updated_at: string;
  last_checked_at: string;
  count: number;
  items: UpdateItem[];
  docs: Record<string, string>;
  how_to_use_zh: string;
  how_to_use_en: string;
}

export interface ScoutBudget {
  gold: number;
  talent_chance: number;
  supply_chance: number;
  ability_gain: number;
}

export interface ScoutFeedItem {
  agent_id: number;
  agent_name: string;
  date: string;
  focus: string;
  budget: number;
  outcome: string;
  summary_zh: string;
  summary_en: string;
}

export interface ScoutRules {
  lang: string;
  daily_limit: number;
  energy_cost: number;
  focus_options: string[];
  focus_bonus: number;
  budgets: ScoutBudget[];
  how_to_scout: {
    method: string;
    path: string;
    auth: string;
    body: { action_type: string; payload: { focus: string; budget: number } };
  };
  recent: ScoutFeedItem[];
  recent_date: string;
  note_zh: string;
  note_en: string;
}

export interface RecoveryCandidate {
  agent_id: number;
  name: string;
  role: string;
  current_city: string;
  created_at: string | null;
  is_claimed: boolean;
  has_claim_ticket: boolean;
  claim_ticket_used: boolean;
}

export interface ClaimRecoveryResult {
  agent_id: number;
  name: string;
  status: "claimed" | "already_claimed" | "transferred";
  transferred_from_another_user: boolean;
  ownership_repaired: boolean;
  claimed_by_user_id: number;
}

export interface AgentRenameResult {
  agent_id: number;
  old_name: string;
  name: string;
  next_rename_at: string | null;
  cooldown_days: number;
}
