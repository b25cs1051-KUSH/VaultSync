"""Seeded, reproducible concurrency attacks against the global invariants."""

from __future__ import annotations

import time

from support import ApiTestCase, PASSWORD, fixture, request


class ConcurrencyInvariantTests(ApiTestCase):
    def test_R20_I1_I2_AC12_fifty_way_ring_preserves_total_and_nonnegative(self) -> None:
        handles = ["ada", "bob", "cy", "dee"]
        before = self.balances()

        def operation(index: int):
            sender = handles[index % len(handles)]
            receiver = handles[(index + 1) % len(handles)]
            return self.post("/payments", {"to_handle": receiver, "amount": 1},
                             handle=sender, key=f"ring-{self.seed}-{index}")

        responses = self.concurrent(50, operation)
        self.assertTrue(all(response.status == 201 for response in responses),
                        [(response.status, response.body) for response in responses])
        after = self.balances()
        self.assertEqual(sum(before.values()), sum(after.values()))
        self.assertTrue(all(balance >= 0 for balance in after.values()), after)
        self.assertTrue(all(response.status < 500 for response in responses))

    def test_R20_I1_I2_fifty_conflicting_partial_drains_have_exact_success_count(self) -> None:
        before = self.balances()
        responses = self.concurrent(50, lambda index: self.post(
            "/payments", {"to_handle": "ada", "amount": 100}, handle="dee",
            key=f"drain-{self.seed}-{index}"))
        self.assertEqual(10, sum(response.status == 201 for response in responses),
                         [(response.status, response.body) for response in responses])
        self.assertEqual(40, sum(response.status == 409 for response in responses))
        self.assertTrue(all(response.status < 500 for response in responses))
        after = self.balances()
        self.assertEqual(sum(before.values()), sum(after.values()))
        self.assertEqual(0, after["dee"])
        self.assertTrue(all(balance >= 0 for balance in after.values()), after)

    def test_I7_fifty_logins_and_large_reset_stay_within_contract_timeouts(self) -> None:
        users = [{"id": f"u_{index}", "email": f"user{index}@example.com", "password": PASSWORD,
                  "display_name": f"User {index}", "handle": f"user{index}", "balance": index}
                 for index in range(50)]
        started = time.monotonic()
        response = request("POST", "/_test/reset", fixture(users=users,
                           settlement_operator_ids=[]), timeout=10)
        self.assertEqual(204, response.status, response.body)
        self.assertLess(time.monotonic() - started, 10)
        responses = self.concurrent(50, lambda index: request("POST", "/auth/login", {
            "email": f"user{index}@example.com", "password": PASSWORD}, timeout=5))
        self.assertTrue(all(item.status == 200 for item in responses),
                        [(item.status, item.body) for item in responses])

    def test_I8_exact_arithmetic_near_safe_integer_limit(self) -> None:
        high = 2**53 - 1000
        users = [
            {"id": "u_high", "email": "high@example.com", "password": PASSWORD,
             "display_name": "High", "handle": "high", "balance": high},
            {"id": "u_low", "email": "low@example.com", "password": PASSWORD,
             "display_name": "Low", "handle": "low", "balance": 1000},
        ]
        self.reset(fixture(users=users, settlement_operator_ids=[]))
        high_token = self.login("high@example.com")
        low_token = self.login("low@example.com")
        response = request("POST", "/payments", {"to_handle": "low", "amount": 999999999},
                           token=high_token, key=self.key())
        self.assertEqual(201, response.status, response.body)
        high_after = request("GET", "/me", token=high_token).body["balance"]
        low_after = request("GET", "/me", token=low_token).body["balance"]
        self.assertEqual(high - 999999999, high_after)
        self.assertEqual(1000 + 999999999, low_after)
        self.assertEqual(2**53, high_after + low_after)
