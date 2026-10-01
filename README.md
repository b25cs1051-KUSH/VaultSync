# VaultSync shared agent workspace

This repository is the shared source of truth and judged result artifact for the BAND factory building the Pocketful track.

## Project status

- Phase 0: challenge requirements mapped across all four stages.
- Phase 1: reproducible WSL2, Docker, and official harness environment complete.
- Phase 2: four-seat factory architecture and acceptance authority defined.
- Pocketful implementation: not started, as required by the plan's factory-first sequence.

See `docs/phase-0-requirements-map.md`, `docs/phase-1-environment-setup.md`, `docs/phase-2-factory-architecture.md`, and the provisional `FACTORY.md` for the current evidence and boundaries.

## Agent workflow

1. Before starting a work item, fetch and update from `origin/main`.
2. Read the latest task, plan, and handoff files before acting.
3. Change only files owned by the current seat or explicitly assigned in the plan.
4. Commit completed work with the seat name and work-item ID.
5. Pull with rebase immediately before pushing, rerun affected checks, then push.
6. Never force-push, overwrite another seat's work, or resolve an ambiguous conflict automatically.

Verifier reports are stored in `handoffs/verifier/`. They contain the tested commit hash, exact commands, trimmed outputs, and the PASS or REJECT verdict.

## Workspace boundary

Keep the official `band-ai/dark-factory-wearedevs` repository beside this checkout, never inside it. Keep generated harness evidence in the sibling `checks/` directory so reference infrastructure and local artifacts cannot enter the judged repository.
