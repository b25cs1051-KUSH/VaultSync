# VaultSync software factory

Status: Phase 1 environment scaffold. The reusable factory architecture is intentionally deferred to Phase 2 of the implementation plan.

## Purpose

This repository is the judged result artifact for the Pocketful track. The factory will coordinate four independent roles—architect, builder, breaker, and verifier—while preserving evidence of delegation, adversarial review, rejection, repair, and final verification.

## Current boundary

- Phase 0 requirements mapping is complete.
- Phase 1 local tooling and official harness setup are complete.
- The official challenge repository is maintained separately and pinned to revision `803560d2a678ace1414465c098eb0ab5380ffade`.
- No Pocketful implementation exists yet.
- Workflow design, handoff contracts, acceptance gates, and repair loops will be specified in Phase 2.

The stage directories are placeholders only. A stage is not runnable or complete until its later implementation phase supplies source code, a `Dockerfile`, and a `RUN.md` and passes the official harness.

## Current roles

- Architect: owns reusable system design and task decomposition.
- Builder: implements work authorized by an accepted handoff.
- Breaker: performs independent adversarial testing.
- Verifier: independently checks evidence and issues PASS or REJECT.

The authoritative generic role contracts are in `mandates/`.

## Evidence index

- Phase 0: `docs/phase-0-requirements-map.md`
- Phase 1: `docs/phase-1-environment-setup.md`
