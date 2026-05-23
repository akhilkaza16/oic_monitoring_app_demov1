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
function getCookieValue(name: string): string | null {
  const cookies = document.cookie.split(";").map((cookie) => cookie.trim());
  const target = cookies.find((cookie) => cookie.startsWith(`${name}=`));
  return target ? decodeURIComponent(target.split("=", 2)[1]) : null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const restInit = init ?? {};
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((restInit.headers as Record<string, string> | undefined) ?? {}),
  };

  const method = (restInit.method ?? "GET").toUpperCase();
  const csrfProtectedMethods = ["POST", "PUT", "PATCH", "DELETE"];
  if (csrfProtectedMethods.includes(method)) {
    const csrfToken = getCookieValue("csrf_token");
    if (csrfToken) {
      headers["X-CSRF-Token"] = csrfToken;
    }
  }

  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers,
    ...restInit,
  });

  if (!response.ok) {
    const contentType = response.headers.get("content-type") || "";
    let details = "";
    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as { detail?: string | Record<string, unknown> };
      if (typeof payload.detail === "string") {
        details = payload.detail;
      } else if (payload.detail) {
        details = JSON.stringify(payload.detail);
      }
    } else {
      details = await response.text();
    }

    const message = details ? `${response.status}: ${details}` : `Request failed with status ${response.status}`;
    throw new Error(message);
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

export function runMockCollectorCycle(): Promise<{ updated_integrations: number }> {
  return request<{ updated_integrations: number }>("/api/mock-collector/run", {
    method: "POST",
  });
}

export function getAuthStatus(): Promise<AuthStatus> {
  return request<AuthStatus>("/api/auth/status");
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

export function logoutAdmin(): Promise<{ status: string }> {
  return request<{ status: string }>("/api/auth/logout", {
    method: "POST",
  });
}

export function getSettings(): Promise<SettingsPayload> {
  return request<SettingsPayload>("/api/settings");
}

export function updateSettings(payload: SettingsPayload): Promise<SettingsPayload & { updated_at: string }> {
  return request<SettingsPayload & { updated_at: string }>("/api/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getAuditLogs(limit = 80): Promise<AuditLogEntry[]> {
  return request<AuditLogEntry[]>(`/api/audit-logs?limit=${limit}`);
}

export function getTrendSnapshots(days = 30): Promise<TrendSnapshot[]> {
  return request<TrendSnapshot[]>(`/api/trends?days=${days}`);
}

export function getAlerts(limit = 20): Promise<AlertEvent[]> {
  return request<AlertEvent[]>(`/api/alerts?limit=${limit}`);
}

export function acknowledgeAlert(alertId: number): Promise<{ status: string }> {
  return request<{ status: string }>(`/api/alerts/${alertId}/acknowledge`, {
    method: "POST",
  });
}
