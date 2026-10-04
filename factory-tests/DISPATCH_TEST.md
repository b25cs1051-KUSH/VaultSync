TASK (factory test run, not the judged run)

Repository: https://github.com/b25cs1051-KUSH/Vsultsync-scratch (branch main). Every seat clones it into a folder named `run-<your seat>` next to its working directory and works only there.

Specification: copy E:\darkfactory\dark-factory-wearedevs\pocketful\spec\stage-1.md (machine A) verbatim to `stage-1/SPEC.md`.

Scope for this run: only account creation, login, the current-user endpoint, and the test reset endpoint with fixture validation. Everything else in the specification is out of scope. Plan exactly two packages: package 1 is account creation, login and the current-user endpoint; package 2 is the test reset endpoint with fixture validation. Time box: dispatch + 3 hours.

Check commands (official check tool, use exactly these):
- Machine A (Architect, Watchdog, Verifier, Reserve Builder, Reserve Breaker): `wsl -d Ubuntu --cd /mnt/e/darkfactory/dark-factory-wearedevs -- /home/kush/.venvs/darkfactory/bin/python -m harness`
- Machine B (Builder, Breaker): `wsl -d Ubuntu --cd /mnt/d/HACKATHONS_/WAD_AMD/dark-factory-wearedevs -- .venv/bin/python -m harness`

Stage gate for this run: the official check in isolated mode for stage 1 with its pass count reported, plus every acceptance criterion inside the scope above. Tests outside the scope are expected to fail and do not block the gate.

Seats (handles): Watchdog @pathakk1601/watchdog, Verifier @pathakk1601/verifier, Builder @jatinsingh6654/builder, Breaker @jatinsingh6654/breaker, Reserve Builder @pathakk1601/reserve-builder, Reserve Breaker @pathakk1601/reserve-breaker. All are already in this room.
