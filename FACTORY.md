# VaultSync software factory

Status: Phase 2 architecture defined. Detailed handoff protocols and final mandate authoring remain deferred to their later plan phases.

## Purpose

This repository is the judged result artifact for the Pocketful track. The factory will coordinate four independent roles—architect, builder, breaker, and verifier—while preserving evidence of delegation, adversarial review, rejection, repair, and final verification.

## Current boundary

- Phase 0 requirements mapping is complete.
- Phase 1 local tooling and official harness setup are complete.
- Phase 2 factory roles, authority boundaries, lifecycle, and quality gates are defined in `docs/phase-2-factory-architecture.md`.
- The official challenge repository is maintained separately and pinned to revision `803560d2a678ace1414465c098eb0ab5380ffade`.
- No Pocketful implementation exists yet.
- Detailed communication, handoff, rejection, and rework message formats remain deferred to Phase 3.
- Existing mandate files remain provisional until they are reconciled with the approved architecture and handoff protocol in Phase 4.

The stage directories are placeholders only. A stage is not runnable or complete until its later implementation phase supplies source code, a `Dockerfile`, and a `RUN.md` and passes the official harness.

## Current roles

- Architect: owns reusable system design and task decomposition.
- Builder: implements work authorized by an accepted handoff.
- Breaker: performs independent adversarial testing.
- Verifier: independently checks evidence and issues PASS or REJECT.

The authoritative generic role contracts are in `mandates/`.

The architecture is authoritative for role boundaries and decision rights. Until the Phase 4 reconciliation is complete, any conflict between a provisional mandate and the architecture must be escalated rather than guessed.

## Evidence index

- Phase 0: `docs/phase-0-requirements-map.md`
- Phase 1: `docs/phase-1-environment-setup.md`
- Phase 2: `docs/phase-2-factory-architecture.md`
