# Pocketful stage 1 adversarial suite

Run the suite against an already-running service:

```powershell
$env:BASE_URL = "http://127.0.0.1:9000"
python stage-1/adversarial/run.py
```

The runner uses only the Python standard library. It prints every test name and
its result. Set `ADVERSARIAL_SEED` to reproduce randomized trials; otherwise the
runner generates and prints a seed.

List the inventory without contacting a service:

```powershell
python stage-1/adversarial/run.py --list
```

## Coverage map

- `test_auth_validation.py`: R1-R8, R14-R16; AC2-AC4, AC6, AC9, AC12; I8.
- `test_money_idempotency.py`: R9-R13, R19; AC5-AC9; I1-I5, I8.
- `test_settlement_export.py`: R17-R18; AC10-AC11; I1-I2, I6.
- `test_concurrency_invariants.py`: R20; AC12; I1-I2, I7-I8.

AC1 is the external stage gate and is deliberately not duplicated here: run the
official isolated harness command named by the Architect. Every HTTP-behaviour
acceptance criterion and every R1-R20/I1-I8 item has a named adversarial test.
