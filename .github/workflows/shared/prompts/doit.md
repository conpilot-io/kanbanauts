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

Instructions:

1. Read the full issue including ALL comments with `gh issue view <number> --comments`.
   Find the latest plan comment that contains `<!-- kanbanauts:plan -->`. Treat that as
   the primary specification.

2. Understand the codebase: read relevant files, search for related code.

3. If the plan (or your investigation) shows that no code change is needed:
   - Do NOT open a pull request.
   - Call `add_comment` explaining why.
   - Call `kanban_report` with `status=blocked` (reason: nothing to implement).
   - Stop.

4. Create a feature branch: `<issue-number>-<short-descriptive-slug>`

5. Implement the change. Follow project conventions.

6. Commit with a conventional message (`fix(...)`, `feat(...)`, ...).
   Include `Closes #<issue-number>` in the commit body.
   Stage named files only (`git add path/to/file`). Do not use `git add -A`.

7. Push and open a draft pull request with `create_pull_request`.
   Reference the issue with `Closes #<issue-number>`.

8. Call `add_comment` with a short summary and the PR link.
9. Call `kanban_report` with `status=succeeded` and `pr_number` set.

If the plan is unclear, call `kanban_report` with `status=blocked` and stop.
