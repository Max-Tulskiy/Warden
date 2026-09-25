---
description: Create an implementation plan from a finished spec (how, with a constitution check)
argument-hint: <NNN-name of the spec, or empty — the latest spec>
---

Create an implementation plan for: **$ARGUMENTS**

Steps:

1. Read `.specify/memory/constitution.md`.
2. Find `specs/NNN-name/spec.md` (by argument, or the most recent
   directory without a `plan.md`). If the spec still has
   `[NEEDS CLARIFICATION: ...]` markers, stop and list them for the user — a
   plan is not written against an incomplete spec.
3. Create `specs/NNN-name/plan.md` from `.specify/templates/plan-template.md`.

Content requirements:

* The "Constitution compliance" section is mandatory and goes principle by
  principle through Section I for every one it touches — with a concrete
  mechanism ("the window is checked in `WindowRequestSchema.validate_range`"),
  not a vague claim ("the window is respected").
* If the plan would violate a principle, that is not marked as resolved: either
  a different approach removes the violation, or it is explicitly escalated as
  a constitution amendment (Section VII) before continuing.
* "Alternatives considered" must include at least one real alternative with a
  reason for rejecting it, not a formality.
* "Verification plan" names concrete commands and states what is checked
  against fixtures in CI versus what is checked manually on a real device
  (principle 7, constitution Section VI).

After creating the file, print its path and briefly list the affected modules.
