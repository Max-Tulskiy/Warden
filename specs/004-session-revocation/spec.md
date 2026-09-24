# Spec: Session revocation

**Directory:** `specs/004-session-revocation/` · **Branch:** `004-session-revocation` · **Status:** draft · **Date:** 2026-09-24

---

## 1. Problem

An operator's session is a signed token that stays valid for eight hours, and
nothing on the server can end it early. The natural response to a suspected
theft of a session — changing the password — therefore does nothing to the
stolen session: the thief keeps working until the token expires. Spec 002
shipped password change with exactly this limit and recorded it as a project
boundary. There is also no way to sign out everywhere, for instance from a
shared computer the operator has left.

A second gap sits next to it. When the server refuses a session, the panel
does not notice: each screen just shows its own "could not load" message, and
the operator is never sent back to sign in.

## 2. Why

Constitution principle 5 says access to the complex's data is authenticated, and
the panel exposes everything the agents collected. Authentication that cannot be
withdrawn is only as strong as the operator's last unobserved moment. Spec 002
listed session revocation as its own piece of work, and the planned management of
several operator accounts depends on it: resetting or disabling another
operator's account is meaningless while their existing sessions keep working.

## 3. User scenarios

### Primary scenario

1. An operator suspects that someone else is using their session, for example
   after leaving a browser open on a shared machine.
2. The operator opens "Настройки" and changes the password.
3. The operator stays signed in on the device where the change was made.
4. The next time any other browser or device uses its old session, the server
   refuses it. That browser returns to the sign-in screen and says the session
   has ended.

### Additional scenarios

* An operator ends all their sessions without changing the password, from the
  same screen, and has to sign in again everywhere, including on the device
  they used.
* An operator has the panel open in two browsers, ends all sessions from one,
  and the other returns to the sign-in screen on its next action.

### Edge cases

| Situation | Expected behavior |
|---|---|
| The current password given for a password change is wrong, or the new password is refused | Nothing changes and no session is ended |
| An operator signs in after their sessions were ended | The new session works normally; only the earlier ones are refused |
| A session issued before this feature reaches a server that has it | It is refused once, and the operator signs in again; nothing else is lost |
| Several panel requests are refused at the same moment | The operator ends up on the sign-in screen once, with no error loop |
| A password change is repeated in quick succession | Each change ends every session issued before it |
| A session ends by reaching its normal expiry | Behaves as before: the panel returns to the sign-in screen |
| An enrolled agent is running | Agents do not use operator sessions and are unaffected |
| Someone signs in with a wrong password | This is a failed sign-in, not an ended session, and shows the existing message |

## 4. Requirements

| # | Requirement | Priority |
|---|---|---|
| R-1 | Changing an operator's own password must end every other session of that operator, taking effect on the next request the old session makes | required |
| R-2 | The session on which the password was changed must stay usable, so the operator is not forced to sign in again straight after | required |
| R-3 | An operator must be able to end all of their own sessions, including the current one, without changing the password | required |
| R-4 | A session that has been ended must be refused on every operator action exactly as an invalid or expired one is | required |
| R-5 | When the server refuses the panel's session on any screen, the panel must return to the sign-in screen and say that the session has ended | required |
| R-6 | Every password change and every "end all sessions" action must be recorded in the audit log | required |
| R-7 | A failed password change must not end any session | required |
| R-8 | The panel must say plainly, where it offers each action, what the action does to other sessions and to the current one | required |
| R-9 | Ending sessions must not change how long a new session lasts | required |

## 5. Out of scope

* listing an operator's sessions, or ending one session and keeping the others —
  revocation is all sessions of one operator at once;
* ending another operator's sessions — there is one account per deployment
  today, and administering other accounts belongs to the operator-management spec
  that builds on this one;
* changing how long a session lasts, or sliding or refresh-based sessions;
* notifying the operator by any channel that their sessions were ended;
* detecting a stolen session, or an idle timeout;
* any change to how agents authenticate.

## 6. Acceptance criteria

| # | Test scenario | Expected result |
|---|---|---|
| A-1 | Sign in twice to get two sessions, change the password with the first, then use the second | The second is refused as unauthorized |
| A-2 | After that password change, use the first session | It still works |
| A-3 | Sign in twice, end all sessions with the first, then use either | Both are refused as unauthorized |
| A-4 | End all sessions, then sign in again | The new session works |
| A-5 | Change the password with a wrong current password, then use another session | The other session still works |
| A-6 | Present a session issued before this feature | It is refused as unauthorized |
| A-7 | Change the password and end all sessions | An audit entry exists for each, and none contains a password |
| A-8 | In the panel, have the server refuse the session on any screen | The panel shows the sign-in screen with a message that the session has ended, once |
| A-9 | In the panel, change the password | The operator stays signed in, and the screen says other sessions were ended |
| A-10 | In the panel, end all sessions | The operator lands on the sign-in screen |
| A-11 | Present a session for an unknown or wrong account, or with no token | Refused exactly as before |

## 7. Impact on existing behavior

The password change now keeps the operator signed in on the current device and
ends every other session, where before it left all of them valid. The panel is
the only client of that operation, so nothing outside this repository changes.
Every session issued before the upgrade stops working once, so each operator
signs in again a single time. Agents, reports, the audit log, and the session
lifetime are unchanged. The sentence on the Settings screen saying earlier
sessions stay valid is replaced by an accurate one.

## 8. Open questions

None.
