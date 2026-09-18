# Spec: Agent-server complex for countering insider activity

**Directory:** `specs/001-agent-server-complex/` · **Branch:** `001-agent-server-complex`
**Status:** draft · **Date:** 2026-09-15

---

## 1. Problem

An information-security administrator has no centralized way to know what is
happening on the workstations inside a protected perimeter: what hardware and
software they run, whether that has changed over time, who has connected
external media, what has been sent to print, which processes have been
launched, and which websites have been opened. Without such a complex, every
one of these facts has to be established by hand and after the fact, once an
incident has already happened.

## 2. Why

The original lab assignment (quoted in full, translated):

> Develop a client-server application with the following functions: the
> client tracks information about the workstation's hardware and installed
> software; about connected removable media; about documents sent to print;
> about running processes; about websites being opened. On request from the
> server, the client must provide information for the time window specified
> in the request (no more than 4 hours). The server correctly displays the
> information received from the client and keeps daily reports. Information
> about hardware and software is stored separately, in order to detect
> possible configuration changes.

This is the project's normative source; the full text is also captured in the
constitution's "Purpose" table (`.specify/memory/constitution.md`).

## 3. User scenarios

### Primary scenario

1. The administrator signs in and issues a one-time enrollment token, then
   hands it to the agent during workstation setup.
2. The agent enrolls with the server and, from that point on, continuously
   observes the station, appending events to a local buffer.
3. The administrator sees the station in the web panel's list of enrolled
   agents, with a last-seen timestamp.
4. The administrator requests data for the station over a time window of
   interest (no more than 4 hours).
5. The agent picks up the request on its next contact with the server,
   selects buffered events for the given window, and sends them to the
   server.
6. The administrator sees the delivered data in the web panel, grouped by
   category (hardware and software, media, printing, processes, websites).

### Additional scenarios

* The agent periodically, without an explicit request, sends the server a
  hardware/installed-software snapshot and a liveness heartbeat.
* The server compares a new snapshot against the previous one and, if the
  configuration has changed, records that as a separate change event — kept
  apart from the snapshot history itself.
* The server stores and displays a report for the current day for each
  station.
* The administrator signs in to the web panel with their own account.

### Edge cases

| Situation | Expected behavior |
|---|---|
| The agent is temporarily offline when a request is placed | The request stays queued and runs the next time the agent contacts the server |
| The requested window exceeds 4 hours | The server rejects placing the request with a clear error; an agent that somehow receives such a task also refuses it |
| No data exists for the requested window (the station was powered off) | The agent replies with an empty result for that category, not an error |
| An enrollment token is reused | The server rejects a second enrollment against an already-used token |
| The connection drops mid-upload of window data | The agent retries the upload on its next contact; the server keeps no partially-saved response to that task |
| Two requests for one station have overlapping windows | Each is handled independently; the agent is not required to merge them |

## 4. Requirements

| # | Requirement | Priority |
|---|---|---|
| R-1 | The agent must continuously observe the station's hardware and installed software | required |
| R-2 | The agent must continuously observe removable-media connections | required |
| R-3 | The agent must continuously observe documents sent to print | required |
| R-4 | The agent must continuously observe launched processes | required |
| R-5 | The agent must continuously observe opened websites | required |
| R-6 | On request from the server, the agent must provide data for the specified time window | required |
| R-7 | A request window must not exceed 4 hours; the system must check this and reject a larger one | required |
| R-8 | The server must correctly display the data received from the agent | required |
| R-9 | The server must keep daily reports | required |
| R-10 | Hardware and software records must be stored separately from other events, to detect configuration changes | required |
| R-11 | The system must distinguish "the new snapshot matches the previous one" from "the configuration changed" | required |
| R-12 | A new agent must enroll using a one-time token issued by the administrator | required |
| R-13 | Access to the web panel must require an administrator login | required |
| R-14 | A signed-in administrator must be able to issue an agent enrollment token without leaving the panel | required |

## 5. Out of scope

* does not intercept the station's network traffic — website data relies on
  installed browsers' history (boundary stated in constitution Section V);
* does not recover the content of printed documents, only their metadata (job
  name, printer, time, initiating process);
* does not let the server reach the agent directly — only the agent initiates
  contact (active-agent model, constitution D-1);
* does not guarantee an instant response to a request — the reply arrives on
  the agent's next contact with the server, not immediately;
* does not replace antivirus protection and does not block anything on the
  station — the complex only observes and reports.

## 6. Acceptance criteria

| # | Test scenario | Expected result |
|---|---|---|
| A-1 | Enroll an agent with a one-time token | The agent appears in the server's station list; a second enrollment with the same token is rejected |
| A-2 | Place a request for a 4-hour window | The server accepts the request |
| A-3 | Place a request for a 4-hour-1-minute window | The server rejects it with a clear error |
| A-4 | Wait for the agent's next contact after A-2 | The server receives data for all five categories covering the requested window |
| A-5 | Connect/disconnect external media on the agent's station | The event appears in the data returned by the next window request covering that moment |
| A-6 | Change the set of installed software on the station | The next inventory snapshot produces a separate configuration-change record, visible in the panel |
| A-7 | Send an identical inventory snapshot twice in a row | The second submission produces no change record |
| A-8 | Open today's report for a station in the panel | It shows the events the server received during the current day |
| A-9 | Try to open the panel without an account | Access is denied |
| A-10 | Issue an enrollment token while signed in | The panel displays the plaintext token once, with its expiration time |

## 7. Impact on existing behavior

The project starts from nothing — there is no existing behavior to impact.
This is the baseline spec defining the system's core; later features (e.g.
richer daily-report breakdowns, extended panel filters) are written as
separate specs that build on this one.

## 8. Open questions

None.
