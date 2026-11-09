---
# Shared Kanbanauts doit prompt
---

# Implement the plan for a GitHub issue

Issue number: `${{ inputs.issue_number }}`
Repository: `${{ github.repository }}`
Existing open pull request (empty when none): `${{ env.KANBANAUTS_EXISTING_PR }}`

You are implementing a feature or fix for a GitHub issue.

When `KANBANAUTS_EXISTING_PR` is set, the repo is already checked out on that
pull request's head branch. Reuse that pull request. Do not open a new one.
When `KANBANAUTS_EXISTING_PR` is empty, the repo is checked out at the default
branch and you must open a new draft pull request.

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
   - Do NOT open a pull request and do not call `push_to_pull_request_branch`.
   - Call `add_comment` with TL;DR, why nothing to implement, and **Next step**
     (`/ai doit` to retry, or `/ai plan` to replan).
   - Call `kanban_report` with `status=blocked` (reason: nothing to implement).
   - Stop.

4. Choose the delivery path:
   - When `KANBANAUTS_EXISTING_PR` is set: stay on the current branch. Do not
     create a new branch. Do not call `create_pull_request`.
   - When `KANBANAUTS_EXISTING_PR` is empty: create a feature branch
     `<issue-number>-<short-descriptive-slug>`.

5. Implement the change. Follow project conventions.

6. Prepare the commit:
   - Use a conventional message (`fix(...)`, `feat(...)`, ...).
   - Include `Closes #<issue-number>` in the commit body / push message.
   - Stage named files only (`git add path/to/file`). Do not use `git add -A`.
   - When reusing an existing pull request: leave the file changes in the
     worktree. Do NOT run `git commit` or `git push` — a local commit is not
     published. Call `push_to_pull_request_branch` once with
     `pull_request_number` set to `KANBANAUTS_EXISTING_PR` and `message` set
     to the conventional commit message (include `Closes #<issue-number>`).
   - When opening a new pull request: you may commit locally as usual, then
     push and open a draft with `create_pull_request`. Reference the issue
     with `Closes #<issue-number>`.

7. Call `add_comment` with:
   - TL;DR (what was done, in plain language)
   - What changed (short bullets)
   - PR link (the existing PR when reusing, or the new draft)
   - **Next step**: Comment `/ai review` to start the AI review.
8. Call `kanban_report` with `status=succeeded`.
   - When reusing: pass the numeric `pr_number` (`KANBANAUTS_EXISTING_PR`).
   - When creating a new PR: Omit `pr_number`. The workflow fills the real
     pull request number after creation. Do not pass temporary ids such as
     `#aw_...`.

When the specification is unclear after reading the issue and comments, call
`add_comment` with the unclear points and a **Next step**, call `kanban_report`
with `status=blocked`, and stop.
