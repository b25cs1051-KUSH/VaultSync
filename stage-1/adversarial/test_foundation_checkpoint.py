"""Checkpoint tests runnable before authentication and wallet reads exist."""

from __future__ import annotations

import time

from support import ApiTestCase, PASSWORD, fixture, request


class FoundationCheckpointTests(ApiTestCase):
    def setUp(self) -> None:
        # S1.1-S1.2 intentionally precede login and /me.
        self.seed = 1

    def test_R1_AC2_health_and_json_content_type(self) -> None:
        response = request("GET", "/health")
        self.assertEqual(200, response.status)
        self.assertEqual({"status": "ok"}, response.body)
        self.assertEqual("application/json; charset=utf-8", response.headers.get("Content-Type"))

    def test_R6_AC12_unparseable_and_non_object_bodies_are_400_envelopes(self) -> None:
        for raw in (b"not-json", b"[]", b"null", b'"text"', b"1"):
            with self.subTest(raw=raw):
                response = request("POST", "/_test/reset", raw_body=raw, timeout=10)
                self.assert_error(response, 400, "malformed_request")

    def test_R16_AC3_D6_reset_validation_and_repeated_replacement(self) -> None:
        old = fixture()
        new = fixture(currency="JPY", minor_units=0, users=[dict(fixture()["users"][0],
                      id="u_new", email="new@example.com", handle="new")],
                      settlement_operator_ids=[])
        for value in (old, new, old):
            response = request("POST", "/_test/reset", value, timeout=10)
            self.assertEqual(204, response.status, response.body)
            self.assertIsNone(response.body)
        for invalid in (fixture(minor_units=1),
                        fixture(users=[dict(fixture()["users"][0], balance=-1)])):
            response = request("POST", "/_test/reset", invalid, timeout=10)
            self.assert_error(response, 422, "validation_failed")
        # A failed reset must not poison or lock the endpoint.
        self.assertEqual(204, request("POST", "/_test/reset", old, timeout=10).status)

    def test_I6_I7_fifty_in_flight_resets_and_reads_never_5xx(self) -> None:
        old = fixture()
        new = fixture(currency="BHD", minor_units=3)
        def operation(index: int):
            try:
                return (request("POST", "/_test/reset", old if index % 2 else new, timeout=10)
                        if index < 25 else request("GET", "/health"))
            except Exception as exc:  # Preserve transport failures as test evidence.
                return exc

        responses = self.concurrent(50, operation)
        failures = [repr(item) for item in responses if isinstance(item, Exception)]
        self.assertEqual([], failures)
        self.assertTrue(all(response.status in (200, 204) for response in responses),
                        [(response.status, response.body) for response in responses])
        self.assertTrue(all(response.status < 500 for response in responses))

    def test_R1_I7_fifty_health_requests_all_receive_200(self) -> None:
        def operation(_: int):
            try:
                return request("GET", "/health")
            except Exception as exc:  # Preserve transport failures as test evidence.
                return exc

        responses = self.concurrent(50, operation)
        failures = [repr(item) for item in responses if isinstance(item, Exception)]
        self.assertEqual([], failures)
        self.assertTrue(all(response.status == 200 for response in responses),
                        [(response.status, response.body) for response in responses])

    def test_I7_large_fixture_reset_hashes_within_ten_seconds(self) -> None:
        users = [{"id": f"u_{index}", "email": f"user{index}@example.com", "password": PASSWORD,
                  "display_name": f"User {index}", "handle": f"user{index}", "balance": index}
                 for index in range(200)]
        value = fixture(users=users, settlement_operator_ids=["u_0"])
        started = time.monotonic()
        response = request("POST", "/_test/reset", value, timeout=10)
        elapsed = time.monotonic() - started
        print(f"LARGE_RESET_SECONDS={elapsed:.3f}")
        self.assertEqual(204, response.status, response.body)
        self.assertLess(elapsed, 10, f"large reset took {elapsed:.3f}s")
