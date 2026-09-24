# Spec: Operator management and roles

**Directory:** `specs/005-operator-management/` · **Branch:** `005-operator-management` · **Status:** done · **Date:** 2026-09-24

---

## 1. Problem

The panel has exactly one kind of user: a full administrator, and in practice
exactly one account, created from the server's configuration on first start.
Nobody can add a second person, take access away from someone who has left,
or reset a password that has been forgotten. Anyone who can sign in can also do
everything: request data from a workstation, issue enrollment tokens, switch
stations off, and read the audit log. There is no way to give a colleague the
ability to look at what was collected without also giving them the ability to
act on the stations.

## 2. Why

Constitution principle 5 says access to what the complex collects is
authenticated, and principle 8 makes the log the record of who did what. Both
assume that "who" can be more than one person and that some people should be
able to see without acting. The earlier specs left this open on purpose: the
audit log viewer (spec 003) noted that limiting the log to an administrator role
belonged here, and session revocation (spec 004) was built first because
disabling an account is meaningless while its sessions keep working.

## 3. User scenarios

### Primary scenario

1. The administrator opens "Операторы" in the panel and sees every account with
   its role and whether it is active.
2. The administrator creates an account for a colleague who only needs to look at
   the data: a username, the role "наблюдатель", and an initial password.
3. The colleague signs in with that password. The panel offers them the stations,
   the reports, and their own settings, and does not offer anything that acts on a
   station or manages accounts.
4. Later the colleague leaves. The administrator disables the account, and the
   colleague's open browser is sent back to the sign-in screen on its next action.

### Additional scenarios

* An administrator promotes an observer to administrator, or demotes an
  administrator to observer.
* An administrator sets a new password for a colleague who forgot theirs; the
  colleague's existing sessions end, and they sign in with the new password.
* An administrator re-enables an account they disabled.
* An observer changes their own password and ends their own sessions, exactly as
  an administrator can.

### Edge cases

| Situation | Expected behavior |
|---|---|
| An administrator tries to change their own role or disable their own account | Refused with a clear message; nothing changes |
| The account being demoted or disabled is the only other administrator | Allowed, because the acting administrator remains; the deployment is never left without an active administrator by the panel's own actions |
| An administrator tries to reset their own password from the operators screen | Refused with a message pointing to the change-password form in settings, which asks for the current password |
| A username already exists, ignoring letter case | Refused with a clear message; nothing is created |
| A username uses characters outside the allowed set, or a password is shorter than the minimum | Refused with a clear message; nothing is created |
| A disabled operator tries to sign in | Refused with the same message as a wrong password |
| An observer opens an administrator-only screen by its address | The panel shows a notice that they lack the rights; it does not sign them out |
| An observer sends an administrator-only request directly to the server | Refused as forbidden, which is different from an ended session |
| An administrator is demoted while they have an administrator-only screen open | Their next action there is refused; the panel then removes what they can no longer use |
| A change sets a role or status the account already has | Succeeds and records nothing |
| An unknown account is addressed | Reported as not found |

## 4. Requirements

| # | Requirement | Priority |
|---|---|---|
| R-1 | Every operator account must have exactly one role: administrator or observer | required |
| R-2 | An administrator must be able to see every account with its username, role, and whether it is active | required |
| R-3 | An administrator must be able to create an account with a username, a role, and an initial password | required |
| R-4 | An administrator must be able to change another account's role | required |
| R-5 | An administrator must be able to disable and re-enable another account; a disabled account cannot sign in and its existing sessions end at once | required |
| R-6 | An administrator must be able to set a new password for another account, which ends that account's sessions | required |
| R-7 | An observer must be able to see stations, reports, inventory, and the server's operating policy, and to change their own password and end their own sessions | required |
| R-8 | An observer must not be able to request data from a station, issue an enrollment token, enable or disable a station, read the audit log, or manage accounts | required |
| R-9 | These restrictions must be enforced by the server itself, not only by what the panel shows | required |
| R-10 | An administrator must not be able to change their own role or status | required |
| R-11 | Every account creation, role change, disabling, enabling, and password reset must be recorded in the audit log, without any password | required |
| R-12 | A new role or status must take effect on the account's next action, without the person signing in again | required |
| R-13 | Usernames must be unique regardless of letter case, use a restricted set of characters, and passwords must meet the existing minimum length | required |
| R-14 | Accounts that exist when this feature arrives must become administrators, so that nobody is locked out by the upgrade | required |
| R-15 | The panel must show each person the sections and actions they can use, and say which role they have | required |

## 5. Out of scope

* deleting an account — accounts are only disabled, so that the audit log's record
  of who did what keeps pointing at a name;
* limiting an observer to particular stations or particular data — an observer
  sees everything the complex has collected, only without acting on it;
* more than two roles, or permissions chosen one by one;
* forcing a person to change an initial or reset password at their first
  sign-in — the administrator who set it knows it until the person changes it;
* changing a username, self-registration, and single sign-on;
* notifying anyone by any channel that their account was created, changed, or
  disabled;
* changing how long a session lasts, or the server's operating policy (a
  separate spec);
* any change to how agents authenticate.

## 6. Acceptance criteria

| # | Test scenario | Expected result |
|---|---|---|
| A-1 | Create an observer, sign in as them, and request the station list, a report, and the policy | All succeed |
| A-2 | As the observer, request data from a station, issue an enrollment token, disable a station, read the audit log, list accounts | Each is refused as forbidden |
| A-3 | As the observer, change their own password and end their own sessions | Both succeed |
| A-4 | As an administrator, list accounts | Each appears with its role and status, and no password data |
| A-5 | Create an account whose username differs from an existing one only by letter case | Refused; nothing is created |
| A-6 | Create an account with a too-short password or a username with a disallowed character | Refused; nothing is created |
| A-7 | Change an observer's role to administrator, then request an administrator-only action as them without signing in again | The action is now allowed |
| A-8 | Change an administrator's role to observer while they hold a session, then request an administrator-only action as them | The action is refused; their session still works for observer actions |
| A-9 | As an administrator, change your own role, disable yourself, or reset your own password from the operators screen | Each is refused; nothing changes |
| A-10 | Disable an account that holds a session, then use the session and try to sign in | Both are refused |
| A-11 | Re-enable that account and sign in | Signing in works |
| A-12 | Reset another account's password | The old password and the account's sessions stop working, and the new password signs in |
| A-13 | Perform each of the five kinds of change | An audit entry exists for each, and none contains a password |
| A-14 | Repeat a change that leaves the role or status as it already is | Succeeds and adds no audit entry |
| A-15 | Start from the database as it was before this feature, with one operator | That operator is an administrator and can sign in |
| A-16 | In the panel, sign in as an observer | The administrator-only sections and controls are absent, the role is shown, and opening one of those sections by address shows a no-rights notice |
| A-17 | In the panel, use the operators screen to create, promote, demote, disable, enable, and reset a password | Each works and is reflected in the list |
| A-18 | Address an unknown account | Reported as not found |

## 7. Impact on existing behavior

Every existing account becomes an administrator, so nothing an existing operator
can do today changes. Three things that any signed-in operator could do before —
request data from a station, issue an enrollment token, and enable or disable a
station — and the audit log viewer, become administrator-only. That is the point
of the feature, and it only changes what a *new* observer account can do. The
panel gains a section for accounts and shows the person's role. Agents, reports,
and sessions are unchanged.

## 8. Open questions

None.
