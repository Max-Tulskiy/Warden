import type {
  Agent,
  AuditEntry,
  EnrollmentToken,
  EventRecord,
  FleetEvent,
  InventoryChange,
  Policy,
  Task,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  options: { method?: string; token?: string | null; body?: unknown } = {},
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  const response = await fetch(`/api/v1${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body.detail)
      .catch(() => undefined);
    throw new ApiError(response.status, detail ?? `request to ${path} failed`);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function login(username: string, password: string): Promise<string> {
  const result = await request<{ access_token: string }>("/auth/login", {
    method: "POST",
    body: { username, password },
  });
  return result.access_token;
}

export function listAgents(token: string): Promise<Agent[]> {
  return request<Agent[]>("/agents", { token });
}

export function createEnrollmentToken(token: string): Promise<EnrollmentToken> {
  return request<EnrollmentToken>("/enrollment-tokens", {
    method: "POST",
    token,
  });
}

export function requestWindow(
  token: string,
  agentId: string,
  windowStart: string,
  windowEnd: string,
): Promise<Task> {
  return request<Task>(`/agents/${agentId}/requests`, {
    method: "POST",
    token,
    body: { window_start: windowStart, window_end: windowEnd },
  });
}

export interface PageParams {
  limit?: number;
  offset?: number;
}

export function getEvents(
  token: string,
  agentId: string,
  reportDate: string,
  page: PageParams = {},
): Promise<EventRecord[]> {
  const params = new URLSearchParams({ report_date: reportDate });
  if (page.limit !== undefined) params.set("limit", String(page.limit));
  if (page.offset !== undefined) params.set("offset", String(page.offset));
  return request<EventRecord[]>(`/agents/${agentId}/events?${params}`, { token });
}

export interface FleetFilters {
  start: string;
  end: string;
  agentIds?: string[];
  category?: EventRecord["category"];
}

export function getFleetEvents(
  token: string,
  filters: FleetFilters,
  page: PageParams = {},
): Promise<FleetEvent[]> {
  const params = new URLSearchParams({ start: filters.start, end: filters.end });
  for (const agentId of filters.agentIds ?? []) params.append("agent_id", agentId);
  if (filters.category) params.set("category", filters.category);
  if (page.limit !== undefined) params.set("limit", String(page.limit));
  if (page.offset !== undefined) params.set("offset", String(page.offset));
  return request<FleetEvent[]>(`/events?${params}`, { token });
}

export interface AuditFilters {
  start: string;
  end: string;
  /** An operator username, a station id, or a hostname; matched exactly. */
  actor?: string;
  /** One action code, or a dotted group such as `operator`. */
  action?: string;
}

export function listAudit(
  token: string,
  filters: AuditFilters,
  page: PageParams = {},
): Promise<AuditEntry[]> {
  const params = new URLSearchParams({ start: filters.start, end: filters.end });
  if (filters.actor) params.set("actor", filters.actor);
  if (filters.action) params.set("action", filters.action);
  if (page.limit !== undefined) params.set("limit", String(page.limit));
  if (page.offset !== undefined) params.set("offset", String(page.offset));
  return request<AuditEntry[]>(`/audit?${params}`, { token });
}

export function getPolicy(token: string): Promise<Policy> {
  return request<Policy>("/policy", { token });
}

export function changePassword(
  token: string,
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  return request<void>("/auth/password", {
    method: "POST",
    token,
    body: { current_password: currentPassword, new_password: newPassword },
  });
}

export function setAgentStatus(
  token: string,
  agentId: string,
  status: Agent["status"],
): Promise<Agent> {
  return request<Agent>(`/agents/${agentId}`, {
    method: "PATCH",
    token,
    body: { status },
  });
}

export function getInventoryChanges(
  token: string,
  agentId: string,
  page: PageParams = {},
): Promise<InventoryChange[]> {
  const params = new URLSearchParams();
  if (page.limit !== undefined) params.set("limit", String(page.limit));
  if (page.offset !== undefined) params.set("offset", String(page.offset));
  const query = params.toString();
  return request<InventoryChange[]>(
    `/agents/${agentId}/inventory/changes${query ? `?${query}` : ""}`,
    { token },
  );
}
