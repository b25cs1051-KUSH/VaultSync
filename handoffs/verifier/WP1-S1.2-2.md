# WP1 S1.2 rework verification

Revision tested (code): `db471c4a4aead6a456445f8c48983d690037ff5e`
Specification/plan read at: tip of main at time of check (stage-1/SPEC.md, stage-1/PLAN.md AC2, AC3, AC12, I6, I7)
Clone: `E:\VaultSync-verifier`

## Diff from the rejected candidate

`git diff fd62c3c15a9907a3f843dcffc2bfe35540bb84f6 db471c4a4aead6a456445f8c48983d690037ff5e -- stage-1/server.py`
confirms the only code change is: a `PocketfulHTTPServer(ThreadingHTTPServer)` subclass with
`request_queue_size = 128` (listen backlog, up from the stdlib default of 5) and
`daemon_threads = True`, used in `main()` instead of the bare `ThreadingHTTPServer`. No other file
under `stage-1/server.py`'s runtime behavior changed. (The rest of the `main` diff vs. the first
checkpoint is unrelated history already merged — adversarial suite relocation, SPEC.md addition —
already verified.)

## Checks run

All run against `docker run --cpus 2 --memory 2g ...` per this handoff:

1. `docker build -t pf1-verify-rework stage-1` → succeeds.
2. Container with `-e PORT=9010`, `--cpus 2 --memory 2g` → `/health` 200 within 2s.
3. Container without `PORT` (default 8080), same limits → `/health` 200.
4. `POST /_test/reset` valid fixture → 204.
5. `POST /_test/reset` negative balance → 422 `validation_failed`; `/health` still 200 after.
6. `POST /_test/reset` with a JSON array body → 400 `malformed_request`.
7. `python -m unittest test_builder_foundation -v` → 4/4 pass (hashing, atomic replace-on-invalid, timestamps, concurrent-reader isolation) — unchanged from the first checkpoint, confirming the backlog/daemon-threads change didn't touch state-store logic.
8. **New, as named in this handoff:** `BASE_URL=http://127.0.0.1:9011 ADVERSARIAL_SEED=20261002 python -m unittest test_foundation_checkpoint -v` against a `--cpus 2 --memory 2g` container → `Ran 6 tests ... OK`, including:
   - `test_I6_I7_fifty_in_flight_resets_and_reads_never_5xx` — 50 concurrent reset/health calls, zero transport exceptions, all responses 200/204, none ≥500.
   - `test_R1_I7_fifty_health_requests_all_receive_200` — 50 concurrent `/health`, zero dropped/failed connections, all 200. **This is the specific case the Breaker's attack on `fd62c3c` found broken (dropped connections under 50 in flight); it now passes.**
   - `test_I7_large_fixture_reset_hashes_within_ten_seconds` — 200-user fixture reset in 1.82s (limit 10s).
   - `test_R16_AC3_D6_reset_validation_and_repeated_replacement`, `test_R6_AC12_unparseable_and_non_object_bodies_are_400_envelopes`, `test_R1_AC2_health_and_json_content_type` — all pass.
9. Sanity: full `stage-1/adversarial/run.py` (47 tests, the 41 original + 6 new) against the same resource-limited container → `Ran 47 tests ... FAILED (failures=40)`. All 40 failures are still exactly the `self.login` 404 (S1.3 not built, same as the first checkpoint) — verified by the same `awk` filter used in the prior report, zero non-login failures. No regression from the backlog change.

## Verdict: PASS

Commands and trimmed output:
```
$ docker build -t pf1-verify-rework stage-1
...naming to docker.io/library/pf1-verify-rework:latest done

$ docker run -d --rm --cpus 2 --memory 2g -e PORT=9010 -p 9010:9010 pf1-verify-rework
$ curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9010/health
200

$ cd stage-1/adversarial && BASE_URL=http://127.0.0.1:9011 ADVERSARIAL_SEED=20261002 \
  python -m unittest test_foundation_checkpoint -v
test_I6_I7_fifty_in_flight_resets_and_reads_never_5xx ... ok
test_I7_large_fixture_reset_hashes_within_ten_seconds ... ok
test_R16_AC3_D6_reset_validation_and_repeated_replacement ... ok
test_R1_AC2_health_and_json_content_type ... ok
test_R1_I7_fifty_health_requests_all_receive_200 ... ok
test_R6_AC12_unparseable_and_non_object_bodies_are_400_envelopes ... ok
Ran 6 tests in 4.817s
OK
LARGE_RESET_SECONDS=1.820

$ python run.py   # full 47-test suite, same container
Ran 47 tests in 6.378s
FAILED (failures=40)   # all 40 still only missing-/auth/login; 0 regressions
```

## Open risks

- Same as the first checkpoint report (handoffs/verifier/WP1-S1.2-1.md): auth/`GET /me`/payments/etc. are unbuilt (S1.3 onward), and there's still no HTTP-observable way to confirm full state replacement beyond the Builder's unit tests + code read, until a read endpoint exists.
- The backlog fix (`request_queue_size=128`) addresses listen-queue overflow; it was not re-tested at higher concurrency than 50 (the documented limit) or under sustained/repeated bursts beyond the single 50-in-flight test runs above.
