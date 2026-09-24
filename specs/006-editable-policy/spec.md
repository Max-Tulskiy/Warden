# Spec: Editable operating policy

**Directory:** `specs/006-editable-policy/` · **Branch:** `006-editable-policy` · **Status:** done · **Date:** 2026-09-24

---

## 1. Problem

The panel shows the server's operating limits — how long a request window may be,
how long an enrollment token lives, how long a session lasts — but they can only
be changed by editing the server's configuration and restarting it. An
administrator who finds a session too long, or wants stations asked for less data
at a time, has to have access to the machine the server runs on. Nothing records
who changed a limit or when, and nothing on the screen says what the server was
configured to use.

## 2. Why

Constitution principle 3 caps a request window at four hours because that is how
much history one request may pull out of a workstation; an administrator is
entitled to tighten that, never to loosen it. Principle 5 makes sessions and
enrollment tokens the way access is granted, and how long they last is the
administrator's call. Principle 8 wants every change of behavior recorded. Spec
002 showed these values read-only and named editing them a separate piece of work;
the accounts that can now be told apart (spec 005) make it safe to give that
ability to administrators only.

## 3. User scenarios

### Primary scenario

1. An administrator opens "Настройки" and finds the server policy with three
   values they can change: the longest window a request may cover, how long an
   enrollment token stays valid, and how long a session lasts. Beside each is the
   range it may take and the value the server's configuration gives it.
2. They shorten the request window from four hours to two, and the session from
   eight hours to four, and save.
3. The panel confirms, and says plainly what happens next: the new window limit
   applies to the next request, the new session length to the next sign-in, and
   sessions and tokens already issued keep the length they were issued with.
4. Asked for a three-hour window afterwards, the server refuses. The window form
   in the panel already says the limit is two hours.

### Additional scenarios

* An administrator returns the values to whatever the server's configuration says
  with one action, after confirming it.
* An observer opens "Настройки" and sees the same values, without anything to
  change.
* An administrator looks in the audit log to see who changed the policy, when, and
  from what to what.

### Edge cases

| Situation | Expected behavior |
|---|---|
| A value is below its lowest or above its highest allowed value, is not a whole number, or is missing | Refused with a message naming the range; nothing is stored |
| The request window is set above four hours | Refused, whatever the server's configuration says; four hours is a ceiling, not a setting |
| Nothing was changed by the save | Succeeds and records nothing |
| The administrator has never saved a policy | The server's configured values apply, and changing the configuration changes what is in force |
| An administrator saved values, and the server's configuration is edited afterwards | The saved values stay in force until the administrator returns to the server's values |
| The session length is shortened | Sessions already issued keep their expiry; only new sign-ins get the new length |
| An enrollment token was issued before the lifetime was changed | It expires when it was going to |
| A window request was placed before the limit was lowered | It stays queued and is answered as requested |
| An observer sends a change directly to the server | Refused as forbidden |
| Two administrators save at nearly the same moment | The later save is what stays; both are recorded |
| The station list, the window form, or the policy cannot be loaded | The rest of the screen keeps working; the window form falls back to the four-hour ceiling and the server still enforces the real limit |

## 4. Requirements

| # | Requirement | Priority |
|---|---|---|
| R-1 | An administrator must be able to change, from the panel, the longest request window, the lifetime of an enrollment token, and the lifetime of a session | required |
| R-2 | The longest request window must never exceed four hours, whatever is saved or configured; the panel can only lower it | required |
| R-3 | A change must apply from the next time the value is used, and must not alter sessions, tokens, or requests that already exist | required |
| R-4 | The panel must show, beside each editable value, the range it may take and the value the server's configuration gives it | required |
| R-5 | An administrator must be able to return all three values to the server's configured values with one confirmed action | required |
| R-6 | Until an administrator saves values, the server's configured values must apply | required |
| R-7 | An observer must be able to see the values but not change them, and the server must refuse a change from them | required |
| R-8 | Every change and every return to the configured values must be recorded in the audit log with the old and new values, and nothing must be recorded when nothing changed | required |
| R-9 | A value outside its range or not a whole number must be refused with a message naming the range, storing nothing | required |
| R-10 | The form that requests a station's data must use the limit currently in force, show it, and check against it | required |
| R-11 | The panel must say, when a policy is saved, what applies when | required |
| R-12 | The limits that are not among the three — upload limits, page size, minimum password length — must stay read-only | required |

## 5. Out of scope

* editing the upload limits, the page size, or the minimum password length;
* any setting per operator or per station;
* a history screen for policy changes, or an "undo" beyond returning to the
  server's configured values — the audit log is the only history;
* changes that start or expire at a chosen time;
* ending sessions that are already issued when the session length is shortened;
* the agent's own four-hour check, which stays as it is and independent of this;
* changing the server's configuration from the panel.

## 6. Acceptance criteria

| # | Test scenario | Expected result |
|---|---|---|
| A-1 | As an administrator, save a request window of 2 hours, then request a window of 3 hours for a station | The request is refused; a 2-hour request is accepted |
| A-2 | Save a request window of 5 hours | Refused; nothing is stored and the limit in force is unchanged |
| A-3 | Have the server's configuration say 6 hours for the window, save nothing, and request a 5-hour window | Refused: the ceiling holds without any saved value |
| A-4 | Save a session length of 30 minutes, sign in, and read the session's expiry | It is 30 minutes ahead |
| A-5 | Hold a session, shorten the session length, then use the held session | It still works until its own original expiry |
| A-6 | Save an enrollment token lifetime of 2 hours and issue a token | It expires in 2 hours; a token issued before keeps its expiry |
| A-7 | Save a value below its minimum, above its maximum, and a non-integer | Each is refused with a message naming the range; nothing is stored |
| A-8 | Read the policy before any save, and after one | Before: the configured values with no sign of a saved policy; after: the saved values and a sign that a policy is saved, with the configured values and the ranges alongside |
| A-9 | Save values, then return to the server's values | The configured values apply again |
| A-10 | Save values, change the server's configuration, restart, and read the policy | The saved values are still in force |
| A-11 | As an observer, read the policy, then try to save and to return to the server's values | Reading works; both changes are refused as forbidden |
| A-12 | Save the same values that are already in force, twice | Both succeed; the second adds no audit entry |
| A-13 | Save, then return to the server's values | An audit entry exists for each, naming the old and new values, and for the return the values it went back to |
| A-14 | In the panel, an administrator edits, saves, and returns to the server's values | Each works, the confirmation message says what applies when, and the return asks first |
| A-15 | In the panel, an observer opens the policy | The values are shown and nothing is editable |
| A-16 | In the panel, lower the window limit and open a station's request form | The form names the new limit and refuses a longer window before sending |
| A-17 | In the panel, enter an out-of-range value | The screen names the range and sends nothing |
| A-18 | Read the policy before and after this feature is deployed on an existing server | The same values are in force; no saved policy exists |

## 7. Impact on existing behavior

Nothing changes until an administrator saves a policy: the server's configured
values stay in force. After that, the three values come from what was saved.
The server's configuration for them becomes the default, no longer the only
source. The sentence on the Settings screen saying the values change only through
the server's configuration is replaced by an accurate one, and the window request
form takes its limit from the server instead of a fixed four hours.

## 8. Open questions

None.
