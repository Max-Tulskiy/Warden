// Types mirror contracts/openapi.yaml -- keep them in sync by hand for now;
// a generated client is future work (see specs/ for how to propose it).

export interface Agent {
  id: string;
  hostname: string;
  os: string;
  status: "active" | "disabled";
  enrolled_at: string;
  last_seen_at: string | null;
}

export interface Task {
  id: string;
  kind: string;
  window_start: string;
  window_end: string;
  status: "pending" | "dispatched" | "completed" | "failed";
}

export interface EnrollmentToken {
  token: string;
  expires_at: string;
}

export interface EventRecord {
  id: string;
  category: "removable_media" | "printing" | "processes" | "web";
  occurred_at: string;
  payload: Record<string, unknown>;
}

export interface InventoryChange {
  id: string;
  detected_at: string;
  added: { hardware: Record<string, unknown>; software: Record<string, unknown> };
  removed: { hardware: Record<string, unknown>; software: Record<string, unknown> };
  modified: { hardware: Record<string, unknown>; software: Record<string, unknown> };
}
