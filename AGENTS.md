# Factory protocol (every seat follows this)

This file is the factory's shared protocol. Each seat's own mandate in `mandates/` adds its role. If the two conflict, the mandate wins for that seat's role, and this file wins for everything shared.

## 1. Single source of truth

Use these, in this order, and nothing else:

1. **Requirements:** `stage-N/SPEC.md`, the complete stage specification committed verbatim by the Architect. It beats any sample check, plan or habit.
2. **Decisions, scope and state:** `stage-N/PLAN.md`, owned by the Architect: acceptance criteria, invariants, work packages with their states, and a decision log.
3. **Code and evidence:** `origin/main` of this repository.

Read `SPEC.md` once per stage and re-read only the sections your work needs. If your context was compacted or you were just reassigned, re-read `PLAN.md` and the relevant parts of `SPEC.md`, not the room history.

If something is unclear, missing or contradictory, ask the **Architect** one precise question with the options you see. Its answer is recorded in the decision log and is binding. No seat ever asks the human or waits for a human reply. If even the Architect cannot resolve a point, it picks the most conservative reading the specification allows, records it as an assumption, and work continues.

## 2. Work packages and steps

- The Architect splits a stage into **at most three work packages** unless the specification clearly needs more. A package has one owner and an ordered list of **steps**, each with one observable "done means".
- The owner does the steps **in order, one at a time**: complete the step, run its quick check, commit, then start the next. Steps that touch shared state, concurrency, exact arithmetic, persistence or data shape get extra tests from their owner before the next step starts.
- Review happens **once per package**, after its last step: one attack, then one verification. There are no mid-package checkpoints.
- Packages run in dependency order. Do not start a package before the ones it depends on are verified.

## 3. Readiness (first stage of a run only)

The Architect's readiness request gives each seat the exact check command for its machine. Pull, run exactly that command with `--help`, and nothing else: do not search for tools and do not start background tasks. Reply to the Architect, @mentioning it, with one line:
```
READY · <seat> · <harness> · <model>
```
or `NOT READY · <seat> · <error>`. Work starts when the Verifier, Builder and Breaker are READY. Later stages skip readiness; a seat that does not respond is handled by failover.

## 4. Messages: one line, evidence in files

- Every room message is **one line** in the formats your mandate gives, and @mentions only the seat that must act next. No greetings, acknowledgements, summaries, restated specifications or pasted output.
- Evidence (commands run, trimmed output, exit codes) goes into a committed file under `handoffs/<seat>/`, and the message names that file and the full commit hash. A claim without evidence in a committed file is false.
- If a message needs nothing from you, do not reply.
- If a command, tool or check fails in a way you cannot fix, send the Architect: `ERROR · <seat> · <what failed> · can I continue: yes/no`. If your own message fails to post, retry once, then report it.

## 5. Lifecycle

`PLANNED → ASSIGNED → IMPLEMENTED → ATTACKED → VERIFIED → ACCEPTED`, with `REWORK` from ATTACKED or VERIFIED back to ASSIGNED. A repaired commit is a new candidate: earlier attack and verification results do not carry over. A REJECT is binding. Only the Architect records ACCEPTED, and only after a Verifier PASS on that exact revision. No seat ever attacks or verifies work it built.

## 6. Effort matches risk

- **Package check:** the owner's tests and the adversarial tests relevant to the package, run locally. Keep it short.
- **Stage gate (once, at the end of the stage):** the official check command in isolated mode, every adversarial suite, every earlier stage's checks, and a pass over `SPEC.md` against the list of requirements with no shipped test.
- Do not re-read files you do not need. Do not restate unchanged code. Spend tokens on hard parts.

## 7. Stages

- Stage N lives in `stage-N/` with its source, a `Dockerfile` and a `RUN.md`. It builds and serves from a clean container and needs no outbound network at runtime.
- A new stage starts only when its task is dispatched. Its first work is copying the accepted `stage-(N-1)/` to `stage-N/` without any nested `.git`. Each folder holds only its own stage's requirements and must keep passing every earlier stage.
- **Build to the specification, not to the tests.** The shipped tests are only part of what is graded; other tests check other requirements in the specification. Never write code that recognises a particular test input and returns the answer that test expects.

## 8. Git

- `origin/main` is shared. Every seat works in **its own clone**, never a working tree shared with another seat.
- Before work and before every push: clean tree, `git pull --rebase origin main`, re-run affected checks.
- Commit only files you own or were assigned (stage them with `git add`), with the package and step id in the subject, using the commit script so your seat identity and usage are recorded:
  `powershell -NoProfile -ExecutionPolicy Bypass -File tools/commit.ps1 -Seat "<seat name>" -Harness "<harness>" -Subject "<subject>"`
- Never force-push, amend or rewrite published history, or commit credentials. On an ambiguous conflict, stop that package and tell the Architect with the conflicting paths.
