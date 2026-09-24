import { describe, expect, it } from "vitest";

import type { Agent } from "../../src/api/types";
import {
  ACTION_GROUPS,
  ACTIONS,
  actionLabel,
  formatDetail,
  resolveParty,
} from "../../src/lib/audit";

// Every action code the server writes today, found by searching the server
// sources for `log_event` calls. A code missing a Russian name would surface
// in the panel as a raw identifier.
const EMITTED_ACTIONS = [
  "agent.enroll",
  "agent.enroll_rejected",
  "agent.inventory_change",
  "agent.inventory_snapshot",
  "agent.report",
  "agent.report_out_of_window",
  "agent.tasks_dispatched",
  "agent.disabled",
  "agent.enabled",
  "enrollment_token.create",
  "operator.login",
  "operator.login_failed",
  "operator.login_throttled",
  "operator.password_change",
  "operator.password_change_failed",
  "operator.password_change_throttled",
  "operator.sessions_revoked",
  "request.window",
];

describe("actionLabel", () => {
  it.each(EMITTED_ACTIONS)("has a Russian name for %s", (code) => {
    const label = actionLabel(code);

    expect(label).not.toBe(code);
    expect(label).toMatch(/[А-Яа-яЁё]/);
  });

  it("gives every known action a name distinct from the others", () => {
    const labels = EMITTED_ACTIONS.map(actionLabel);

    expect(new Set(labels).size).toBe(EMITTED_ACTIONS.length);
  });

  it("returns an unknown code unchanged so the entry is never hidden", () => {
    expect(actionLabel("policy.changed_by_a_later_version")).toBe(
      "policy.changed_by_a_later_version",
    );
  });
});

describe("filter choices", () => {
  it("offers the four groups the server's codes fall into", () => {
    expect(ACTION_GROUPS.map((group) => group.value)).toEqual([
      "operator",
      "agent",
      "enrollment_token",
      "request",
    ]);
    for (const group of ACTION_GROUPS) {
      expect(group.label).toMatch(/[А-Яа-яЁё]/);
    }
  });

  it("offers every known action as a single choice, with its name", () => {
    expect(ACTIONS.map((action) => action.value).sort()).toEqual(
      [...EMITTED_ACTIONS].sort(),
    );
    for (const action of ACTIONS) {
      expect(action.label).toBe(actionLabel(action.value));
    }
  });

  it("puts every known action under one of the offered groups", () => {
    const groups = ACTION_GROUPS.map((group) => group.value);

    for (const code of EMITTED_ACTIONS) {
      expect(groups).toContain(code.split(".")[0]);
    }
  });
});

describe("formatDetail", () => {
  it("shows a dash when there is nothing to show", () => {
    expect(formatDetail({})).toBe("—");
  });

  it("writes one key: value line per entry", () => {
    expect(formatDetail({ hostname: "WS-01", os: "linux" })).toBe(
      "hostname: WS-01\nos: linux",
    );
  });

  it("writes a list or an object as compact JSON", () => {
    expect(formatDetail({ task_ids: ["a", "b"] })).toBe('task_ids: ["a","b"]');
    expect(formatDetail({ counts: { added: 1 } })).toBe('counts: {"added":1}');
  });

  it("writes numbers, booleans and null as they are", () => {
    expect(formatDetail({ event_count: 3, ok: false, note: null })).toBe(
      "event_count: 3\nok: false\nnote: null",
    );
  });
});

describe("resolveParty", () => {
  const stations: Agent[] = [
    {
      id: "6f1c2a94-1111-4222-8333-444455556666",
      hostname: "WS-01",
      os: "linux",
      status: "active",
      enrolled_at: "2026-09-01T12:00:00Z",
      last_seen_at: null,
    },
  ];

  it("shows a known station id as its hostname", () => {
    expect(resolveParty("6f1c2a94-1111-4222-8333-444455556666", stations)).toBe("WS-01");
  });

  it("leaves an operator name, a hostname or an unknown id as it is", () => {
    expect(resolveParty("admin", stations)).toBe("admin");
    expect(resolveParty("WS-02", stations)).toBe("WS-02");
    expect(resolveParty("00000000-0000-4000-8000-000000000000", stations)).toBe(
      "00000000-0000-4000-8000-000000000000",
    );
  });

  it("leaves everything as it is while the station list is missing", () => {
    expect(resolveParty("6f1c2a94-1111-4222-8333-444455556666", null)).toBe(
      "6f1c2a94-1111-4222-8333-444455556666",
    );
    expect(resolveParty("admin", [])).toBe("admin");
  });
});
