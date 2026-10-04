TASK · stage 1

Repository: https://github.com/b25cs1051-KUSH/VaultSync-pocketful (branch main). Every seat clones it into a folder named `run-<your seat>` next to its working directory and works only there.

Specification: copy E:\darkfactory\dark-factory-wearedevs\pocketful\spec\stage-1.md (machine A) verbatim to `stage-1/SPEC.md`. Build all of it.

Deliverable: `stage-1/` with the service source, a `Dockerfile` and a `RUN.md`, built and served from a clean container with no outbound network at runtime. Time box: dispatch + 3 hours 30 minutes.

Check commands (official check tool, use exactly these):
- Machine A (Architect, Watchdog, Verifier, Reserve Builder, Reserve Breaker): `wsl -d Ubuntu --cd /mnt/e/darkfactory/dark-factory-wearedevs -- /home/kush/.venvs/darkfactory/bin/python -m harness`
- Machine B (Builder, Breaker): `wsl -d Ubuntu --cd /mnt/d/HACKATHONS_/WAD_AMD/dark-factory-wearedevs -- .venv/bin/python -m harness`

Stage gate: `<check command> run --track pocketful --repo <your clone> --stage 1 --mode isolated` passes, plus everything `AGENTS.md` lists for a stage gate.

Seats (handles): Watchdog @pathakk1601/watchdog-1, Verifier @pathakk1601/verifier, Builder @jatinsingh6654/builder, Breaker @jatinsingh6654/breaker, Reserve Builder @pathakk1601/reserve-builder, Reserve Breaker @pathakk1601/reserve-breaker. All are already in this room.
