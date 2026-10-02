"""Focused WP1 authentication and reset/read concurrency attacks."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from support import ApiTestCase, PASSWORD, error_code, fixture, request


class AuthenticationCheckpointTests(ApiTestCase):
    def test_R4_I6_concurrent_duplicate_signup_creates_exactly_one_account(self) -> None:
        body = {"email": "race@example.com", "password": PASSWORD,
                "display_name": "Racer", "unknown": "ignored"}
        responses = self.concurrent(50, lambda _: request("POST", "/auth/signup", body))
        self.assertEqual(1, sum(response.status == 201 for response in responses),
                         [(response.status, response.body) for response in responses])
        self.assertEqual(49, sum(response.status == 409 for response in responses))
        self.assertTrue(all(response.status == 201 or error_code(response) == "email_taken"
                            for response in responses))
        login = request("POST", "/auth/login", {"email": "RACE@example.com",
                        "password": PASSWORD})
        self.assertEqual(200, login.status, login.body)

    def test_R4_I7_fifty_concurrent_logins_create_distinct_valid_tokens(self) -> None:
        responses = self.concurrent(50, lambda _: request("POST", "/auth/login", {
            "email": "ADA@example.com", "password": PASSWORD}))
        self.assertTrue(all(response.status == 200 for response in responses),
                        [(response.status, response.body) for response in responses])
        tokens = [response.body["token"] for response in responses]
        self.assertEqual(50, len(set(tokens)))
        for token in tokens:
            me = request("GET", "/me", token=token)
            self.assertEqual(200, me.status, me.body)
            self.assertEqual(("u_ada", "ada", 10000),
                             (me.body["user_id"], me.body["handle"], me.body["balance"]))

    def test_I6_reset_racing_me_reads_exposes_only_old_or_replaced_state(self) -> None:
        token = self.tokens["ada"]
        replacement = fixture(currency="JPY", minor_units=0,
                              users=[dict(fixture()["users"][1], id="u_new",
                                          email="new@example.com", handle="new")],
                              settlement_operator_ids=[])
        barrier = threading.Barrier(50)

        def read_me():
            barrier.wait(timeout=5)
            return request("GET", "/me", token=token)

        def reset_state():
            barrier.wait(timeout=5)
            return request("POST", "/_test/reset", replacement, timeout=10)

        with ThreadPoolExecutor(max_workers=50) as pool:
            reads = [pool.submit(read_me) for _ in range(49)]
            reset_future = pool.submit(reset_state)
            responses = [future.result() for future in reads]
            reset_response = reset_future.result()
        self.assertEqual(204, reset_response.status, reset_response.body)
        for response in responses:
            self.assertIn(response.status, (200, 401), response.body)
            if response.status == 200:
                self.assertEqual(("u_ada", "ada", 10000, "EUR", 2),
                                 (response.body["user_id"], response.body["handle"],
                                  response.body["balance"], response.body["currency"],
                                  response.body["minor_units"]))
            else:
                self.assertEqual("unauthenticated", error_code(response))
        self.assert_error(request("GET", "/me", token=token), 401, "unauthenticated")

    def test_R4_R6_auth_body_types_password_boundary_and_ignored_handle(self) -> None:
        for field in ("email", "password", "display_name"):
            body = {"email": "typed@example.com", "password": PASSWORD,
                    "display_name": "Typed"}
            body[field] = 7
            with self.subTest(field=field):
                self.assert_error(request("POST", "/auth/signup", body),
                                  400, "malformed_request")
        short = request("POST", "/auth/signup", {"email": "short@example.com",
                        "password": "1234567", "display_name": "Short"})
        self.assert_error(short, 422, "validation_failed")
        exact = request("POST", "/auth/signup", {"email": "exact@example.com",
                        "password": "12345678", "display_name": "Exact",
                        "handle": "must_be_ignored"})
        self.assertEqual(201, exact.status, exact.body)
        me = request("GET", "/me", token=exact.body["token"])
        self.assertEqual("exact", me.body["handle"])
