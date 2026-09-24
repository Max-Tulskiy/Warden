# Spec: Audit log viewer

**Directory:** `specs/003-audit-log-viewer/` · **Branch:** `003-audit-log-viewer` · **Status:** done · **Date:** 2026-09-24

---

## 1. Problem

The server records every notable action in its audit log — agent
enrollment, task pickup, window delivery, inventory changes, operator
logins and failed logins, password changes, station status changes — but
nothing reads it back. An administrator who wants to know who requested a
station's data, when a station was disabled, or whether someone has been
guessing the panel password has to open a database shell. The log exists
for accountability, yet in practice only someone with direct database
access can see it.

## 2. Why

Constitution principle 8 ("every action is logged") gives the reason for
the log: "a security-administrator workstation must itself be accountable —
who requested what, and when." Accountability that nobody can see from
the product is incomplete. Spec 002 listed a viewer for this log as a
separate, not-yet-written spec (its section 5). The features planned after
it (session revocation, operator management, an editable policy) each add
new audited actions, and a viewer lets an administrator verify those
actions from the panel.

## 3. User scenarios

### Primary scenario

1. The administrator opens "Журнал" in the panel sidebar.
2. The panel shows the audit entries for the last 24 hours, newest first.
   Each row shows when the action happened, a readable name for the action,
   who performed it, what it was performed on, and its additional details.
   The actor is an operator's username, an enrolled station's identifier, or,
   for a station that is still registering, the hostname it announced.
3. The administrator picks a different time range, either a preset (last
   hour / last 24 hours / last 7 days) or a custom start and end, and
   optionally narrows the list to one actor or one kind of action.
4. The panel shows the matching entries; if more exist than fit on one
   page, the administrator loads the next page.

### Additional scenarios

* An administrator narrows the list to failed and throttled logins to check
  whether someone is guessing the panel password.
* An administrator narrows the list to one operator's username to review
  everything that account did.

### Edge cases

| Situation | Expected behavior |
|---|---|
| The chosen end of the range is not after its start | The request is rejected with a clear error |
| No entries match the chosen filters | The panel shows an empty result, not an error |
| More entries match than fit on one page | The panel offers to load the next page |
| An entry carries an action the panel has no readable name for (e.g. one added by a later server version) | The panel shows the raw action code instead of hiding the entry |
| The request carries no valid operator session | The server rejects it the same way as every other panel endpoint |

## 4. Requirements

| # | Requirement | Priority |
|---|---|---|
| R-1 | The administrator must be able to view audit log entries for an arbitrary time range from the panel | required |
| R-2 | The view must offer at least three preset ranges (last hour, last 24 hours, last 7 days) in addition to a custom range | required |
| R-3 | Each entry must show its time, action, actor, target, and additional details | required |
| R-4 | Entries must be listed newest first | required |
| R-5 | The administrator must be able to narrow the list to a single actor | required |
| R-6 | The administrator must be able to narrow the list to one kind of action or a group of related actions (e.g. all operator actions) | required |
| R-7 | Every known action must be shown under a readable Russian name; an unknown action must still be shown | required |
| R-8 | Large result sets must be paged, not returned whole | required |
| R-9 | Only a signed-in operator may read the audit log | required |

## 5. Out of scope

* The audit log stays read-only: this feature does not let anyone edit,
  delete, or prune entries from the panel.
* Viewing the audit log is not itself recorded in the audit log. No other
  read in the panel is audited either (reports, station lists, policy). The
  log records actions that change something or authenticate someone.
* No export (CSV, PDF, etc.) of the log.
* No live updating: the list is loaded when requested, not pushed as new
  entries arrive.
* No restriction of the log to particular operators. Today every operator
  is a full administrator. Limiting the log to an administrator role
  belongs to the operator-management spec that introduces roles.
* No retention or rotation policy for the log. It grows as it does today.
* The agent's local log on the workstation (principle 8, "locally on the
  agent") is not shown; only the server's central log is.

## 6. Acceptance criteria

| # | Test scenario | Expected result |
|---|---|---|
| A-1 | Log in, then request the log for the last hour with no other filter | The login entry just created appears, newest first, with its time, action, actor, and target |
| A-2 | Request the log for a custom range whose end is before its start | The request is rejected with a clear error |
| A-3 | Record actions by two different actors, then filter by one of them | Only that actor's entries appear |
| A-4 | Record a successful and a failed login and a station status change, then filter to the operator-action group | Both login entries appear, the station status change does not |
| A-5 | Record more entries than one page holds | The first page is full, the next page continues without gaps or repeats |
| A-6 | Request the log without an operator session | The request is rejected as unauthorized |
| A-7 | Display an entry whose action has no known readable name | The raw action code is shown |

## 7. Impact on existing behavior

No existing endpoint, table column, or screen changes. The panel gains one
sidebar item and one screen. Nothing changes for already-enrolled agents.
Range reads of the log must stay fast as it grows (an implementation
concern for the plan, not a visible change).

## 8. Open questions

None.
