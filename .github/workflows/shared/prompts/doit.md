---
# Shared Kanbanauts doit prompt
---

# Implement the plan for a GitHub issue

Issue number: `${{ inputs.issue_number }}`
Repository: `${{ github.repository }}`

You are implementing a feature or fix for a GitHub issue.
The repo is already checked out at the default branch.

PRIVACY: Do not put emails, names, IP addresses, IBANs, tokens, passwords,
or other personal data in any GitHub comment.

If `AGENTS.md` exists, read it first.

SCOPE:
- Implement ONLY what the issue asks for.
- Keep the PR small and focused.
- Add tests for changed business logic.
- Do NOT edit `.github/workflows` or CI config unless the issue explicitly asks.
- Do NOT install new dependencies unless strictly required.

Follow the shared comment-style rules for every `add_comment` you post.

Instructions:

1. Read the full issue including ALL comments with `gh issue view <number> --comments`.
   Use the latest plan comment when one exists. A plan comment is a comment that
   contains the text `kanbanauts:plan`, or the line `kanbanauts-plan`, or the plan
   sections (TL;DR, Goal, Proposed approach).
   When no plan comment exists, the issue title, body, and the other comments are
   the specification. Implement that. A missing plan comment is not a reason to stop.
   Ignore command comments, grant comments, and short status comments.
   When the chosen plan lists an open question and no later human comment answers
   it, call `add_comment` that lists the questions under TL;DR, then a **Next step**
   with `/ai doit <your answers>`, call `kanban_report` with `status=blocked`, and stop.
   When the issue lists more than one approach and there is no plan, implement the
   first concrete approach and name that choice in the PR.

2. Understand the codebase: read relevant files, search for related code.

3. If the plan (or your investigation) shows that no code change is needed:
   - Do NOT open a pull request.
   - Call `add_comment` with TL;DR, why nothing to implement, and **Next step**
     (`/ai doit` to retry, or `/ai plan` to replan).
   - Call `kanban_report` with `status=blocked` (reason: nothing to implement).
   - Stop.

4. Create a feature branch: `<issue-number>-<short-descriptive-slug>`

5. Implement the change. Follow project conventions.

6. Commit with a conventional message (`fix(...)`, `feat(...)`, ...).
   Include `Closes #<issue-number>` in the commit body.
   Stage named files only (`git add path/to/file`). Do not use `git add -A`.

7. Push and open a draft pull request with `create_pull_request`.
   Reference the issue with `Closes #<issue-number>`.

8. Call `add_comment` with:
   - TL;DR (what was done, in plain language)
   - What changed (short bullets)
   - PR link
   - **Next step**: Comment `/ai review` to start the AI review.
9. Call `kanban_report` with `status=succeeded`. Omit `pr_number`.
   The workflow fills the real pull request number after creation.
   Do not pass temporary ids such as `#aw_...`.

When the specification is unclear after reading the issue and comments, call
`add_comment` with the unclear points and a **Next step**, call `kanban_report`
with `status=blocked`, and stop.
