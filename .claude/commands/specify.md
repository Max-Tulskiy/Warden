---
description: Create a spec for a new feature (what and why, no technical decisions)
argument-hint: <feature description in your own words>
---

Create a spec for the feature described by the user: **$ARGUMENTS**

Steps:

1. Read `.specify/memory/constitution.md` — project purpose, principles, and
   boundaries.
2. Look at existing directories under `specs/` and pick the next free
   three-digit number. Build a short kebab-case English slug, e.g.
   `004-daily-reports`.
3. If the project is under git and the current branch does not match the new
   feature, offer to create a branch with the same name as the directory.
4. Create `specs/NNN-name/spec.md` from `.specify/templates/spec-template.md`.

Content requirements:

* Write **what** and **why**, not **how**. No module, class, function, or file
  names — those belong in the plan.
* Do not guess on the user's behalf. Anything that does not follow
  unambiguously from the request and the constitution is marked
  `[NEEDS CLARIFICATION: specific question]`.
* The "Out of scope" section is mandatory — leaving it out violates
  constitution principle 10.
* Phrase acceptance criteria so they can be verified by a test (principle 7 —
  without real hardware wherever possible).
* If the feature follows from a lab assignment function, cite the matching row
  in the constitution's "Purpose" table.

After creating the file, print its path, list the open questions, and ask the
user about them via AskUserQuestion if they block planning.
