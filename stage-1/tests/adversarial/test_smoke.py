"""Skeleton smoke check; full requirement coverage is added in S0.2."""

from __future__ import annotations

import unittest

from support import request


class SmokeTests(unittest.TestCase):
    def test_R1_AC2_health_ready_contract(self) -> None:
        response = request("GET", "/health")
        self.assertEqual(200, response.status)
        self.assertEqual({"status": "ok"}, response.body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
