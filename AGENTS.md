# Factory protocol (every seat follows this)

This file is the factory's shared protocol. Each seat's own mandate in `mandates/` adds its role. If the two conflict, the mandate wins for that seat's role, and this file wins for everything shared.

## 1. Single source of truth

Use these, in this order, and nothing else:

1. **Requirements:** the task and specification text pasted into your handoff. The specification beats any sample check, plan or habit.
2. **Decisions, scope and state:** `stage-N/PLAN.md` for the active stage, owned by the Architect. It holds acceptance criteria, invariants, work items with their states, and a decision log.
3. **Code and evidence:** `origin/main` of this repository.

If something is unclear, missing or contradictory, ask the **Architect** in the room with one precise question and the options you see. The Architect answers from the specification, records the answer in the decision log, and that answer is binding. No seat ever asks the human, and no seat waits for a human reply. If even the Architect cannot resolve a point, the Architect picks the most conservative reading the specification allows, records it as an assumption, and work continues.

## 2. Work items

- The Architect splits each stage into work items. Each item has one concern, one owner, one observable "done means", and the stage it belongs to.
- **Size by severity.** Small: one file or one behaviour. Medium: a few files, one feature. Large: anything touching shared state, concurrency, exact arithmetic, persistence, or more than one feature. **Large items are split before assignment.** No item should need more than one focused session to finish.
- Build in dependency order, one item at a time per owner. Do not start a later item before the earlier one it depends on is verified.

## 3. Lifecycle

`PLANNED → ASSIGNED → IMPLEMENTED → ATTACKED → VERIFIED → ACCEPTED`, with `REWORK` from ATTACKED or VERIFIED back to ASSIGNED. A repaired commit is a new candidate: earlier attack and verification results do not carry over to it. A REJECT is binding. Only the Architect records ACCEPTED, and only after a Verifier PASS on that exact revision.

## 4. Effort matches risk

- **Item check (every item):** the owner's own tests, the relevant adversarial tests, and the checks the item names. Keep it short.
- **Stage gate (end of every stage):** the full official check in isolated mode, every adversarial suite, every earlier stage's checks, and a line-by-line pass over the stage specification for requirements no sample check covers.
- Spend tokens on hard parts, not easy ones. Do not re-read files you do not need. Do not restate unchanged code.

## 5. Handoffs and evidence

- Every delegated handoff contains the complete task and the complete specification text for the stage, plus the work item, the shared repository and the exact revision. Never point at an earlier message. Split long handoffs into numbered messages.
- Every claim carries evidence: the exact commands run and their trimmed output, with the full commit hash. A claim without evidence is false.
- @mention only the seat that must act next. Do not send acknowledgements, thanks or status updates. If a message needs nothing from you, do not reply.

## 6. Stages

- Stage N lives in `stage-N/` with its source, a `Dockerfile` and a `RUN.md`. It builds and serves from a clean container and needs no outbound network at runtime.
- When stage N is accepted, copy `stage-N/` to `stage-(N+1)/` (without any nested `.git`) and extend the copy. Each folder holds only its own stage's requirements, and must keep passing every earlier stage.
- Build to the specification, never to the sample checks. Never special-case a known check input.

## 7. Git

- `origin/main` is shared. Before work and before every push: clean tree, `git pull --rebase origin main`, re-run affected checks.
- Commit only files you own or were assigned, under your own seat identity, with the work item in the subject.
- Never force-push, amend or rewrite published history, or commit credentials. On an ambiguous conflict, stop that item and tell the Architect with the conflicting paths.
