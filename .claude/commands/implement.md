---
description: Carry out a spec's tasks in order, checking them off
argument-hint: <NNN-name of the spec, or empty — the latest spec>
---

Implement the tasks from: **$ARGUMENTS**

Steps:

1. Read `.specify/memory/constitution.md`, `specs/NNN-name/spec.md`,
   `plan.md`, and `tasks.md`.
2. Work through `tasks.md` in order. Check `[x]` off in the file after each
   one.
3. Follow TDD (skill `dev-python`): test before implementation, wherever the
   tasks call for it.
4. Every change must conform to the constitution. If implementation reveals a
   need to violate a principle, stop and tell the user instead of violating
   it silently.
5. Follow the language mode (principle 9): code and docstrings in English;
   user-facing text and project documentation in Russian; this constitution
   and everything under `specs/` in English.
6. Leave no AI-generation markers anywhere — not in code, comments,
   documentation, or commit messages.
7. Before marking the final tasks done, run `ruff check`, `ruff format
   --check`, `mypy`, `bandit`, and the tests for the affected modules.

If part of the task list is blocked by an external factor (no access to a
Windows machine for a live collector check, etc.), finish everything else and
explicitly say what is left and why, instead of silently skipping it.
