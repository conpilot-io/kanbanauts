---
# Shared Kanbanauts comment style
---

# How to write GitHub comments

Write for a busy reader. Prefer short bullets over long paragraphs.
Start every posted comment with a plain-language **TL;DR** (3-5 bullets, little jargon).
Use clear markdown headings (`## TL;DR`, `## What changed`, `## Test instructions`,
`## Next step`, and when needed `## Reproduction steps`).
Put detail only in later sections that need it (approach, files, findings).
End every posted comment with a **Next step** section that includes a copy-paste `/ai ...` line
when the next action is a command.
Prefer `/ai` (not `/agent` or `/kanbanauts`) in Next step text.

## Test instructions (doit and clean review)

When posting Test instructions:

- If a user can test the change on the frontend / UI: write step-by-step QA instructions.
- If the change affects backend or shared runtime behavior that is not directly
  testable on the frontend: write `Do regression testing`.
- If the change is internal only (unit tests, docs, CI/scripts, or other
  non-user-facing work): write `No testing applied`.

## Reproduction steps (review findings)

Include step-by-step **Reproduction steps** only for findings that are both
severity blocker or major **and** user-facing (a person can trigger them in the
product UI). Do not invent reproduction steps for minor notes, missing tests,
style issues, or internal/code-only defects. Do not post Test instructions on the
issue when the review is blocked on findings.

## Next step by outcome

- Plan ready: Comment `/ai doit` to implement this plan.
- Plan needs input / blocked on questions: Answer in a comment, then run:
  `/ai doit <your answers>`
  (or `/ai plan` to replan after you answer).
- Plan no_code: Explain that no code change is needed. Next step: close the issue
  or move it to Done.
- Plan failed: Comment `/ai plan` to try again.
- Doit succeeded (PR opened): Link the PR. Include Test instructions. Comment
  `/ai review` to start the AI review.
- Doit blocked on questions: Comment `/ai doit <your answers>` after you decide.
- Doit failed / nothing to implement: Comment `/ai doit` to retry, or `/ai plan` to replan.
- Review clean: Post Test instructions on the issue. Approve and merge the PR in
  GitHub when ready.
- Review has fixable findings: List the findings. Add Reproduction steps only for
  user-facing blocker/major issues. On the **issue**, comment
  `/ai doit <what to fix>`.
- Review blocked (no PR): Comment `/ai doit` on the issue to open a draft PR first.
