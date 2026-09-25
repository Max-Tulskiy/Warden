---
description: Break a finished plan into numbered, verifiable tasks
argument-hint: <NNN-name of the spec, or empty — the latest spec>
---

Create the task list for: **$ARGUMENTS**

Steps:

1. Find `specs/NNN-name/plan.md` (by argument, or the most recent
   directory with a `plan.md` but no `tasks.md`).
2. Create `specs/NNN-name/tasks.md` from `.specify/templates/tasks-template.md`.

Content requirements:

* Every task is a verifiable outcome: a new endpoint, a test, a screen, a
  migration. Not "improve module X" but "add
  `POST /api/v1/agents/{id}/requests` with window validation ≤ 4 hours."
* Implementation tasks come before their tests only where a test genuinely
  cannot be written first — usually it is the other way round, per TDD from
  skill `dev-python`: test before implementation.
* Separate tasks for updating `docs/ru/` and `docs/en/`, and, if the contract
  changed, `contracts/openapi.yaml` — do not forget the Russian/English split
  for user-facing documentation (constitution principle 9).
* Final tasks run `ruff`/`mypy`/`bandit` and the full test suite of the
  affected modules.

After creating the file, print its path and the task count.
