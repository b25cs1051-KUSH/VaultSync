# Stage 1 plan: Pocketful payments and settlements

Owner: Architect. Only the Architect edits this file.
Specification: `pocketful/spec/stage-1.md` (pasted in full into every handoff).
Official check (machine A): `wsl -d Ubuntu -- bash -lc ". ~/.venvs/darkfactory/bin/activate && cd /mnt/e/darkfactory/dark-factory-wearedevs && python -m harness run --track pocketful --repo <clone> --stage 1 --mode isolated"`
Official check (machine B): `wsl -d Ubuntu --cd /mnt/d/HACKATHONS_/WAD_AMD/dark-factory-wearedevs -- .venv/bin/python -m harness run --track pocketful --repo <clone> --stage 1`
Stage start: 2026-10-02T16:06+05:30. Readiness: Verifier, Builder, Breaker, Reserve Builder, Reserve Breaker all READY.

## Acceptance criteria

Each is checked by `curl` against the running container (`docker build -t pf1 stage-1 && docker run --rm -e PORT=9000 -p 9000:9000 pf1`) unless a command is named.

- AC1. The official check in isolated mode prints `claimed stage: 1` and every stage-1 test passes.
- AC2. `docker build stage-1` succeeds, and the container started with `-e PORT=<p>` answers `GET /health` with 200 `{"status":"ok"}` within 60 s, with no outbound network (isolated mode). Without `PORT` it listens on 8080. `RUN.md` holds one command that builds and starts it.
- AC3. `POST /_test/reset` with the §4 fixture returns 204, seeded users log in with their password, `GET /me` shows fixture balance, handle, currency and minor_units. A fixture with a negative balance returns 422 `validation_failed` and the previous state is unchanged. `settlement_operator_ids` defaults to `[]`.
- AC4. Signup/login follow §6 including derived handles (lowercase, `[^a-z0-9_]`→`_`, truncate 20), `email_taken`, `handle_taken` (no account created), short password and bad email 422, wrong credentials 401. Missing, malformed or unknown bearer token gives 401 `unauthenticated` on every authenticated endpoint.
- AC5. `POST /payments` follows §8: response shape including `settlement_id: null` and `request_id: null`, defaults, every error row, verbatim note round trip, atomic debit and credit.
- AC6. Requests: create (no balance check), pay (payer only, visibility choice, `request_not_pending`, `insufficient_funds` changes nothing), decline and cancel (idempotent on own terminal state, 409 on the other terminal states, 403 for the wrong party), `GET /requests` with direction, status, limit, offset, `has_more`, newest first, scoped to the two parties.
- AC7. Splits follow §8 and §9: shares in handle order with the remainder to the first participants, zero shares still produce requests, caller-only split gives `requests: []`, duplicate or empty list 422, unknown handle 404, no balance checks.
- AC8. `GET /activity` returns exactly the payments visible by the §4 feed contract, newest first, with limit, offset and `has_more`. Requests never appear.
- AC9. Idempotency on all five write paths follows §7: 400 missing key, 422 key over 255 characters, 201 first use, 200 identical replay, 409 reuse with a different body (including a now-invalid body), per-user scope, per-path scope, keys reusable after a 4xx, exactly one 201 under concurrent identical requests.
- AC10. Settlements follow §11: 401 without token, 403 non-operator, 1..32 transfers, entry errors in input order before funds, net affordability, all-or-nothing, failed validation claims no key, 201 with `settlement_id`, `committed_at`, member payments in input order with that `settlement_id` and `created_at == committed_at`, replay 200.
- AC11. Export and import follow §10: export shape, import replaces atomically and returns 204, tokens, passwords, idempotency receipts, operators, settlement membership survive, invalid input gives 422 and changes nothing, repeated import does not duplicate, reset clears imported state.
- AC12. Errors: every 4xx/5xx has `{"error":{"code","message"}}`. No 5xx under any input in the adversarial suite or under 50 concurrent requests.

## Invariants

- I1. Sum of all balances equals the total seeded by the last reset (or carried by the last import), at every observable moment, under concurrency and retries.
- I2. No balance is ever negative, including transiently. Settlements apply their net effect as one step.
- I3. A request moves money at most once, even with concurrent pays using different keys.
- I4. A claimed idempotency key for (user, method, path) yields exactly one effect. Concurrent identical first uses give one 201 and the rest 200 with the identical body. A request that ends in 4xx claims no key.
- I5. A payment is visible in both wallets or neither. A failed write leaves no trace (no payment, no request, no key, no id consumed visibly).
- I6. Reset and import replace state atomically. No request observes a mix of old and new state.
- I7. Within limits: 2 vCPU, 2 GiB, 50 in flight, 5 s per request, 10 s for reset/import/export. Password hashing must not make reset of a large fixture or bursts of logins exceed these limits.
- I8. Amount arithmetic is exact integer arithmetic for all values up to ±2^53.

## Requirements with no shipped test

The shipped sample suite never exercises these. They are mandatory.

- R1. `PORT` default 8080 and listening on 0.0.0.0. Health is 200 only when ready.
- R2. Timestamps are RFC 3339 with an explicit offset on every response (`created_at`, `committed_at`).
- R3. 401 `unauthenticated` for missing, malformed (`Bearer` absent, wrong scheme) and unknown tokens on every authenticated endpoint, including `/me`, `/activity`, `/requests`, `/settlements`.
- R4. Signup: 409 `email_taken`, 422 for password under 8 characters, 422 for email not `local@domain`. Login: 401 for wrong password. Multiple tokens per account stay valid together.
- R5. Passwords stored with a password-hashing function (bcrypt, scrypt, Argon2 or equivalent). Never plaintext, including inside export state.
- R6. Wrong JSON type of a field gives 400 `malformed_request` (for example `to_handle: 5`, `participant_handles: "ada"`), except the endpoint rules: amount wrong type or boolean 422, note non-string including null 422, visibility other than the two strings 422. A body that parses but is not a JSON object is 400.
- R7. Amount `1000.0` and `1e3` are valid integral amounts. `1000.5`, `"1000"`, `true`, `0`, `-1`, `1000000001` are 422.
- R8. `Idempotency-Key` of exactly 255 characters is accepted. Empty header is 400 `missing_idempotency_key`.
- R9. Idempotency for `POST /requests` and `POST /splits` (replay 200 identical body, reuse 409, concurrent identical first uses give one 201).
- R10. Replay after the resource changed (request cancelled or paid) still returns 200 with the original body and changes nothing.
- R11. A claimed key is resolved before field validation: same key with an invalid body is 409 `idempotency_key_reuse`.
- R12. Concurrent pays of one request with different keys: exactly one 201, others 409 `request_not_pending`, money moved once.
- R13. Decline twice is 200. Cancel twice is 200. Decline of paid or cancelled is 409 `request_not_pending`. Cancel of paid or declined is 409. Wrong party on decline or cancel is 403.
- R14. `GET /requests` unknown query parameters ignored, `limit=1e9`, `4.0`, `+4` are 422, `has_more` correct at page boundaries, newest first.
- R15. Seeded payments and seeded requests in every status appear correctly in feeds and request lists. Seeded records get server timestamps.
- R16. `GET /me` currency and minor_units for JPY (0) and BHD (3) fixtures. Reset with `minor_units` outside {0,2,3} is 422.
- R17. Settlements, all rules except the happy path: 401, 403, missing key 400, 0 or 33 transfers 422, non-array or non-object entries 422, unknown handle 404, self-transfer 422 `self_payment`, entry amount/note/visibility rules, first failing entry in input order decides the error, net affordability across chained transfers, 409 `insufficient_funds` with nothing changed, failed validation claims no key, replay 200, `settlement_id` null on non-member payments everywhere, member `created_at` equals `committed_at`, operator gets no extra visibility into private payments or others' requests.
- R18. Export/import, all rules except the single-payment round trip: `track` and `format_version` values, 422 for missing fields, wrong track, wrong version, invalid state, with destination unchanged, tokens valid after import, idempotent replays after import return the original response, failed keys still reusable, repeat import does not duplicate, import removes prior destination users and tokens, reset after import clears it, export is an atomic snapshot, operators and settlement membership preserved, malformed JSON 400.
- R19. Unicode and emoji notes round-trip byte for byte through activity, requests, splits and export/import. Note length counts characters (code points), not bytes.
- R20. 50 concurrent requests across many wallets (rings, partial drains) keep I1 and I2 and never 5xx.

## Work packages

States: PLANNED, ASSIGNED, IMPLEMENTED, ATTACKED, VERIFIED, ACCEPTED, REWORK.

### WP0 Adversarial suite (owner: Breaker) — IMPLEMENTED at fb53973ab4f082fa46c4416d44c3a8d776e42130
Depends on: nothing. Built from the specification, AC, invariants and R1–R20 only.
- S0.1 Suite skeleton runnable against a base URL. Done means: one command runs it and reports per-test results.
- S0.2 Tests for R1–R20 and I1–I8, including concurrency bursts of 50. Done means: committed under `stage-1/adversarial/`, each test names the R/I/AC id it covers.

### WP1 Foundation (owner: Builder) — ASSIGNED: S1.2 checkpoint ATTACK PASS + VERIFY PASS at db471c4a4aead6a456445f8c48983d690037ff5e (rework 1); S1.3 in progress
Depends on: nothing.
- S1.1 Service skeleton, Dockerfile, RUN.md, `PORT` handling, `GET /health`, JSON error envelope, body parsing (400 on unparseable or non-object). Done means: container builds and `/health` returns 200 in isolated mode.
- S1.2 **High-risk (data shape, shared state).** State store and `POST /_test/reset` with fixture validation (negative balance 422 changes nothing, minor_units), seeded users with hashed passwords, seeded payments and requests with server timestamps, operators. Done means: reset returns 204 and a second reset fully replaces state. **Checkpoint: hand off after this step.**
- S1.3 Signup, login, bearer auth, `GET /me`. Done means: AC3 and AC4 hold.

### WP2 Payments, idempotency, feed (owner: Builder) — PLANNED
Depends on: WP1.
- S2.1 **High-risk (concurrency, shared state).** Idempotency layer shared by all five write paths: per (user, method, path) key, canonical JSON body comparison, claim-before-validate ordering, concurrent identical first uses give one 201. Done means: AC9 holds for `POST /payments`. **Checkpoint.**
- S2.2 **High-risk (exact arithmetic, concurrency).** `POST /payments` with all validation rows and an atomic transfer. Done means: AC5 holds and 50 concurrent payments keep I1 and I2.
- S2.3 `GET /activity` with feed contract and paging. Done means: AC8 holds.

### WP3 Requests and splits (owner: Builder) — PLANNED
Depends on: WP2.
- S3.1 `POST /requests`, `POST /requests/{id}/pay` (I3 under concurrent pays), decline, cancel. Done means: AC6 write rows and R12, R13 hold.
- S3.2 `GET /requests` with filters and paging. Done means: AC6 list rows and R14 hold.
- S3.3 `POST /splits` with §9 shares. Done means: AC7 holds.

### WP4 Settlements (owner: Builder) — PLANNED
Depends on: WP2.
- S4.1 **High-risk (shared state, exact arithmetic).** `POST /settlements` with validation order, net affordability, single atomic commit, `settlement_id` on members and null elsewhere. Done means: AC10 and R17 hold.

### WP5 Export and import (owner: Builder) — PLANNED
Depends on: WP3, WP4.
- S5.1 **High-risk (persistence, data shape).** `GET /_test/export` and `POST /_test/import` with full-state round trip and validation. Done means: AC11 and R18 hold.

## Decision log

- D1 (assumption). Check order on every authenticated write: 401 auth, then 400 missing key, then 400 body parse/not an object, then 422 key length, then idempotency lookup (replay 200 or reuse 409), then field validation (400 wrong type, 422), then 404 unknown handle or resource, then 403 wrong party, then 409 state or funds. Reason: §7 fixes the key lookup after parse and auth and before validation. The rest is the most conservative order.
- D2 (assumption). A caller who is neither party of a request gets 403 `forbidden` on pay, decline and cancel, matching the per-endpoint tables. An id that does not exist is 404.
- D3 (assumption). Emails are compared case-insensitively for `email_taken` and login. The derived handle is computed from the lowercased local part as §4 states.
- D4 (assumption). Note length and the 200 limit count Unicode code points. Notes are stored and returned verbatim.
- D5 (assumption). `transfers` missing, not an array, empty, over 32 entries, or containing a non-object entry is 422 `validation_failed` (§11 "malformed batch shape"). Within entries, ordinary payment field rules apply (wrong-typed handle is 400 per §5).
- D6 (assumption). Fixture validation on reset: negative balance, `minor_units` outside {0,2,3}, or a body that is not a valid fixture object gives 422 `validation_failed` and changes nothing.
- D7. All five seats READY at stage start. WP0 assigned to Breaker, WP1 to Builder.
- D8. Builder push blocked by uncommitted Breaker files in the Builder working tree. Builder stages only its own paths and pulls with --autostash. Breaker works only in its own clone and commits under stage-1/adversarial/.
- D9. Adversarial suite lives at stage-1/adversarial/ (41 tests, run.py with BASE_URL), moved there by the Breaker at fb53973 in its own clone (VaultSync-breaker on machine B).
- D10. The stage specification is committed verbatim at stage-1/SPEC.md. Every handoff after the first names it with the exact revision, so every seat on either machine can open the complete text instead of receiving it split across many messages.
- D11. WP1 S1.2 at fd62c3c ATTACK FAIL: 25 resets + 25 health reads in flight drop connections (RemoteDisconnected). REWORK to Builder. Verification of fd62c3c stopped; the repaired commit is a new candidate.

## Constraints (verbatim from the task)

- "Build from the supplied requirements. Source code, API documentation and schemas from existing products in this domain must not be used."
- "Deliver an HTTP service, a `Dockerfile` and a `RUN.md` with a command that builds and starts the service without manual setup. Language, framework and storage are unrestricted. A `docker-compose.yml` is optional."
- "The image must run on its own with `-e PORT=<port>` and a port mapping. Runtime networking has no outbound access. All runtime dependencies, initialization and seed data must work within that single container. Compose configuration is not used to start the service."
- "Runtime assets and dependencies must be included in the image. This includes fonts, scripts and stylesheets; external services are unavailable at runtime."
- Resource limits: CPU 2 vCPU; Memory 2 GiB; start to first healthy response 60 s; up to 50 concurrent requests in flight; per-request timeout 5 s (10 s for `POST /_test/reset`); outbound network available during `docker build`, none at run time; disk ephemeral.
- "Passwords must be stored using a password-hashing function such as bcrypt, scrypt or Argon2, or an equivalent. Plaintext password storage is not permitted."
- "Requests must not produce 5xx responses, including under concurrent load."
- From the human task: stage 1 goes in `stage-1/` at the repository root, with source, a Dockerfile and RUN.md. It must build and serve from a clean container with no outbound network at runtime, and hold only stage 1's requirements. Build to the specification, not the sample checks. Do not start stage 2.
