# Implementation plan: [FEATURE NAME]

**Spec:** [./spec.md](./spec.md) · **Status:** draft · **Date:** YYYY-MM-DD

---

## 1. Approach

How the feature is implemented: affected agent/server/panel modules, sequence
of changes, new types and endpoints. Unlike `spec.md`, concrete module, class,
and function names belong here.

## 2. Alternatives considered

| Option | Why rejected |
|---|---|
| … | … |

## 3. Constitution compliance

A table covering every touched principle in Section I of the constitution.

| Principle | How it is satisfied |
|---|---|
| 1. Platform code is isolated | … |
| 2. Data does not leave the buffer without a request | … |
| 3. Request window ≤ 4 hours | … |
| … | … |

**Violations:** none / describe and justify.

## 4. Affected modules

| Module | Change |
|---|---|
| `server/...` | … |
| `agent/...` | … |
| `web/...` | … |

## 5. Data formats

New or changed database tables, Pydantic schemas, endpoints — cross-referenced
to the relevant section of `contracts/openapi.yaml`.

## 6. Interface

What changes in the web panel: new screens, fields, states.

## 7. Risks

| Risk | Mitigation |
|---|---|
| … | … |

## 8. Verification plan

Unit and integration tests (principle 7 — no real hardware needed), commands
for a local run:

```bash
pytest server/tests/unit -k ...
pytest agent/tests/unit -k ...
```

If the feature touches a platform collector, describe both the fixture-based
check that runs in CI and the live check to perform before release
(principle 10, constitution Section VI).
