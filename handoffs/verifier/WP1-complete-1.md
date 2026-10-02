# WP1 package verification (S1.1 + S1.2 + S1.3 complete)

Revision tested (code): `d89cfb05f7f9b3828615076473b77ecafbbe6580`
Specification/plan read at: `stage-1/SPEC.md`, `stage-1/PLAN.md` at that revision (D10 verbatim spec)
Named scope: AC2, AC3, AC4, R1, R3, R4, R5, R16, I6, I7, D1, D3, D6
Clone: `E:\VaultSync-verifier`

## Code review (server.py diff since the S1.2 rework PASS at db471c4a)

`git diff db471c4a..d89cfb0 -- stage-1/server.py` adds: `derive_handle`, `required_body_string`,
`_validate_auth_body`, `StateStore.signup/login/authenticate`, and the `/auth/signup`, `/auth/login`,
`GET /me` routes. Read in full. Key points verified by inspection, then confirmed black-box below:

- `signup`/`login`/`authenticate` all run under `StateStore.lock`; `login` releases the lock during
  the expensive `password_matches` scrypt verify and re-checks the *current* `self._state` afterward
  before minting a token — so a reset racing a login cannot hand out a token against stale
  credentials (I6), and doesn't serialize slow hashing behind the single lock (I7).
- `build_reset_state` always resets `"tokens": {}` on every reset, so a reset atomically invalidates
  every previously issued token with no separate revocation step (AC3 "old tokens 401").
- `derive_handle` matches §4 exactly: lowercase local part, `[^a-z0-9_]`→`_`, truncate 20 (D3).
- `required_body_string` gives 422 for a missing field, 400 `malformed_request` for the wrong JSON
  type — matching R6's general rule (email/password aren't in the amount/note/visibility carve-out).
- `do_GET`/`do_POST` call `_authenticated_user()` before the final 404 fall-through for any path
  outside the public list, so unauthenticated calls to not-yet-built endpoints (`/activity`,
  `/requests`, `/settlements`, `/payments`) already return 401 rather than 404 (R3), ahead of WP2+.

## Checks run

1. `docker build -t pf1-wp1-complete stage-1` → succeeds.
2. `python -m unittest test_builder_foundation -v` (stage-1/tests) → 6/6 pass, including the two new
   tests: case-insensitive login/signup with multiple distinct tokens + correct derived handle +
   `balance: 0`, and atomic email_taken/handle_taken (state unchanged on either conflict).
3. Container run `--cpus 2 --memory 2g -e PORT=9020`: `/health` 200; without `PORT` → 8080 → 200.
4. AC3: reset with 2 seeded users → 204; seeded login → 200 with token; `GET /me` → exact fixture
   balance/handle/currency/minor_units.
5. **New external check named in this handoff** — second reset fully replaces state, observed through
   `/me`/login (no read endpoint existed at the prior checkpoint):
   - Old user (`ada`) login after a second reset seeding only `cy` → `401 unauthenticated`.
   - Old token (minted before the second reset) on `GET /me` → `401 unauthenticated` (`Invalid bearer token`).
   - New user (`cy`) logs in and reads `/me` → 200, correct balance.
6. **New external check** — invalid reset preserves state and tokens: with `cy` logged in, a
   negative-balance reset and a `minor_units: 1` reset both → 422 `validation_failed`; `cy`'s existing
   token still returns 200 on `/me` with the unchanged balance, and `cy` can still log in afterward.
7. AC4: signup → 201 with derived handle; duplicate email (case-insensitive) → 409 `email_taken`;
   signup whose derived handle collides with a seeded handle → 409 `handle_taken`; password under 8
   chars → 422; malformed email → 422; login wrong password → 401; login unknown email → 401.
8. R3: `/me` with no `Authorization` → 401; `Authorization: Basic ...` → 401; unknown bearer token →
   401; unauthenticated `GET /activity` (not yet implemented) → 401, not 404.
9. R16: reset with `JPY`/`minor_units:0` and `BHD`/`minor_units:3` → `GET /me` reports the correct
   currency and minor_units in both cases.
10. R4: two concurrent logins for the same account → two distinct tokens, both independently valid on `/me`.
11. Password hash never appears in any response body (`/me`, signup, login) — grepped, zero matches.
12. Full `stage-1/adversarial/run.py` (47 tests) against the live container: `Ran 47 tests ...
    FAILED (failures=30, errors=7)`. Every one of the 37 failing/erroring tests calls an endpoint from
    WP2–WP5 (`/payments`, `/requests`, `/splits`, `/settlements`, `/_test/export`, `/_test/import`) —
    confirmed by reading each failing test body, e.g. `test_R5_password_never_plaintext_in_export`
    fails only because `GET /_test/export` 404s (R5 itself is independently confirmed by item 11 and
    code review), `test_R2_timestamps_have_explicit_offsets` needs `/payments` and `/settlements`.
    Every test tagged to the named scope (R1, R3, R4, R16, AC2, AC3, AC4, parts of AC12, I7) passed:
    `test_R1_AC2_health_ready_contract`, `test_R3_AC4_unauthenticated_all_protected_endpoint_families`,
    `test_R4_AC4_signup_login_handle_and_credential_boundaries`,
    `test_R4_derived_handle_lowercase_substitute_and_truncate`,
    `test_R16_AC3_currency_minor_units_and_invalid_reset_is_atomic`,
    `test_AC12_every_exercised_error_has_code_and_message`,
    `test_I7_fifty_logins_and_large_reset_stay_within_contract_timeouts`, plus all 6
    `test_foundation_checkpoint` and the `test_smoke` health test. No 5xx anywhere.
13. Breaker's new `test_auth_checkpoint.py` (commit `233a489`, adversarial-only — `git diff d89cfb0
    233a489 --stat` touches only `stage-1/adversarial/test_auth_checkpoint.py` and `PLAN.md`, no
    server code) run against the same `d89cfb0` container: `Ran 4 tests ... OK` — 50-way concurrent
    duplicate signup creates exactly one account, 50 concurrent logins mint 50 distinct valid tokens,
    reset racing 49 concurrent `/me` reads never observes mixed state, and auth body type/length
    boundaries hold.

## Verdict: PASS

Commands and trimmed output:
```
$ docker build -t pf1-wp1-complete stage-1 → naming to ...pf1-wp1-complete:latest done

$ cd stage-1/tests && python -m unittest test_builder_foundation -v
Ran 6 tests in 0.257s
OK

$ curl -X POST .../_test/reset -d '{...2 users...}' -w "%{http_code}"  → 204
$ curl .../me -H "Authorization: Bearer $TOKEN1" → 200 {"user_id":"u_ada",...}

$ curl -X POST .../_test/reset -d '{...only cy...}' → 204
$ curl -X POST .../auth/login -d '{"email":"ada@example.com",...}' → 401 unauthenticated
$ curl .../me -H "Authorization: Bearer $TOKEN1" (pre-reset token) → 401 "Invalid bearer token"

$ curl -X POST .../_test/reset -d '{...balance:-1...}' → 422 validation_failed
$ curl .../me -H "Authorization: Bearer $TOKEN_CY" (unaffected) → 200, balance unchanged

$ BASE_URL=... python run.py   # full 47-test suite
Ran 47 tests in 13.854s
FAILED (failures=30, errors=7)   # all 37 need WP2-WP5 endpoints; 0 regressions in named scope

$ BASE_URL=... python -m unittest test_auth_checkpoint -v   # Breaker's new concurrency attacks
Ran 4 tests in 3.447s
OK
```

## Open risks

- WP2–WP5 (payments, requests, splits, settlements, export/import) are unbuilt; the 37 adversarial
  failures above are expected at this point in the plan and are not part of this package's scope.
- R5's "never plaintext in export" is confirmed by code review and black-box inspection of every
  current response (item 11), not by the export endpoint itself — that endpoint doesn't exist until
  WP5 and must be re-checked against R5/R18 then.
- Scrypt hashing runs synchronously inside the handler thread; under 50 concurrent signups the listen
  backlog/thread-per-connection model (`request_queue_size=128`, `daemon_threads=True`) was exercised
  by the Breaker's 50-way concurrent signup/login tests (item 13) with no failures, but sustained load
  beyond the documented 50-in-flight limit was not tested here.
