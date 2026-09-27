# Shared Git collaboration rules

- Treat `origin/main` as the shared source of truth.
- Before work: ensure the tree is clean, then run `git pull --rebase origin main`.
- Read the current task, plan, and relevant files under `handoffs/` before acting.
- Commit only files owned by your seat or explicitly assigned to you.
- Before push: run the relevant checks, run `git pull --rebase origin main`, rerun affected checks, then push.
- Never force-push, rewrite published history, discard another agent's changes, or commit credentials.
- If a rebase or merge conflict is ambiguous, stop and report the conflicting paths instead of guessing.
- Preserve independent review: Builder reasoning must not be copied into Verifier reports, and the Verifier must not edit implementation or tests.

