# Spec: [FEATURE NAME]

**Directory:** `specs/NNN-name/` · **Status:** draft · **Date:** YYYY-MM-DD

> This document answers **what** and **why**. Module, class, function, and file
> names do not belong here — they appear in `plan.md`.
> Anything unclear is marked `[NEEDS CLARIFICATION: question]`, never guessed at.

---

## 1. Problem

What is broken or missing today. One or two paragraphs, no solution.

## 2. Why

Who needs this and under what circumstances. If the feature follows from a lab
assignment function, quote the relevant row from the constitution's "Purpose"
table.

## 3. User scenarios

### Primary scenario

1. The administrator …
2. The agent/server …
3. The administrator sees …

### Additional scenarios

* …

### Edge cases

What must happen when: the agent is offline; the request window exceeds 4
hours; there is no data for the window at all; an enrollment token is reused;
the network between agent and server drops mid-upload.

## 4. Requirements

Phrased so they can be verified, with no technical decisions.

| # | Requirement | Priority |
|---|---|---|
| R-1 | The system must … | required |
| R-2 | The system must … | nice to have |

## 5. Out of scope

Explicit boundaries. Without this section the spec is considered incomplete
(constitution principle 10).

## 6. Acceptance criteria

| # | Test scenario | Expected result |
|---|---|---|
| A-1 | … | … |
| A-2 | … | … |

## 7. Impact on existing behavior

What changes for the administrator and for already-enrolled agents.

## 8. Open questions

* `[NEEDS CLARIFICATION: …]`

*A spec is ready for planning once this section is empty.*
