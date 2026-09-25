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

/** The certificate authority behind the server's own certificate. */
export interface TlsAuthority {
  pem: string;
  sha256: string;
}

export interface EventRecord {
  id: string;
  category: "removable_media" | "printing" | "processes" | "web";
  occurred_at: string;
  payload: Record<string, unknown>;
}

export interface FleetEvent extends EventRecord {
  agent_id: string;
  hostname: string;
}

export type Role = "admin" | "viewer";

export interface Me {
  username: string;
  role: Role;
}

export interface Operator {
  id: string;
  username: string;
  role: Role;
  status: "active" | "disabled";
}

/** The three limits an administrator can change. */
export interface EditablePolicy {
  max_request_window_hours: number;
  enrollment_token_ttl_hours: number;
  session_lifetime_minutes: number;
}

export interface Bounds {
  min: number;
  max: number;
}

/** The limits in force, plus what an administrator may do with the editable ones. */
export interface Policy extends EditablePolicy {
  min_password_length: number;
  max_report_events: number;
  max_inventory_entries: number;
  max_page_size: number;
  /** True when an administrator saved a policy; false when the server's configuration decides. */
  overridden: boolean;
  /** What the server's configuration gives the editable values, which a reset returns to. */
  defaults: EditablePolicy;
  bounds: Record<keyof EditablePolicy, Bounds>;
}

export interface AuditEntry {
  id: string;
  actor: string;
  /** Kept a plain string: a row from another server version may carry an unknown code. */
  action: string;
  target: string;
  occurred_at: string;
  detail: Record<string, unknown>;
}

export interface InventoryChange {
  id: string;
  detected_at: string;
  added: { hardware: Record<string, unknown>; software: Record<string, unknown> };
  removed: { hardware: Record<string, unknown>; software: Record<string, unknown> };
  modified: { hardware: Record<string, unknown>; software: Record<string, unknown> };
}
