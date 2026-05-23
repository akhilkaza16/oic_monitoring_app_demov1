import {
  ExecutiveSummary,
  FilterOptions,
  IntegrationDetailResponse,
  IntegrationListResponse,
  LatencyLog,
  SettingsPayload,
} from "./types";

const API_BASE = process.env.REACT_APP_BACKEND_URL;

if (!API_BASE) {
  throw new Error("REACT_APP_BACKEND_URL is required in frontend/.env");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
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

export function runMockCollectorCycle(): Promise<{ updated_integrations: number }> {
  return request<{ updated_integrations: number }>("/api/mock-collector/run", {
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
