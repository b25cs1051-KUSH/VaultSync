"""Adversarial authentication, parsing, boundary, seed, and listing checks."""

from __future__ import annotations

import json
import urllib.parse

from support import ApiTestCase, PASSWORD, assert_rfc3339_with_offset, fixture, request


class AuthenticationAndValidationTests(ApiTestCase):
    def test_R1_AC2_health_ready_contract(self) -> None:
        response = request("GET", "/health")
        self.assertEqual(200, response.status)
        self.assertEqual({"status": "ok"}, response.body)

    def test_R2_timestamps_have_explicit_offsets(self) -> None:
        payment = self.post("/payments", {"to_handle": "bob", "amount": 1}, key=self.key())
        self.assertEqual(201, payment.status, payment.body)
        assert_rfc3339_with_offset(self, payment.body["created_at"])
        settlement = self.post("/settlements", {"transfers": [
            {"from_handle": "ada", "to_handle": "bob", "amount": 1}
        ]}, key=self.key())
        self.assertEqual(201, settlement.status, settlement.body)
        assert_rfc3339_with_offset(self, settlement.body["committed_at"])
        self.assertEqual(settlement.body["committed_at"], settlement.body["payments"][0]["created_at"])

    def test_R3_AC4_unauthenticated_all_protected_endpoint_families(self) -> None:
        cases = [("GET", "/me", None), ("GET", "/activity", None),
                 ("GET", "/requests", None), ("POST", "/settlements", {"transfers": []})]
        for method, path, body in cases:
            for headers in ({}, {"Authorization": "Basic abc"},
                            {"Authorization": "Bearer unknown-token"}):
                with self.subTest(method=method, path=path, headers=headers):
                    response = request(method, path, body, extra_headers=headers)
                    self.assert_error(response, 401, "unauthenticated")

    def test_R4_AC4_signup_login_handle_and_credential_boundaries(self) -> None:
        bad_password = request("POST", "/auth/signup", {
            "email": "new@example.com", "password": "short", "display_name": "New"})
        self.assert_error(bad_password, 422, "validation_failed")
        bad_email = request("POST", "/auth/signup", {
            "email": "not-an-email", "password": PASSWORD, "display_name": "New"})
        self.assert_error(bad_email, 422, "validation_failed")
        taken = request("POST", "/auth/signup", {
            "email": "ADA@EXAMPLE.COM", "password": PASSWORD, "display_name": "Other"})
        self.assert_error(taken, 409, "email_taken")
        collision_email = "A-D-A@example.net"  # derives a_d_a, used below
        created = request("POST", "/auth/signup", {
            "email": collision_email, "password": PASSWORD, "display_name": "First"})
        self.assertEqual(201, created.status, created.body)
        collision = request("POST", "/auth/signup", {
            "email": "a+d+a@example.net", "password": PASSWORD, "display_name": "Second"})
        self.assert_error(collision, 409, "handle_taken")
        absent = request("POST", "/auth/login", {"email": "a+d+a@example.net", "password": PASSWORD})
        self.assert_error(absent, 401, "unauthenticated")
        wrong = request("POST", "/auth/login", {"email": "ada@example.com", "password": "wrong pass"})
        self.assert_error(wrong, 401, "unauthenticated")
        token_1 = self.login("ADA@example.com")
        token_2 = self.login("ada@example.com")
        self.assertNotEqual(token_1, token_2)
        for token in (token_1, token_2):
            self.assertEqual(200, request("GET", "/me", token=token).status)

    def test_R4_derived_handle_lowercase_substitute_and_truncate(self) -> None:
        response = request("POST", "/auth/signup", {
            "email": "UPPER.long-local+suffix@example.com", "password": PASSWORD,
            "display_name": "Derived"})
        self.assertEqual(201, response.status, response.body)
        me = request("GET", "/me", token=response.body["token"])
        self.assertEqual("upper_long_local_suf", me.body["handle"])
        self.assertEqual(0, me.body["balance"])

    def test_R5_password_never_plaintext_in_export(self) -> None:
        exported = request("GET", "/_test/export", timeout=10)
        self.assertEqual(200, exported.status, exported.body)
        serialized = json.dumps(exported.body, ensure_ascii=False)
        self.assertNotIn(PASSWORD, serialized)

    def test_R6_AC12_body_shape_and_wrong_type_error_partition(self) -> None:
        token = self.tokens["ada"]
        not_object = request("POST", "/payments", [], token=token, key=self.key())
        self.assert_error(not_object, 400, "malformed_request")
        malformed = request("POST", "/payments", token=token, key=self.key(), raw_body=b'{"x":')
        self.assert_error(malformed, 400, "malformed_request")
        wrong_handle = self.post("/payments", {"to_handle": 5, "amount": 1}, key=self.key())
        self.assert_error(wrong_handle, 400, "malformed_request")
        wrong_participants = self.post("/splits", {
            "amount": 1, "participant_handles": "bob"}, key=self.key())
        self.assert_error(wrong_participants, 400, "malformed_request")
        for field, value in (("amount", True), ("amount", "1"), ("note", None),
                             ("visibility", 3), ("visibility", "friends")):
            body = {"to_handle": "bob", "amount": 1, field: value}
            with self.subTest(field=field, value=value):
                self.assert_error(self.post("/payments", body, key=self.key()),
                                  422, "validation_failed")

    def test_R7_I8_integral_json_numbers_and_amount_boundaries(self) -> None:
        for amount in (1000.0,):
            response = self.post("/payments", {"to_handle": "bob", "amount": amount}, key=self.key())
            self.assertEqual(201, response.status, response.body)
            self.assertEqual(1000, response.body["amount"])
        exponent = request("POST", "/payments", token=self.tokens["ada"], key=self.key(),
                           raw_body=b'{"to_handle":"bob","amount":1e3}')
        self.assertEqual(201, exponent.status, exponent.body)
        for amount in (1000.5, "1000", True, 0, -1, 1000000001):
            with self.subTest(amount=amount):
                response = self.post("/payments", {"to_handle": "bob", "amount": amount}, key=self.key())
                self.assert_error(response, 422, "validation_failed")

    def test_R8_AC9_idempotency_key_length_edges_and_empty(self) -> None:
        accepted = self.post("/payments", {"to_handle": "bob", "amount": 1}, key="x" * 255)
        self.assertEqual(201, accepted.status, accepted.body)
        too_long = self.post("/payments", {"to_handle": "bob", "amount": 1}, key="x" * 256)
        self.assert_error(too_long, 422, "validation_failed")
        for key in (None, ""):
            with self.subTest(key=key):
                response = self.post("/payments", {"to_handle": "bob", "amount": 1}, key=key)
                self.assert_error(response, 400, "missing_idempotency_key")

    def test_R14_AC6_request_query_validation_pagination_and_order(self) -> None:
        for amount in (1, 2, 3):
            response = self.post("/requests", {"payer_handle": "bob", "amount": amount}, key=self.key())
            self.assertEqual(201, response.status, response.body)
        page = self.get("/requests?direction=outgoing&status=pending&limit=2&offset=0&ignored=yes")
        self.assertEqual(200, page.status, page.body)
        self.assertEqual([3, 2], [item["amount"] for item in page.body["requests"]])
        self.assertIs(page.body["has_more"], True)
        last = self.get("/requests?limit=2&offset=2")
        self.assertEqual([1], [item["amount"] for item in last.body["requests"]])
        self.assertIs(last.body["has_more"], False)
        for query in ("limit=1e9", "limit=4.0", "limit=%2B4", "limit=0", "limit=201",
                      "offset=-1", "direction=sideways", "status=unknown"):
            with self.subTest(query=query):
                self.assert_error(self.get("/requests?" + query), 422, "validation_failed")

    def test_R15_seeded_records_all_statuses_and_feed_scope(self) -> None:
        seeded = fixture(
            payments=[{"id": "p_seed", "from_user_id": "u_ada", "to_user_id": "u_bob",
                       "amount": 7, "note": "seed", "visibility": "private"}],
            requests=[
                {"id": f"rq_{status}", "requester_id": "u_ada", "payer_id": "u_bob",
                 "amount": index + 1, "note": status, "status": status}
                for index, status in enumerate(("pending", "paid", "declined", "cancelled"))
            ])
        self.reset(seeded)
        self.tokens = {user["handle"]: self.login(user["email"]) for user in seeded["users"]}
        for handle in ("ada", "bob"):
            feed = self.get("/activity", handle)
            self.assertEqual(["p_seed"], [p["payment_id"] for p in feed.body["payments"]])
            assert_rfc3339_with_offset(self, feed.body["payments"][0]["created_at"])
        self.assertEqual([], self.get("/activity", "cy").body["payments"])
        listed = self.get("/requests", "bob")
        self.assertEqual({"pending", "paid", "declined", "cancelled"},
                         {item["status"] for item in listed.body["requests"]})
        for item in listed.body["requests"]:
            assert_rfc3339_with_offset(self, item["created_at"])

    def test_R16_AC3_currency_minor_units_and_invalid_reset_is_atomic(self) -> None:
        for currency, units in (("JPY", 0), ("BHD", 3)):
            seeded = fixture(currency=currency, minor_units=units)
            self.reset(seeded)
            token = self.login("ada@example.com")
            me = request("GET", "/me", token=token)
            self.assertEqual((currency, units), (me.body["currency"], me.body["minor_units"]))
        self.reset()
        original_token = self.login("ada@example.com")
        before = request("GET", "/me", token=original_token).body
        for invalid in (fixture(minor_units=1), fixture(users=[dict(fixture()["users"][0], balance=-1)])):
            response = request("POST", "/_test/reset", invalid, timeout=10)
            self.assert_error(response, 422, "validation_failed")
            self.assertEqual(before, request("GET", "/me", token=original_token).body)


class ErrorEnvelopeTests(ApiTestCase):
    def test_AC12_every_exercised_error_has_code_and_message(self) -> None:
        cases = [
            self.post("/payments", {"to_handle": "missing", "amount": 1}, key=self.key()),
            self.post("/payments", {"to_handle": "ada", "amount": 1}, key=self.key()),
            self.post("/payments", {"to_handle": "bob", "amount": 10**9}, handle="dee", key=self.key()),
        ]
        for response in cases:
            self.assertGreaterEqual(response.status, 400)
            self.assertLess(response.status, 500)
            self.assertIsInstance(response.body["error"]["code"], str)
            self.assertIsInstance(response.body["error"]["message"], str)
