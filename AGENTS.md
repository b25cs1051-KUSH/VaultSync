# Factory protocol (every seat follows this)

This file is the factory's shared protocol. Each seat's own mandate in `mandates/` adds its role. If the two conflict, the mandate wins for that seat's role, and this file wins for everything shared.

## 1. Single source of truth

Use these, in this order, and nothing else:

1. **Requirements:** the task and specification text pasted into your handoff. The specification beats any sample check, plan or habit.
2. **Decisions, scope and state:** `stage-N/PLAN.md` for the active stage, owned by the Architect. It holds acceptance criteria, invariants, work packages with their states, and a decision log.
3. **Code and evidence:** `origin/main` of this repository.

If something is unclear, missing or contradictory, ask the **Architect** in the room with one precise question and the options you see. The Architect answers from the specification, records the answer in the decision log, and that answer is binding. No seat ever asks the human, and no seat waits for a human reply. If even the Architect cannot resolve a point, the Architect picks the most conservative reading the specification allows, records it as an assumption, and work continues.

## 2. Work packages and steps

- The Architect assigns **work packages**. A package has one owner, a stage, and an ordered list of **steps**; each step has one observable "done means". A long package is fine if its steps are simple.
- The owner does the steps **in order, one at a time**: complete the step, run its own quick check, commit with the step id in the subject, then start the next step. Never work on several steps at once.
- Cross-seat review happens **once per package**, after the last step: one attack, then one verification. There are no mid-package checkpoints; checkpoint marks in an existing plan are ignored.
- Steps that touch shared state, concurrency, exact arithmetic, persistence or data shape get extra tests from their owner before the next step starts.
- Packages run in dependency order. Do not start a package before the ones it depends on are verified.

## 3. Readiness before any work

The Architect's readiness request gives each seat the exact check command for its machine. Pull the shared repository, run exactly that command with `--help`, and nothing else: do not search for tools and do not start background tasks. Then reply to the Architect, @mentioning it:
```
READY · <seat> · Harness <name> · Model <id> · pull OK · check tool OK
```
If either step fails, reply `NOT READY` with the error. Work starts when the Verifier, Builder and Breaker are all READY; reserves reply too, but do not block the start.

## 3a. Errors

If a command, tool or check fails in a way you cannot fix yourself, send the Architect one line: `ERROR · <seat> · <what failed> · can I continue: yes/no`. If your own message or reply fails to post, retry once, then report it. Never assume a failed message was delivered.

## 4. Lifecycle

`PLANNED → ASSIGNED → IMPLEMENTED → ATTACKED → VERIFIED → ACCEPTED`, with `REWORK` from ATTACKED or VERIFIED back to ASSIGNED. A repaired commit is a new candidate: earlier attack and verification results do not carry over to it. A REJECT is binding. Only the Architect records ACCEPTED, and only after a Verifier PASS on that exact revision. No seat ever attacks or verifies work it built.

## 5. Effort matches risk

- **Package check (every package and every high-risk checkpoint):** the owner's own tests, the relevant adversarial tests, and the checks the package names. Keep it short.
- **Stage gate (end of every stage):** the full official check in isolated mode, every adversarial suite, every earlier stage's checks, and a line-by-line pass over the stage specification against the list of requirements with no shipped test.
- Spend tokens on hard parts, not easy ones. Do not re-read files you do not need. Do not restate unchanged code.

## 6. Handoffs and evidence

- The Architect commits the complete specification text for the stage to `stage-N/SPEC.md` once. Every handoff names the package, the shared repository and the exact revision, and points to `stage-N/SPEC.md` and `stage-N/PLAN.md` instead of repeating them. Never point at an earlier message.
- Every claim carries evidence: the exact commands run and their trimmed output, with the full commit hash. A claim without evidence is false.
- @mention only the seat that must act next. Do not send acknowledgements, thanks or status updates. If a message needs nothing from you, do not reply.

## 7. Stages

- Stage N lives in `stage-N/` with its source, a `Dockerfile` and a `RUN.md`. It builds and serves from a clean container and needs no outbound network at runtime.
- When stage N is accepted, copy `stage-N/` to `stage-(N+1)/` (without any nested `.git`) and extend the copy. Each folder holds only its own stage's requirements, and must keep passing every earlier stage.
- **Build to the specification, not to the tests.** The shipped tests are only part of what is graded; hidden tests check other requirements written in the specification. Passing the shipped tests is the start, not the finish. Never write code that recognises a particular test input and returns the answer that test expects.

## 8. Git

- `origin/main` is shared. Before work and before every push: clean tree, `git pull --rebase origin main`, re-run affected checks.
- Commit only files you own or were assigned, under your own seat identity, with the package and step id in the subject.
- Never force-push, amend or rewrite published history, or commit credentials. On an ambiguous conflict, stop that package and tell the Architect with the conflicting paths.
