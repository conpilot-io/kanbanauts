---
# Shared Kanbanauts comment style
---

# How to write GitHub comments

Write for a busy reader. Prefer short bullets over long paragraphs.
Start every posted comment with a plain-language **TL;DR** (3-5 bullets, little jargon).
Put detail only in later sections that need it (approach, files, findings).
End every posted comment with a **Next step** section that includes a copy-paste `/ai ...` line.
Prefer `/ai` (not `/agent` or `/kanbanauts`) in Next step text.

## Next step by outcome

- Plan ready: Comment `/ai doit` to implement this plan.
- Plan needs input / blocked on questions: Answer in a comment, then run:
  `/ai doit <your answers>`
  (or `/ai plan` to replan after you answer).
- Plan no_code: Explain that no code change is needed. Next step: close the issue
  or move it to Done.
- Plan failed: Comment `/ai plan` to try again.
- Doit succeeded (PR opened): Link the PR. Comment `/ai review` to start the AI review.
- Doit blocked on questions: Comment `/ai doit <your answers>` after you decide.
- Doit failed / nothing to implement: Comment `/ai doit` to retry, or `/ai plan` to replan.
- Review clean: Approve and merge the PR in GitHub when ready.
- Review has fixable findings: On the **issue**, comment `/ai doit <what to fix>`.
- Review blocked (no PR): Comment `/ai doit` on the issue to open a draft PR first.
