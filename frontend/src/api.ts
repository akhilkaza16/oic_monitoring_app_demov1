import {
  AlertEvent,
  AuditLogEntry,
  AuthPayload,
  AuthResponse,
  AuthStatus,
  ExecutiveSummary,
  FilterOptions,
  IntegrationDetailResponse,
  IntegrationListResponse,
  LatencyLog,
  SettingsPayload,
  TrendSnapshot,
} from "./types";

const API_BASE = process.env.REACT_APP_BACKEND_URL;

if (!API_BASE) {
  throw new Error("REACT_APP_BACKEND_URL is required in frontend/.env");
}

const ADMIN_TOKEN_STORAGE_KEY = "badger-admin-token";

export function getStoredAdminToken(): string | null {
  return window.localStorage.getItem(ADMIN_TOKEN_STORAGE_KEY);
}

export function setStoredAdminToken(token: string): void {
  window.localStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, token);
}

export function clearStoredAdminToken(): void {
  window.localStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
}

interface RequestOptions extends RequestInit {
  authToken?: string | null;
}

async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  const { authToken, ...restInit } = init ?? {};
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((restInit.headers as Record<string, string> | undefined) ?? {}),
  };
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    headers,
    ...restInit,
  });

  if (!response.ok) {
    const details = await response.text();
    throw new Error(`Request failed: ${response.status} ${details}`);
  }

  return (await response.json()) as T;
}

export function getExecutiveSummary(): Promise<ExecutiveSummary> {
  return request<ExecutiveSummary>("/api/executive-summary");
}

export interface IntegrationQuery {
  status?: string;
  project?: string;
  business_domain?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export function getIntegrations(query: IntegrationQuery): Promise<IntegrationListResponse> {
  const searchParams = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      searchParams.set(key, String(value));
    }
  });
  return request<IntegrationListResponse>(`/api/integrations?${searchParams.toString()}`);
}

export function getFilterOptions(): Promise<FilterOptions> {
  return request<FilterOptions>("/api/filter-options");
}

export function getIntegrationDetail(integrationId: string): Promise<IntegrationDetailResponse> {
  return request<IntegrationDetailResponse>(`/api/integrations/${integrationId}`);
}

export function getLatencyLogs(endpoint?: string, limit = 20): Promise<LatencyLog[]> {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (endpoint) {
    params.set("endpoint", endpoint);
  }
  return request<LatencyLog[]>(`/api/latency-logs?${params.toString()}`);
}

export function runMockCollectorCycle(authToken?: string | null): Promise<{ updated_integrations: number }> {
  return request<{ updated_integrations: number }>("/api/mock-collector/run", {
    method: "POST",
    authToken,
  });
}

export function getAuthStatus(authToken?: string | null): Promise<AuthStatus> {
  return request<AuthStatus>("/api/auth/status", { authToken });
}

export function registerAdmin(payload: AuthPayload): Promise<AuthResponse> {
  return request<AuthResponse>("/api/auth/register-admin", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function loginAdmin(payload: AuthPayload): Promise<AuthResponse> {
  return request<AuthResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getSettings(authToken: string): Promise<SettingsPayload> {
  return request<SettingsPayload>("/api/settings", { authToken });
}

export function updateSettings(
  payload: SettingsPayload,
  authToken: string
): Promise<SettingsPayload & { updated_at: string }> {
  return request<SettingsPayload & { updated_at: string }>("/api/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
    authToken,
  });
}

export function getAuditLogs(authToken: string, limit = 80): Promise<AuditLogEntry[]> {
  return request<AuditLogEntry[]>(`/api/audit-logs?limit=${limit}`, { authToken });
}

export function getTrendSnapshots(days = 30): Promise<TrendSnapshot[]> {
  return request<TrendSnapshot[]>(`/api/trends?days=${days}`);
}

export function getAlerts(limit = 20): Promise<AlertEvent[]> {
  return request<AlertEvent[]>(`/api/alerts?limit=${limit}`);
}

export function acknowledgeAlert(alertId: number, authToken: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/api/alerts/${alertId}/acknowledge`, {
    method: "POST",
    authToken,
  });
}
