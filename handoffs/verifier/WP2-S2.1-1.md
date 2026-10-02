# WP2 S2.1 high-risk checkpoint verification

Revision tested (code): `a0e6d84b8b97cdd401f6222ce1b6234251fc3d88`
Specification: `stage-1/SPEC.md` §7 (verbatim, D10)
Named scope: AC9, I4, I5, R8, R10, R11, D1 — shared idempotency layer observable through `POST /payments` (full payment validation is S2.2, out of scope).
Clone: `E:\VaultSync-verifier`

## Code review

`git diff d89cfb0..a0e6d84 -- stage-1/server.py` adds `canonical_json`/`_normalize_json_value`
(sorts keys, collapses integral floats to int so `1000`/`1000.0`/`1e3` compare equal as the same
parsed JSON value — correct, since JSON itself has only one numeric type), `StateStore.execute_idempotent`
(generic per `(user_id, method, path, key)` scope) and `create_payment_idempotent` built on it, plus
minimal `_create_payment` field handling and the `/payments` route wiring.

- `execute_idempotent` holds `self.lock` for the full claim-check-and-execute: it re-validates the
  token is still bound to `user_id` (defends a reset race), looks up `previous` by scope, returns
  409 on a body mismatch or the stored 200 response on a match, and only writes
  `state["idempotency"][scope]` **after** `operation(state)` returns without raising — so any
  `RequestError` from `_create_payment` (400/401/404/409/422, all 4xx) propagates out of the `with`
  block before the key is claimed, matching I4/AC9 "a request that ends in 4xx claims no key" exactly.
- Holding one global lock across lookup+execute trivially gives "concurrent identical first uses →
  exactly one 201" (I4) at the cost of serializing all writes stage-wide — correct for this scope,
  a throughput tradeoff only, not a correctness defect.
- Route-level order in `do_POST` for `/payments`: auth (401) → `_idempotency_key()` (400 missing) →
  `_read_json_object()` (400 parse/non-object) → key length (422) → `execute_idempotent` (409 reuse
  or the stored 200, checked before `_create_payment`'s field validation) → field validation (400/422)
  → self_payment (422) → recipient lookup (404) → funds (409). This is an exact match for D1's
  declared order.
- `build_reset_state` always sets `"idempotency": {}` on every reset, so receipts don't survive a
  reset (checked below).

## Checks run

1. `docker build -t pf1-wp2-s21 stage-1` → succeeds.
2. `python -m unittest test_builder_foundation -v` → **10/10 pass** (6 prior + 4 new: canonical replay
   precedes validation, failed request doesn't claim key, 50 concurrent identical requests have one
   effect, key scope includes user/method/path).
3. Builder's own `stage-1/tests/http_idempotency_check.py` run against a live `--cpus 2 --memory 2g`
   container → `HTTP_IDEMPOTENCY_OK one_201=1 replays=49 balances=9990,2510` — reproduced exactly.
4. My own independent HTTP checks against a separate container instance:
   - Missing `Idempotency-Key` → 400 `missing_idempotency_key`; empty header → same.
   - 255-char key → accepted, 201. 256-char key → 422. 10 KB key → 422.
   - First use (key `r1`, amount 7) → 201; replay with reordered keys and `7.0` instead of `7` → 200,
     byte-identical response body; balance moved exactly once (9995→9988, not twice).
   - Same key, different amount → 409 `idempotency_key_reuse`; same key with a *now-invalid* body
     (`to_handle:7, amount:true`) → still 409 (not 400/422) — confirms R11's "claimed key resolved
     before field validation."
   - Bob reusing the same key string `r1` with his own body → independent 201 (per-user scope).
   - Key `big` against an unaffordable amount → 409 `insufficient_funds`; the **same key** retried
     with an affordable body → 201 (first use), not 409 reuse — confirms the key stays open after a
     409, not just after 400/422.
   - Independent 50-concurrent-identical-request check (own script, same key, same body) → exactly
     one 201, 49×200, exactly one 10-unit debit (balance 9990→9980).
5. Per-path scope is exercised only by the Builder's unit test (`test_key_scope_includes_user_method_and_path`,
   item 2) since no second write path exists yet — read and reproduced, not an external HTTP gap in
   this package's actual scope (S2.2+ wires the other four paths onto the same shared function).
6. Breaker's new `test_idempotency_checkpoint.py` (commit `0c360bd`, diff-confirmed to touch only
   that file + `PLAN.md`, no server code) run against the same candidate: `Ran 7 tests ... OK` —
   canonical numeric/whitespace/ordering equivalence, boolean-vs-number distinctness (`1` ≠ `true` as
   JSON values), D1 ordering (unknown token → 401 before missing-key check), NaN/Infinity rejected as
   malformed without claiming the key, every 4xx kind (404/422 self_payment/422 validation/409 funds)
   leaves the key reusable, 50 conflicting-body first uses → exactly 1×201/24×200/25×409 with a
   single effect, and a reset clears a prior receipt so the same key becomes a fresh first use again.

## Verdict: PASS

Commands and trimmed output:
```
$ docker build -t pf1-wp2-s21 stage-1 → naming to ...pf1-wp2-s21:latest done

$ cd stage-1/tests && python -m unittest test_builder_foundation -v
Ran 10 tests in 0.479s
OK

$ BASE_URL=http://127.0.0.1:9030 python http_idempotency_check.py
HTTP_IDEMPOTENCY_OK one_201=1 replays=49 balances=9990,2510

$ curl -X POST .../payments -H "Idempotency-Key: r1" -d '{"to_handle":"bob","amount":7}' → 201
$ curl -X POST .../payments -H "Idempotency-Key: r1" -d '{"amount":7.0,"to_handle":"bob"}' → 200 (identical body)
$ curl -X POST .../payments -H "Idempotency-Key: r1" -d '{"to_handle":"bob","amount":8}' → 409 idempotency_key_reuse
$ curl -X POST .../payments -H "Idempotency-Key: big" -d '{"to_handle":"bob","amount":999999999}' → 409 insufficient_funds
$ curl -X POST .../payments -H "Idempotency-Key: big" -d '{"to_handle":"bob","amount":1}' → 201   # key reused after 409

$ python verifier_concurrent_check.py   # 50 threads, same key/body
201 count=1 200 count=49 before=9990 after=9980 delta=10

$ BASE_URL=... python -m unittest test_idempotency_checkpoint -v
Ran 7 tests in 1.598s
OK
```

## Open risks

- Per-path scoping is verified by code + the Builder's unit test only; no second write path exists
  yet to confirm externally over HTTP (expected — S2.2/WP3/WP4 wire `/requests`, `/splits`,
  `/settlements` onto the same `execute_idempotent`, must be rechecked then for R9/R10 specifically).
- A single global `StateStore.lock` serializes all writes stage-wide; correct here, but worth
  re-examining for throughput once more write paths and higher realistic concurrency are in play (I7).
- R10 ("replay after the resource changed... still returns 200... changes nothing") is exercised here
  only via "replay after funds moved further" (payments have no cancel/pay-request state machine yet);
  the request-cancellation variant of R10 is WP3 scope.
