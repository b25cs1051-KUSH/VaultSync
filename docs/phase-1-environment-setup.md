# Phase 1 — Local environment setup

Status: complete on 2026-10-01 (Asia/Calcutta).

This document records the reproducible environment created for Phase 1 of the implementation plan. It deliberately contains no Pocketful implementation.

## Canonical workspace layout

All collaborators should keep the reference/test infrastructure separate from the judged result repository:

```text
D:\HACKATHONS_\WAD_AMD\
├── dark-factory-wearedevs\   official reference and harness
├── VaultSync\                 shared submission repository
└── checks\                    uncommitted harness evidence
```

The matching WSL paths are:

```text
/mnt/d/HACKATHONS_/WAD_AMD/dark-factory-wearedevs
/mnt/d/HACKATHONS_/WAD_AMD/VaultSync
/mnt/d/HACKATHONS_/WAD_AMD/checks
```

The submission repository remains connected to `https://github.com/b25cs1051-KUSH/VaultSync.git`. The official repository is a separate checkout of `https://github.com/band-ai/dark-factory-wearedevs.git`, pinned in detached-HEAD state at `803560d2a678ace1414465c098eb0ab5380ffade`, the revision used for the Phase 0 requirements map.

## Verified toolchain

- WSL: 2.6.3.0, Ubuntu on WSL2, kernel 6.6.87.2-1.
- Python in WSL: 3.14.4 (satisfies the official Python 3.12+ requirement).
- Git in WSL: 2.53.0.
- Docker Desktop: 4.92.0 with Engine and CLI 29.8.0.
- Official harness dependencies: `httpx==0.28.1`, `playwright==1.63.0`, and `pytest==9.1.1`.
- Playwright Chromium: installed in WSL through the pinned harness environment.

Docker Desktop's Ubuntu integration was verified with both client and server reachable from `/usr/bin/docker` inside WSL2.

## Reproduce the harness environment

From PowerShell, clone the official package beside `VaultSync` and pin the audited revision:

```powershell
Set-Location D:\HACKATHONS_\WAD_AMD
git clone https://github.com/band-ai/dark-factory-wearedevs.git dark-factory-wearedevs
Set-Location dark-factory-wearedevs
git checkout 803560d2a678ace1414465c098eb0ab5380ffade
```

Then install the official dependencies inside Ubuntu WSL2:

```bash
cd /mnt/d/HACKATHONS_/WAD_AMD/dark-factory-wearedevs
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r harness/requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m harness --help
```

The final command displayed the official `run` and `check` subcommands.

## Docker verification

The official toy scaffold was used as the trivial container rather than introducing application code into the submission repository.

The following behaviors were verified from WSL2:

- built `scaffold/Dockerfile` as `vaultsync-phase1-smoke:803560d`;
- started a container from the image;
- mapped container port 8080 to `127.0.0.1:18080`;
- received `{"status":"ok"}` from `GET /health`;
- removed the temporary container after the check.

The retained image is harmless build cache and may be removed locally at any time. It is not part of the submission.

## Official harness verification

The official Stage 1 toy suite was run in grading-style isolated mode against the official scaffold:

```powershell
wsl -d Ubuntu --cd /mnt/d/HACKATHONS_/WAD_AMD/dark-factory-wearedevs -- `
  .venv/bin/python -m harness run `
  --track toy `
  --build scaffold `
  --stages 1 `
  --mode isolated `
  --out /mnt/d/HACKATHONS_/WAD_AMD/checks/phase1-toy-isolated-final-803560d
```

The harness completed normally and collected eight checks: two passed and six failed. That result is the official documented baseline for the intentionally incomplete scaffold, whose counter endpoints return `501 not_implemented`; it proves the Docker-backed harness runs without claiming that the toy is implemented. The completed report is stored locally at `checks/phase1-toy-isolated-final-803560d/report.json` outside the submission repository.

## Submission-repository scaffold

Phase 1 now provides:

- the existing `README.md`;
- a deliberately provisional `FACTORY.md`;
- all four generic mandates under `mandates/`;
- tracked placeholder directories `stage-1/` through `stage-4/`;
- a repository `.gitignore` that excludes local environments, secrets, caches, and harness output.

The stage placeholders intentionally contain no source code, `Dockerfile`, or `RUN.md`. Those files belong to the later stage implementation phases. `room.json` is likewise deferred until collaboration evidence is exported and sanitized. Therefore a full submission gate check is not expected to pass at Phase 1.

The official offline checker was still executed as a safety audit. It reported exactly nine expected pre-implementation gaps: `Dockerfile` and `RUN.md` are absent in each of four stages, and `room.json` is absent. It reported no additional mandate, layout, or credential problems.

## Completion evidence

- Official repo cloned separately: PASS.
- Result repo independently initialized and connected to its shared GitHub remote: PASS.
- Required result structure exists: PASS.
- Docker image build: PASS.
- Docker container startup: PASS.
- Required port exposure and health response: PASS.
- Docker available inside WSL2: PASS.
- Official harness CLI installation: PASS.
- Official toy harness execution in isolated mode: PASS (expected scaffold test baseline: 2 passed, 6 failed).
- Shared workspace paths documented for both Windows and WSL: PASS.

Phase 1 is complete. The next authorized activity in the implementation plan is Phase 2, factory architecture design—not Pocketful feature implementation.
