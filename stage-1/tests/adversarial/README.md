# Pocketful stage 1 adversarial suite

Run the suite against an already-running service:

```powershell
$env:BASE_URL = "http://127.0.0.1:9000"
python stage-1/tests/adversarial/run.py
```

The runner uses only the Python standard library. It prints every test name and
its result. Set `ADVERSARIAL_SEED` to reproduce randomized trials; otherwise the
runner generates and prints a seed.

