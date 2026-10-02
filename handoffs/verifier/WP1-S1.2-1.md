# WP1 S1.2 checkpoint verification

Revision tested (code): `fd62c3c15a9907a3f843dcffc2bfe35540bb84f6`
Specification/plan read at: `4ac41617d6a884c548d4634ad861c1327de01974` (stage-1/SPEC.md, stage-1/PLAN.md)
Clone: `E:\VaultSync-verifier`

## Scope

S1.2 done means: container builds and `/health` returns 200 with no outbound network; reset
returns 204 and a second reset fully replaces state. Auth/`GET /me` (S1.3) are not yet built and
are out of scope for this checkpoint, per the handoff.

## Checks run

1. `docker build -t pf1-verify stage-1` → succeeds (python:3.13-slim base, no extra deps).
2. `docker run -e PORT=9001 -p 9001:9001 pf1-verify` → `GET /health` → `200 {"status":"ok"}`.
3. `docker run -p 8080:8080 pf1-verify` (no `PORT`) → `GET /health` on 8080 → `200 {"status":"ok"}`.
4. `RUN.md` command verbatim (`docker build -t pocketful-stage-1 stage-1 && docker run --rm -e PORT=9000 -p 9000:9000 pocketful-stage-1`) → builds and serves `/health` 200.
5. `POST /_test/reset` with the §4 fixture (2 users, 1 payment, 1 request) → `204`, empty body.
6. Second `POST /_test/reset` with a different user set → `204` (full replacement; see code-level confirmation below, since no state-reading endpoint exists yet at this checkpoint).
7. `POST /_test/reset` with `balance: -1` → `422 {"error":{"code":"validation_failed","message":"user.balance is out of range"}}`; `GET /health` still `200` afterward (no crash).
8. `POST /_test/reset` with `minor_units: 1` → `422 validation_failed`.
9. `POST /_test/reset` with a JSON array body (non-object) → `400 malformed_request`.
10. `python -m unittest stage-1.tests.test_builder_foundation -v` (Builder's own tests, run directly against `server.py`) → `Ran 4 tests ... OK`. These four tests directly assert: passwords are hashed (`password_hash` present, raw password absent, `password_matches` verifies), a second reset fully replaces state (old user gone, new balance present, operators reset to `[]`), seeded payments/requests get RFC3339-with-offset `created_at`, and concurrent readers during a reset only ever observe one complete state or the other, never a mix.
11. `stage-1/tests/adversarial/run.py` (full 41-test suite) against the running container: `Ran 41 tests ... FAILED (failures=40)`. The one pass is `test_smoke.SmokeTests.test_R1_AC2_health_ready_contract`. All 40 failures are `AssertionError: 200 != 404` inside `ApiTestCase.setUp` → `self.login(...)`, i.e. every one fails because `POST /auth/login` is 404 (not built — S1.3). Verified mechanically: `grep -c "^FAIL:"` = 40, and every FAIL block's traceback is the `self.login` assertion — none is a reset/password/state assertion. No 5xx appeared anywhere in the run.
12. Code read of `server.py`: `password_hash` uses `hashlib.scrypt` (n=4096, r=8, p=1) with a random 16-byte salt, stored as `scrypt$n$r$p$salt$digest`; the raw password is never retained on the user record. `StateStore.replace_from_fixture` calls `build_reset_state(fixture)` (which raises `RequestError` on any invalid field) and only swaps `self._state` under the lock *after* `build_reset_state` returns successfully — so a 422 from reset provably cannot have mutated the store (confirmed behaviorally by item 10's `test_invalid_fixture_does_not_change_state`).

## Verdict: PASS

Commands and trimmed output:
```
$ docker build -t pf1-verify stage-1
...naming to docker.io/library/pf1-verify:latest done

$ curl -s -o - -w "\n%{http_code}" http://127.0.0.1:9001/health
{"status":"ok"}
200

$ curl -s -X POST http://127.0.0.1:9002/_test/reset -d '{...valid fixture...}' -w "\n%{http_code}"
204

$ curl -s -X POST http://127.0.0.1:9002/_test/reset -d '{...balance:-1...}' -w "\n%{http_code}"
{"error":{"code":"validation_failed","message":"user.balance is out of range"}}
422

$ cd stage-1/tests && python -m unittest test_builder_foundation -v
Ran 4 tests in 0.146s
OK

$ BASE_URL=http://127.0.0.1:9005 python stage-1/tests/adversarial/run.py
Ran 41 tests in 2.806s
FAILED (failures=40)   # all 40 are missing-/auth/login (S1.3), 0 are reset/password/state related
```

## Open risks

- Auth, `GET /me`, payments, requests, splits, settlements, export/import are entirely unbuilt (S1.3 onward) — expected at this checkpoint, not a defect of S1.2.
- No HTTP-observable way exists yet to confirm "second reset fully replaces state" from outside the process (no read endpoint until S1.3+); that claim rests on the Builder's own unit tests (item 10) plus code inspection (item 12), both reproduced here. Re-verify behaviorally via `GET /me`/export once those endpoints exist.
- `_read_json_object` caps body size at 16 MiB; not a spec requirement, not tested, low risk.
