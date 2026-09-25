# Spec: Connect a Windows agent to the server from a window and the installer, trusting the server's own certificate authority

**Directory:** `specs/009-windows-agent-configurator/` · **Status:** draft · **Date:** 2026-09-25

---

## 1. Problem

A Windows station is connected to the server today by editing a protected
configuration file by hand. The administrator has to find that file in a
folder ordinary users cannot open, type in the server address and a one-time
enrollment token, and restart the service. If the token is missing, the
service stops with an error instead of waiting to be configured, and the only
place the reason shows up is the service's own log.

A second problem sits behind the first. In the default deployment the server's
certificate is issued by a certificate authority of its own, which no
workstation knows, so the agent refuses to talk to the server. Enrollment
cannot succeed at all until someone makes the workstation trust that authority,
and the complex offers no supported way to do it.

Zabbix agent, whose active model this complex follows (D-1), has the opposite
experience: the server address is entered in the installer, and connecting the
agent is a matter of filling in a field.

## 2. Why

The person affected is the information-security administrator who rolls the
agent out — by hand on one machine, or by a silent install pushed to many. The
first thing that administrator must be able to do, install the agent and see
the station appear in the panel, does not work out of the box on a self-hosted
server, and when it fails it fails without a message an administrator would
read.

No row of the constitution's "Purpose" table maps to this directly: it is the
delivery path every row depends on, since the agent provides no data until it
is enrolled. It rests on three existing rules: the enrollment-token exchange
(D-3), the native Windows installer (D-7), and principle 5 (the exchange is
authenticated and encrypted), which the feature must keep intact rather than
route around.

## 3. User scenarios

### Primary scenario

1. The administrator issues an enrollment token in the panel. The panel shows,
   beside it, the fingerprint of the server's certificate authority.
2. On the Windows station the administrator opens the agent's window
   («Warden Agent — настройка») from the Start menu and approves the
   elevation prompt.
3. The administrator enters the server address and the token and asks to
   connect.
4. The server's certificate is not trusted, and the server offers its own
   certificate authority. The window shows who that authority is, how long it
   is valid, and its fingerprint, and asks the administrator to compare the
   fingerprint with the one in the panel.
5. The administrator confirms. The window enrolls the station and reports it as
   connected. The station appears in the panel as active, and the agent works
   from then on with certificate checking on.

### Additional scenarios

* **Interactive install.** The installer's wizard asks for the server address
  and the token and, optionally, the fingerprint the administrator expects. On
  the final page an option opens the agent's window. Every field may be left
  empty to finish in the window later.
* **Silent install.** The same three values are given to a silent install. If
  the fingerprint matches, the station is enrolled with no prompt at all.
* **Silent install without a fingerprint against a self-signed server.** The
  installation succeeds, the station is not enrolled and nothing is trusted;
  the administrator finishes in the window.
* **A server whose certificate the system already trusts** (a certificate from
  a public authority, or one distributed to the workstations by the
  organization). The window asks nothing about certificates and connects.
* **Checking before enrolling.** With only an address entered, the window says
  whether the server is unreachable, reachable but not trusted, or reachable
  and trusted.
* **Looking at the state.** At any time the window shows whether the service
  is running, whether the station is enrolled and with which server, when the
  server was last reached successfully, and the last error.
* **Moving the station to another server.** The window warns that the station
  must be enrolled again, asks for confirmation, forgets the previous
  enrollment and the trust given to the previous server, and enrolls at the new
  one.
* **The server's authority changed** (for example, the server was rebuilt and
  issued a new authority). The station can no longer verify the server. The
  window says so, offers the new authority for the same fingerprint comparison,
  and, once confirmed, the enrolled station carries on without enrolling again.

### Edge cases

* The token is wrong, expired, or already used: the window says which, and
  nothing is stored.
* The fingerprint the administrator expected does not match the one the server
  offers: the authority is not trusted, the station is not enrolled, and the
  message says the fingerprints differ.
* The address is wrong or the server is down: the message tells this apart
  from a certificate that is not trusted and from a refused token, since each
  is fixed differently.
* The server offers no authority of its own (its certificate comes from a
  public one) and the system does not trust the certificate: the window says
  there is no authority to offer, so the certificate has to be made trusted
  some other way.
* The window is opened without administrator rights: it explains why it cannot
  change anything and changes nothing.
* The service starts before it is configured: it keeps running and waits,
  rather than stopping or restarting in a loop.
* The connection drops during enrollment: afterwards the station is either
  fully enrolled or exactly as before; a half-written state never remains.
* An installer upgrade over an enrolled station: the connection is neither
  asked about nor changed.
* A station already enrolled by an earlier version, or configured with the token
  in the configuration file: it keeps working unchanged.

## 4. Requirements

| # | Requirement | Priority |
|---|---|---|
| R-1 | A Windows station must be connectable to a server by entering the server address and an enrollment token in a window on the station, without editing any file | required |
| R-2 | The window must show the service's state, whether the station is enrolled and with which server, when the server was last reached successfully, and the last error | required |
| R-3 | The window must be able to check an address without enrolling, and say whether the server is unreachable, reachable but not trusted, or reachable and trusted | required |
| R-4 | When the server's certificate is not trusted and the server offers its own certificate authority, the window must show that authority's owner, validity, and fingerprint, and trust it only after the administrator confirms or a fingerprint expected in advance matches | required |
| R-5 | The server must offer its own certificate authority's certificate, with its fingerprint, to a station that has not enrolled yet, when the deployment uses one, and say plainly that it has none when it does not | required |
| R-6 | The panel must show that same fingerprint where the administrator issues an enrollment token, so it can be compared with the one the window shows | required |
| R-7 | Trust given this way must apply only to the agent's own connections; the station's system-wide certificate trust must not be modified | required |
| R-8 | The agent's configuration and the trust it holds must be readable and changeable only by administrators, like the rest of the agent's data | required |
| R-9 | After trust and enrollment the agent must work exactly as before — poll, heartbeat, inventory, answering requests — with certificate checking on. The one request made without checking the server's certificate is the one that fetches the server's authority before it is trusted; it carries no token and no key, and what it returns is used only after its fingerprint is confirmed. No other mode that skips checking may be introduced | required |
| R-10 | The enrollment token entered in the window or given to the installer must not remain on the station after the attempt, whether it succeeded or failed, and a failed attempt must store nothing, including trust. A token an administrator put in the configuration file by hand is that administrator's own choice and is left as it is | required |
| R-11 | Changing the server of an enrolled station must need explicit confirmation and a new enrollment, and trust given to the previous server must not carry over to the new one | required |
| R-12 | Changes to the connection must need administrator rights; without them the window must say so and change nothing | required |
| R-13 | The installer's wizard must ask for the server address, the token, and optionally the expected fingerprint; all three must be optional, and a failed connection attempt must never fail the installation | required |
| R-14 | The same three values must be accepted by a silent install, and a silent install without an expected fingerprint must never trust an authority it has not been told to | required |
| R-15 | A service that is not configured yet must keep running and wait, and start working within one minute of being configured, without a reinstall | required |
| R-16 | An installer upgrade of an enrolled station must not ask about or change its connection | required |
| R-17 | Everything the window and the installer show, including errors, must be in Russian | required |
| R-18 | Trust decisions (with the fingerprint accepted), enrollment attempts and their outcomes, and changes of server must be recorded in the agent's local log, without the token; the server keeps recording enrollment as before | required |
| R-19 | The server certificate authority to trust must also be settable through the agent's configuration on any platform, so a Linux station, or one without the window, can use a self-signed server | nice to have |

## 5. Out of scope

* does not add a window or an installer page for Linux — a Linux station keeps
  configuration through its file and its packages; only R-19 is shared;
* does not let the window change polling intervals, inventory intervals, or
  retention — it covers the connection to the server and nothing else;
* does not let the window or the installer choose the name a station registers
  under: it is always the computer's name, as by default today (a name set in
  the configuration file keeps working);
* does not install any certificate into the system's trust store, and does not
  add client certificates (mutual TLS stays deferred, D-3);
* does not renew or rotate trust by itself — when the server's authority
  changes, the administrator trusts the new one, by the same comparison;
* does not disconnect a station on its own without a new server to enroll at —
  a station is disabled from the panel, as today;
* does not push configuration from the server to the agent — the agent still
  only initiates connections (D-1);
* does not make the first trust safe against an attacker in the path when the
  administrator does not compare the fingerprint: trusting an authority the
  first time rests on that comparison, and the boundary is stated in the
  documentation (principle 10);
* does not sign the installer — the SmartScreen warning of Section V remains;
* does not add a tray icon or any resident interface — the window opens when the
  administrator asks for it;
* does not change how the agent is uninstalled, or what an uninstall leaves
  behind.

## 6. Acceptance criteria

| # | Test scenario | Expected result |
|---|---|---|
| A-1 | Against a test server presenting a certificate from its own authority, connect with an address, a token, and confirmation of the shown fingerprint | The station is enrolled and a following poll succeeds with certificate checking on |
| A-2 | The expected fingerprint differs from the one the server offers | Nothing is trusted or enrolled, nothing is stored, and the message says the fingerprints differ |
| A-3 | The silent path with no expected fingerprint against the same server | The install is not failed; nothing is trusted and the station is not enrolled |
| A-4 | Against a server whose certificate is already trusted | The station connects, no authority is fetched, and no trust decision is asked or stored |
| A-5 | Present a token that is unknown, expired, or already used | A message names which; nothing is stored, including trust |
| A-6 | Use an address nothing listens on, an address with an untrusted certificate, and a refused token, one after another | Three different messages |
| A-7 | Change the server of an enrolled station, first declining the confirmation and then accepting it | Declining changes nothing; accepting clears the old enrollment and trust, and enrollment at the new server works |
| A-8 | Trust an authority, then list what changed on the station | Only the agent's own data changed; the system certificate trust is untouched |
| A-9 | Open the window, or run the change, without administrator rights (manual, Windows) | It explains why and changes nothing |
| A-10 | Start the service unconfigured, then configure it | It keeps running and, within one minute of configuring, makes its first poll |
| A-11 | Complete enrollment successfully, then again with a failure; search the agent's stored files and its log | The token appears in none of them |
| A-12 | Compare the fingerprint the server offers with the one the panel shows | They are the same value, and equal to the fingerprint of the certificate itself |
| A-13 | Ask a server that has no authority of its own to offer one | The reply says it has none, and the window says the certificate must be made trusted another way |
| A-14 | Trust an authority and enroll; read the agent's local log | It holds the accepted fingerprint, the enrollment outcome, and the server, and no token |
| A-15 | Rebuild the server so its authority changes, with an enrolled station | The window says the server cannot be verified, offers the new authority, and after confirmation the same station works without enrolling again |
| A-16 | Start an agent enrolled by the previous version, and one with the token in its configuration | Both connect exactly as before |
| A-17 | Check the text of every message the window and the installer can show | All of it is Russian |
| A-18 | Record every request the connection flow makes against a test server | The token and the agent's key appear only on requests that verified the certificate; the one unverified request carries neither |
| A-19 | On a real Windows 10/11 machine: walk through the wizard with and without values, a silent install with the three values, an upgrade over an enrolled station, and the window from the Start menu (manual, Section VI) | Each behaves as the scenarios above describe |

## 7. Impact on existing behavior

An agent that is not configured no longer exits with an error: it waits and
reports in its status that it has nothing to connect to. A configuration file that
holds a token keeps working, and a station already enrolled is untouched.
The default configuration installed on Windows no longer carries a placeholder
token to replace by hand.

The server gains one piece of public information, the certificate of its own
authority and its fingerprint, which is readable without a credential because
the station that needs it cannot yet be trusted or enrolled; the plan must
justify that as another endpoint open to unauthenticated callers (D-10). The
panel shows the fingerprint on the screen where tokens are issued. The default
deployment changes so that the server can read the certificate authority its
reverse proxy created.

The installer gains a wizard page and a second program with a Start menu
entry. The parts that only run on Windows are built in CI but proven only by
the manual pass of A-19.

## 8. Open questions

*None — this section is empty and the spec is ready for planning.*
