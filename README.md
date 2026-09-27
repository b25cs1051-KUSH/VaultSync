# VaultSync shared agent workspace

This repository is the shared source of truth for the BAND factory.

## Agent workflow

1. Before starting a work item, fetch and update from `origin/main`.
2. Read the latest task, plan, and handoff files before acting.
3. Change only files owned by the current seat or explicitly assigned in the plan.
4. Commit completed work with the seat name and work-item ID.
5. Pull with rebase immediately before pushing, rerun affected checks, then push.
6. Never force-push, overwrite another seat's work, or resolve an ambiguous conflict automatically.

Verifier reports are stored in `handoffs/verifier/`. They contain the tested commit hash, exact commands, trimmed outputs, and the PASS or REJECT verdict.

