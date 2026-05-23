export type IntegrationStatus = "healthy" | "warning" | "critical" | "unknown";

export interface IntegrationSummary {
  integration_id: string;
  name: string;
  project: string;
  business_domain: string;
  owner: string;
  status: IntegrationStatus;
  failed_instances: number;
  connection_errors: number;
  timeouts: number;
  aborted_runs: number;
  scheduled_runs_missed: number;
  success_rate: number;
  last_run_at: string;
}

export interface IntegrationListResponse {
  total: number;
  limit: number;
  offset: number;
  items: IntegrationSummary[];
}

export interface ExecutiveSummary {
  health_score: number;
  total_integrations: number;
  healthy_count: number;
  warning_count: number;
  critical_count: number;
  unknown_count: number;
  critical_incidents: number;
  top_failing_integrations: IntegrationSummary[];
  last_refresh: string;
}

export interface Recommendation {
  priority: number;
  title: string;
  rationale: string;
  action: string;
}

export interface RunEvent {
  event_time: string;
  run_status: IntegrationStatus;
  duration_ms: number;
  error_type: string | null;
  message: string;
}

export interface IntegrationDetailResponse {
  integration: IntegrationSummary;
  endpoint_url: string;
  recommendations: Recommendation[];
  recent_runs: RunEvent[];
}

export interface LatencyLog {
  endpoint: string;
  method: string;
  latency_ms: number;
  created_at: string;
}

export interface FilterOptions {
  projects: string[];
  business_domains: string[];
}

export interface SettingsPayload {
  oic_base_url: string;
  auth_mode: string;
  polling_seconds: number;
  notification_email: string;
  threshold_issue_score_warning: number;
  threshold_issue_score_critical: number;
  threshold_missed_schedules_warning: number;
  threshold_missed_schedules_critical: number;
  threshold_critical_integrations_warning: number;
  threshold_critical_integrations_critical: number;
  webhook_enabled: boolean;
  webhook_url: string;
  webhook_bearer_token: string;
  webhook_max_retries: number;
  webhook_initial_backoff_seconds: number;
  webhook_timeout_seconds: number;
}

export interface AuthStatus {
  has_admin: boolean;
  authenticated_email: string | null;
}

export interface AuthPayload {
  email: string;
  password: string;
}

export interface AuthResponse {
  token: string;
  email: string;
}

export interface PasswordResetRequestPayload {
  email: string;
}

export interface PasswordResetRequestResponse {
  status: string;
  reset_code: string;
  expires_in_minutes: number;
}

export interface PasswordResetConfirmPayload {
  email: string;
  reset_code: string;
  new_password: string;
}

export interface SessionRevokeResponse {
  revoked_sessions: number;
}

export interface WebhookDeliveryLogItem {
  id: number;
  event_type: string;
  severity: string;
  status: "success" | "failed";
  attempts: number;
  http_status: number | null;
  error_message: string | null;
  created_at: string;
}

export interface WebhookDeliveryLogResponse {
  summary: {
    success: number;
    failed: number;
    total: number;
  };
  items: WebhookDeliveryLogItem[];
}

export interface AuditLogEntry {
  id: number;
  actor_email: string | null;
  action_type: string;
  target: string;
  details: string;
  created_at: string;
}

export interface TrendSnapshot {
  snapshot_date: string;
  healthy_count: number;
  warning_count: number;
  critical_count: number;
  unknown_count: number;
  health_score: number;
}

export type AlertSeverity = "critical" | "warning" | "info";

export interface AlertEvent {
  id: number;
  severity: AlertSeverity;
  integration_id: string;
  title: string;
  message: string;
  simulated_email_to: string;
  created_at: string;
  acknowledged: boolean;
  metric_type?: string | null;
  metric_value?: number | null;
}
