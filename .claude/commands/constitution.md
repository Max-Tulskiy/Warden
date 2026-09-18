---
description: Amend the project constitution following the procedure in its Section VII
argument-hint: <what to change and why>
---

Amend the constitution: **$ARGUMENTS**

Steps (Section VII of `.specify/memory/constitution.md`):

1. State the change together with its rationale — which need the current
   rules fail to cover. If the rationale is not obvious from the argument,
   ask the user.
2. Edit `.specify/memory/constitution.md`.
3. Decide the version bump semantics and update the header:
   * **MAJOR** — a principle is removed, or changed so existing code no
     longer complies;
   * **MINOR** — a principle, decision, or section is added;
   * **PATCH** — a wording clarification with no change of meaning.
4. Update the "last amended" date in the header.
5. Add a row to the "Version history" table.
6. Check whether `docs/ru/`, `docs/en/`, `README.md`, or
   `.specify/templates/` have become stale — bring them in line as part of the
   same change if so.

After the change, print the new version and a one-line summary of what
changed.
