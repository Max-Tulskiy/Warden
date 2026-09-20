# Spec: Panel reports and settings

**Directory:** `specs/002-panel-reports-and-settings/` · **Branch:** `002-panel-reports-and-settings` · **Status:** done · **Date:** 2026-09-18

---

## 1. Problem

The web panel's sidebar has three items: stations, reports, and settings.
Only the station list is a real screen; reports and settings are inert
placeholders with no click handler at all. Underneath that gap sit three
things the product cannot actually do yet: an administrator cannot see
activity across more than one station or over anything but a single
calendar day, cannot revoke a compromised station's access, and cannot
change their own password even though the deployment's own setup
instructions tell them to.

## 2. Why

The lab assignment requires "the server correctly displays the information
received from the client and keeps daily reports" (constitution's Purpose
table, row on daily reports) — a per-station, per-day view satisfies the
letter of that but not an administrator's actual question, which is usually
"what happened across the fleet in the last hour/day/week." Constitution
principle 8 ("every action ... is logged") already assumes an administrator
who can act on a station (e.g. revoke it) and be held accountable for that
action via the audit log this spec's endpoints write to. Constitution
principle 5 ("agent-server exchange is authenticated") is only as strong as
the operator's own password; a seeded default that can never be changed is
a standing weakness the deployment docs already warn about without the
product being able to fix it.

## 3. User scenarios

### Primary scenario

1. The administrator opens "Reports" and picks a time range — either a
   preset (last hour / today / last week) or a custom start and end — and,
   optionally, one or more specific stations and an event category.
2. The panel shows the matching events across all selected stations in one
   table, each row naming which station it came from.
3. The administrator opens "Settings", sees the server's current operating
   policy values (window cap, token lifetime, upload limits) for reference,
   and changes their own password.
4. The administrator disables a compromised or decommissioned station from
   the same screen; its agent key stops working on the station's next
   contact attempt.

### Additional scenarios

* An administrator re-enables a station they disabled by mistake.
* An administrator narrows a report to a single station by selecting only
  that one from the station list.

### Edge cases

| Situation | Expected behavior |
|---|---|
| The chosen end of the range is not after its start | The panel/server rejects placing the report request with a clear error |
| No events match the chosen range/station/category combination | The panel shows an empty result, not an error |
| More rows match than fit on one page | The panel offers to load the next page, mirroring the existing per-station report screen |
| The administrator enters a new password that fails the minimum-length policy | The change is rejected with a clear error before anything is stored |
| The administrator changes their password | Already-issued session tokens for that account keep working until they expire on their own; there is no immediate revocation of prior sessions |
| A disabled station's agent tries to poll for tasks or submit a report | The server rejects it the same way it already rejects an unknown or wrong key |

## 4. Requirements

| # | Requirement | Priority |
|---|---|---|
| R-1 | The administrator must be able to request a report of events across one, several, or all stations for an arbitrary time range | required |
| R-2 | The report screen must offer at least three preset ranges (last hour, last day, last week) in addition to a custom range | required |
| R-3 | Each row of a cross-station report must show which station it came from | required |
| R-4 | The administrator must be able to filter a report by event category | nice to have |
| R-5 | The administrator must be able to change their own password from the panel | required |
| R-6 | A new password must meet a minimum-length policy | required |
| R-7 | The administrator must be able to view the server's current operating policy values (request window cap, enrollment token lifetime, upload limits) without leaving the panel | required |
| R-8 | The administrator must be able to disable a station, immediately preventing its agent from authenticating further | required |
| R-9 | The administrator must be able to re-enable a previously disabled station | required |
| R-10 | Every password change and every station status change must be recorded in the audit log | required |

## 5. Out of scope

* does not add a way to read the audit log from the panel — the log is
  written for this and prior features, but a viewer for it is a separate,
  not-yet-written spec;
* does not let an administrator manage other administrator accounts
  (create, remove, or reset another operator's password) — there is one
  seeded account per deployment today, and multi-operator management is a
  separate concern;
* does not invalidate already-issued session tokens when a password
  changes — sessions are stateless JWTs with no revocation list, and adding
  one is a separate piece of work with its own tradeoffs;
* does not let the operating policy values (window cap, token lifetime,
  upload limits) be changed from the panel — they stay server-configured,
  this feature only makes them visible;
* a report's time range is a read against events the server has already
  stored, not a new request sent to any agent, so it is not subject to and
  does not touch the ≤4h agent-request-window cap (constitution principle
  3, which governs `POST /api/v1/agents/{id}/requests`, a different
  operation) — a week-long report range is therefore in scope and not a
  boundary violation.

## 6. Acceptance criteria

| # | Test scenario | Expected result |
|---|---|---|
| A-1 | Request a report for "last hour" with no station filter | The panel shows matching events from every station, each row labeled with its station |
| A-2 | Request a report for a custom range where the end is before the start | The request is rejected with a clear error |
| A-3 | Request a report filtered to two specific stations | Only those stations' events appear |
| A-4 | Change the password with the wrong current password | The change is rejected, the password is unchanged |
| A-5 | Change the password to one shorter than the minimum length | The change is rejected |
| A-6 | Change the password successfully, then log in with the new one | Login succeeds; the old password no longer works |
| A-7 | Open "Settings" while signed in | The current operating policy values are visible, read-only |
| A-8 | Disable a station, then have its agent attempt to poll for tasks | The server rejects the attempt the same way it rejects an invalid key |
| A-9 | Re-enable a disabled station | Its agent can authenticate again on its next contact |
| A-10 | Change a password or a station's status | A corresponding row appears in the audit log |

## 7. Impact on existing behavior

Existing agents, tasks, and the per-station daily report
(`GET /agents/{id}/events?report_date=`) are unchanged; this feature adds
endpoints and screens alongside them. An administrator's existing session
and the seeded default password keep working exactly as before until the
administrator chooses to change it.

## 8. Open questions

None.
