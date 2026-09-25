# Spec: Record who views collected data and the audit log

**Directory:** `specs/008-read-audit/` · **Status:** draft · **Date:** 2026-09-25

---

## 1. Problem

The audit log records what changes something or authenticates someone: who
disabled a station, who changed the policy, who signed in. It does not
record what anyone looks at. An operator with a legitimate sign-in can read
every event the stations have delivered, every inventory change, and the
audit log itself, and nothing shows that they did. The constitution already
names this as an accepted boundary (Section V: "reads ... are not
recorded, ... so a gap in the log is not proof that nothing was read").

## 2. Why

The complex exists to counter insider activity, and its own operators are
among the people who can misuse what it collects: an administrator or an
observer can read every station's processes, print jobs, media
connections, and visited sites. Constitution principle 8 ("every action ...
is logged") gives the reason a security-administrator workstation must be
accountable: "who requested what, and when." The panel's reports are the
"displaying data and keeping daily reports" function in the constitution's
Purpose table; making views of them accountable is the same accountability
extended to the data the complex collects. Reading the audit log is the
one read that reveals who did what, so it is in scope too.

## 3. User scenarios

### Primary scenario

1. An operator opens a station's daily report, the cross-station report, or
   a station's inventory-change history.
2. The audit log gains an entry: who looked, at what, and when — the
   station, the day or period, and the filters used.
3. Later an administrator opens the audit log, narrows it to views, and sees
   which operator looked at which station's data, and when.

### Additional scenarios

* An administrator reads the audit log; that read is recorded like any other
  view.
* An observer's views are recorded exactly like an administrator's — an
  observer can read all collected data (constitution D-10).
* An operator pages through a long report with "show more"; each page is its
  own entry, carrying which page it was.

### Edge cases

* The station list, the server policy, the list of operators, and the
  session check are not recorded. They are metadata or helper calls the
  panel makes on several screens; an entry for each would bury the entries
  that matter.
* A request that is rejected — no session, a role that is not allowed,
  parameters that fail validation — produces no view entry, because nothing
  was disclosed.
* A view that matches nothing (a day with no events, a station with no
  changes) is still a view and is recorded.
* The audit log's own view entries appear in the log, including the entry
  for the view that is being displayed.
* The same view requested twice is two entries; there is no collapsing of
  repeats.
* A view is never answered without its entry: if the entry cannot be
  stored, the request fails and returns no data.

## 4. Requirements

| # | Requirement | Priority |
|---|---|---|
| R-1 | Every accepted request to view a station's daily report, the cross-station report, a station's inventory-change history, or the audit log must be recorded in the audit log, naming the operator and the moment | required |
| R-2 | An entry must say what was viewed: which kind of view, which station or period, and which filters were applied | required |
| R-3 | An entry for a page of results after the first must say which page it is | nice to have |
| R-4 | Views must be recorded for every role — administrator and observer alike | required |
| R-5 | A view must not be answered if its entry cannot be stored | required |
| R-6 | A rejected request (no valid session, a role that is not allowed, invalid parameters) must not produce a view entry | required |
| R-7 | View entries must be distinguishable from the entries that record changes and sign-ins, so an administrator can list only views, or everything but views | required |
| R-8 | The panel must show view entries under Russian names, offer views as their own choice in the audit log's action filter, and stop saying that reads are not recorded | required |
| R-9 | The documentation and the constitution must state exactly what is and is not recorded (principle 10) | required |

## 5. Out of scope

* does not record the station list, the server policy, the list of
  operators, or the session check — see the edge cases;
* does not record the agent-facing task poll — it is the agent's own
  protocol, not an operator viewing anything, and it already has its own
  narrower signal;
* does not record rejected or failed requests as attempts — a refused
  request is a different kind of event from a view, and is not part of this
  spec;
* does not make the audit log tamper-evident — the boundary that a person
  with write access to the database can alter it is unchanged;
* does not add retention, pruning, or rate limiting to the audit log — it
  grows by one row per accepted view, and none of those exist today for
  changes either;
* does not add a screen — views appear in the existing audit log screen;
* does not cover ending sessions on a password change, which an earlier
  draft of this spec also included: `specs/004-session-revocation/`
  delivered it, and it is not part of this one.

## 6. Acceptance criteria

| # | Test scenario | Expected result |
|---|---|---|
| A-1 | Request a station's daily report | One entry naming the operator, the station, and the day |
| A-2 | Request the cross-station report with stations, a category, and a period | One entry naming the period and the filters |
| A-3 | Request a station's inventory-change history | One entry naming the station |
| A-4 | Request the audit log for a period with a filter | One entry naming the period and the filter; it is visible on the next read |
| A-5 | An observer requests a daily report | The entry names the observer |
| A-6 | Request any of the four without a session, request the audit log as an observer, or send invalid parameters | The request is refused as it is today; no entry is added |
| A-7 | Request the station list, the policy, and the list of operators | No entry is added |
| A-8 | Request the same view twice, then the second page of it | Three entries; the third carries its page |
| A-9 | Request a view that matches nothing | The response is empty and one entry is added |
| A-10 | Make the entry impossible to store, then request a view | The request fails and no data is returned |
| A-11 | Filter the audit log by the views group, and by the operator group | The first returns only views; the second returns none of them |
| A-12 | Open the audit log screen | View entries show Russian names, views are a choice in the action filter, and the hint under the filters no longer says reads are not recorded |

## 7. Impact on existing behavior

No endpoint changes its response shape or its access rules. The description
text of the four views changes, so the API contract is regenerated. The
audit log grows by one row per accepted view; existing entries are
untouched. The audit log screen's action filter gains a choice and its hint
text changes. The constitution's boundary on unrecorded reads is rewritten
to say which reads are and are not recorded, and the documents that repeat
it are brought in line.

## 8. Open questions

*None — this section is empty and the spec is ready for planning.*
