import type { Agent, EnrollmentToken, EventRecord, InventoryChange, Task } from "./types";

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
