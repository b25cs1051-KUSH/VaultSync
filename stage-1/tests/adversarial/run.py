"""Run the independent Pocketful stage 1 adversarial suite."""

from __future__ import annotations

import argparse
import os
import random
import sys
import unittest
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    if not os.environ.get("BASE_URL"):
        parser.error("BASE_URL must name the running service, e.g. http://127.0.0.1:9000")

    seed = int(os.environ.get("ADVERSARIAL_SEED", random.SystemRandom().randrange(2**63)))
    os.environ["ADVERSARIAL_SEED"] = str(seed)
    print(f"ADVERSARIAL_SEED={seed}", flush=True)

    suite_dir = Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(str(suite_dir), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

