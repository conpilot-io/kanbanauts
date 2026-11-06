# End-to-end checklist

Use a test org that is **not** `conpilot-io`.

1. Install https://github.com/apps/kanbanauts on a sandbox repo.
2. Merge the **Set up Kanbanauts** PR.
3. Set org secret `KANBANAUTS_AI_API_KEY` and variable `KANBANAUTS_AI_MODEL`.
4. Create an issue, add it to the Project, move it to Plan.
5. Expect labels `agent:queued` → `agent:running` → plan comment → `agent:succeeded`.
6. Move the central `v1` tag to a test commit and re-run. Expect new behavior with no change in the sandbox repo.

Optional: `.github/workflows/e2e.yml` for a manual reminder checklist.
