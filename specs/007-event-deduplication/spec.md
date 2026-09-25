# Spec: Deduplicate events delivered through overlapping window requests

**Directory:** `specs/007-event-deduplication/` · **Branch:** `007-event-deduplication`
**Status:** done · **Date:** 2026-09-22

---

## 1. Problem

A station's events reach the server only as answers to `window_request`
tasks (constitution principle 2). Nothing stops two tasks from covering
overlapping time ranges — an administrator may request the last hour and,
minutes later, the last four hours for the same station; a slow response
may be retried; two administrators may act on the same station around the
same time. Each task is answered independently from the agent's buffer, so
an occurrence that falls inside more than one requested window is delivered,
and stored, once per task. The daily report and the cross-station report
(`specs/002-panel-reports-and-settings/`) then show that one real print job,
media connection, process launch, or page visit as two or more separate
rows. This gap is already named as an accepted boundary in the constitution
(Section V, version 1.0.2): "overlapping requests can store the same event
twice, since events are not deduplicated on ingestion."

## 2. Why

From the constitution's "Purpose" table: "Displaying data and keeping daily
reports | `server` + web panel." A report that can silently count the same
occurrence more than once is not correctly displaying what happened — an
administrator counting how many times a USB drive was connected, or how
many pages went to a given printer, on a given day gets an answer that
depends on how the operators happened to request windows, not on what
actually happened on the station. Fixing this also lets the constitution
drop the duplicate-events boundary it currently has to warn about.

## 3. User scenarios

### Primary scenario

1. An administrator requests the last hour of data for a station, then,
   shortly after, separately requests the last four hours for the same
   station (e.g. to be safe, or after being asked to check something they
   suspect happened slightly earlier).
2. The agent answers both tasks from its local buffer; one particular
   occurrence (say, a print job) falls inside both windows and is sent back
   in both answers.
3. The administrator opens the daily report or the cross-station report for
   that station and sees the print job once, with the rest of the window's
   events unaffected.

### Additional scenarios

* The administrator (or the panel, on a retry after a slow response) places
  the exact same window request twice; the report still shows each real
  occurrence once.
* Two administrators, working independently, request overlapping windows for
  the same station around the same time.

### Edge cases

* Windows that overlap only partially (e.g. 10:00–11:00 and 10:30–11:30):
  only the occurrences in the overlapping half must be deduplicated: the
  30–60 range are answered by both tasks and must count once; 10:00–10:30 is
  answered by the first task only.
* Two windows that do not overlap at all: no deduplication should occur, and
  no legitimate event should ever be dropped because it merely resembles
  another one — two occurrences are the same only when they are the same
  underlying observation (same station, same category, at the exact instant
  it was recorded, with the exact same recorded detail), never merely
  "close" or "similar."
* A station is disabled and its buffered-but-undelivered events are never
  requested again — unaffected by this feature; deduplication only concerns
  occurrences that a station actually delivers.

## 4. Requirements

| # | Requirement | Priority |
|---|---|---|
| R-1 | The same real-world occurrence, when delivered as the answer to more than one window request, must be stored and counted once, regardless of how many tasks delivered it | required |
| R-2 | Two distinct occurrences must never be merged into one, even when a window request repeats or overlaps another | required |
| R-3 | The daily report and the cross-station report must reflect the deduplicated count, not the number of deliveries | required |
| R-4 | Deduplication must not depend on the order in which overlapping tasks are answered | required |
| R-5 | Placing or answering an overlapping window request must not fail or be rejected because of the overlap — deduplication is silent to the administrator and to the agent | required |

## 5. Out of scope

* Deduplicating across different stations — an occurrence is already scoped
  to one station (`agent_id`); this spec does not touch cross-station
  matching.
* Deduplicating hardware/software inventory snapshots or change records —
  already governed by their own versioning rule (constitution principle 6),
  unrelated to category events.
* Cleaning up duplicate rows already stored before this feature ships. The
  project has no production data at stake; deduplication takes effect for
  events stored from this feature onward, and existing rows are left as is.
* Changing the 4-hour window cap, the window-request flow, or who may place
  a request.
* Preventing an agent from re-collecting or re-buffering the same real
  occurrence on its own (e.g. two genuinely separate USB connections of the
  same device) — those remain two distinct occurrences to report.

## 6. Acceptance criteria

| # | Test scenario | Expected result |
|---|---|---|
| A-1 | Two overlapping window requests are placed and answered for a station; one buffered occurrence falls inside both windows | The daily report and the cross-station report show that occurrence once |
| A-2 | The same window request is answered, then somehow answered again for the same task or an identical new one | No duplicate row is added the second time |
| A-3 | Two overlapping window requests are placed; each window also contains an occurrence the other does not | Both distinct occurrences are present in the report, exactly once each |
| A-4 | Two non-overlapping window requests are placed for a station | Nothing is deduplicated; every delivered occurrence is stored |
| A-5 | Two different stations each report an occurrence with the same category, timestamp, and detail (coincidentally identical) | Both are stored — deduplication never merges occurrences across stations |

## 7. Impact on existing behavior

No change to the request/window flow itself, and no agent-visible change —
the agent still answers every task it is given from its buffer exactly as
today; discarding an already-known occurrence happens only where events are
ingested and reported. Reports for stations that were never subject to
overlapping requests are unaffected. Once implemented, the constitution's
Section V note about duplicate events becomes stale and must be removed or
rewritten as part of this feature's amendment step.

## 8. Open questions

*None — this section is empty and the spec is ready for planning.*
