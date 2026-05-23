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
}
