# Factory edge cases and failure test

The judged run is fully autonomous, so every failure we can foresee has to be handled by the factory itself. This file lists those failures, what the factory does about each one, and the test run that proves it. The results go into FACTORY.md.

## Seat layout

| Seat | Machine and account | Model | Role |
|---|---|---|---|
| Architect | A, Claude Pro | Opus | Plans, decides, accepts. Wakes only on events |
| Watchdog | A, Claude Pro | Haiku | Loops `tools/watch.ps1`. Wakes the Architect on silence or high usage |
| Verifier | A, Claude Pro | Sonnet | Package checks and the stage gate |
| Reserve Builder, Reserve Breaker | A, Claude Pro | Sonnet | Standby. Take over on failover. The Reserve Breaker can also verify |
| Builder | B, Codex | gpt-5.6-sol, medium effort | Builds |
| Breaker | B, Codex | lighter Codex model | Attacks |

A usage limit takes down every seat on that account at once. Codex does the heavy work (building and attacking), and Claude does the light work (planning, verifying, watching), so both 5-hour windows are used.

## How detection works

- **Claude usage:** `tools/watch.ps1` reads machine A's active 5-hour block from BAND (`band usage blocks --active`).
- **Codex usage:** every commit made through `tools/commit.ps1` carries a `Usage-Block: Codex <usd>` trailer read from machine B's BAND. The watch script reads the newest one from git.
- **Limits:** `tools/factory-limits.json` holds the size of each account's 5-hour block in BAND's USD estimate. It is set once by calibration (T0). Alerts fire at 85% and 95%.
- **Silence:** no commit on `origin/main` and no local seat activity for 30 minutes.
- **Watchdog alive:** the watch loop writes a heartbeat. The Architect checks it before ending any turn and sends `@Watchdog WAKE` if it is stale.

## Edge cases

| ID | Case | What the factory does |
|---|---|---|
| E1 | The Architect ends its turn while work is in flight (seen in the rehearsal) | It is allowed to sleep now. Every handoff @mentions the next seat, and finished work reaches the Architect. The Watchdog wakes it on silence |
| E2 | The Builder hits its Codex limit mid-step, silently | `ALERT SILENCE` after 30 min → the Architect pings → second `ALERT SILENCE` with no reply → reassigned to the Reserve Builder from the last pushed commit. About 60 min in total |
| E3 | The Breaker hits its Codex limit | Same as E2, failing over to the Reserve Breaker |
| E4 | Builder and Breaker go down together (one Codex account) | One DECISION reassigns both to their reserves |
| E5 | Codex is at 85% or 95% of its block | 85%: Codex seats finish their current step and take no new work, and the next package goes to the reserves. 95%: they stop now and their work is reassigned. This prevents E2 instead of reacting to it |
| E6 | Claude is at 85% or 95% of its block | 85%: no new packages; the package in flight finishes, then the stage gate runs. 95%: the stage stops as blocked, with a `Resume` section in `PLAN.md` |
| E7 | The Claude limit is actually hit (Architect, Watchdog, Verifier and reserves all go down) | Not recoverable autonomously. E6 makes the Architect close the stage before this happens. Accepted risk |
| E8 | A primary seat comes back after its reserve took over | The Architect tells it in one line that it is on standby. It takes only new work |
| E9 | A message fails to post, or a reply is staged and never sent | The seat retries once, then sends an `ERROR` line. If even that is lost, silence detection catches it |
| E10 | A seat replies without the @mention | The commit is still pushed. The Architect is woken by the next handoff or by `ALERT SILENCE` |
| E11 | Machine B sleeps, BAND closes or the network drops | Same as E2. Before every dispatch both machines are set to stay awake |
| E12 | Docker or the official check tool fails | One retry. If it fails on one machine only, a seat on the other machine runs the check. Otherwise the stage is blocked, with evidence |
| E13 | Push rejected or merge conflict | `pull --rebase`. An ambiguous conflict goes to the Architect |
| E14 | The Verifier is unavailable | The Reserve Breaker verifies any package it did not attack |
| E15 | The same package is REJECTED 3 times | Re-planned into smaller packages |
| E16 | Two seats share one working tree | Forbidden. Every seat has its own clone |
| E17 | The Architect continues into the next stage without a dispatch | It stops after the stage gate: final report, `@Watchdog STOP`, then nothing |
| E18 | The 5-hour window ends before the stage is done | Time box: at dispatch + 4h, no new packages and the gate runs on what is done |
| E19 | A seat's context is compacted | All state is in `PLAN.md`, `SPEC.md` and `handoffs/`. The seat re-reads those, not the room |
| E20 | The Watchdog stops looping | The Architect sees a stale heartbeat and sends `@Watchdog WAKE` |

## The test run

**Use a separate scratch repository and a new room.** The judged run must start from a fresh repository with clean history, so nothing from this test may land in it. A human may act during this test, because it is a test and not the judged run.

**Task:** the real stage-1 specification, cut down to its first package (users, login, reset). It is small enough to be cheap and real enough to measure M3 against the rehearsal, where the same package cost one checkpoint and one rework.

### T0. Calibration (humans, 10 min, before dispatch)
1. Both machines: open BAND, run `band usage blocks --active`, and note the USD figure. At the same moment, note the 5-hour % from the provider: claude.ai → Settings → Usage on machine A, and `/status` in Codex on machine B.
2. Block size = USD ÷ (% used / 100). Write both values into `tools/factory-limits.json` in the scratch repo.
3. Machine B: make a test commit with `tools/commit.ps1` and check that `git log -1` shows a `Usage-Block: Codex <number>` line, not `unknown`. If it shows `unknown`, BAND is not tracking Codex there, and E5 falls back to silence detection (E2).

### Test sequence (one dispatch)

| ID | When | Human action | Expected | What we learn |
|---|---|---|---|---|
| T1 | Dispatch | None | Readiness, `SPEC.md` and `PLAN.md`, `@Watchdog START`, Breaker suite, Builder package 1, one attack, one verify. All messages one line. The Architect sleeps between events | Happy path cost and time. M1, M2, M3, M5 and M8 working |
| T2 | When package 1 is verified, the Architect assigns package 2 | Jatin closes BAND on machine B | `ALERT SILENCE`, ping, second alert, DECISION, both reserves take over (E2, E4) | Failover works without a human, and how long it takes |
| T3 | After T2's DECISION | Jatin reopens BAND | The Builder and Breaker are told they are on standby. No duplicate work (E8) | Recovery rule |
| T4 | While the Verifier checks package 2 | Stop Docker Desktop on machine A for 2 minutes | Retry, or the check moves to machine B (E12) | Infrastructure failure handling |
| T5 | After package 2 is verified | Lower `claude_block_usd` in `factory-limits.json` so the current usage reads above 85% | `ALERT USAGE Claude 85%`, then the Architect runs the gate on what is done and does not start package 3 (E6) | Usage alert handling |
| T6 | After the final report | None for 15 min | `@Watchdog STOP`, no stage-2 work, silence (E17) | Clean stop |

### What we measure
After each test, record: wall time, `band usage agents` per seat (machine A), `band usage blocks --active` on both machines, number of room messages, and the rework count.

## Deciding on M3 (one review per package, no checkpoints)

The risk with M3 is that a defect a checkpoint would have caught early is caught late, after more code has been built on top of it, so the fix costs more.

Compare package 1 in this test with WP1 in the rehearsal:

| Outcome | Decision |
|---|---|
| Cost at most 70% of the rehearsal, and at most 1 rework round | Keep M3 |
| Cost lower, but 2 or more rework rounds, or a rework that touched more than the failing step | Partial M3: one checkpoint only for steps the Architect marks as shared state or concurrency |
| Cost not lower | Drop M3. Checkpoints were not the cost driver |

The test covers one package, so it is a signal, not proof. The stage gate's adversarial suite still runs in full whichever way we decide, so M3 never lowers what is checked before acceptance. It only changes when defects are found.
