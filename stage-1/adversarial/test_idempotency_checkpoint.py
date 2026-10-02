"""Focused S2.1 attacks for the shared idempotency contract."""

from __future__ import annotations

from support import ApiTestCase, BASE_USERS, error_code, request


class IdempotencyCheckpointTests(ApiTestCase):
    def test_R9_canonical_json_numeric_spelling_order_and_whitespace(self) -> None:
        key = self.key("canonical")
        first = request("POST", "/payments", token=self.tokens["ada"], key=key,
                        raw_body=b'{"to_handle":"bob","amount":1,"extra":{"x":1.0,"y":[2e0]}}')
        replay = request("POST", "/payments", token=self.tokens["ada"], key=key,
                         raw_body=b'{ "extra" : { "y" : [ 2 ], "x" : 1e0 }, "amount" : 1.0, "to_handle" : "bob" }')
        self.assertEqual((201, 200), (first.status, replay.status))
        self.assertEqual(first.body, replay.body)
        self.assertEqual(9999, self.get("/me", "ada").body["balance"])

    def test_R11_boolean_and_number_are_distinct_json_values(self) -> None:
        key = self.key("bool-number")
        first = self.post("/payments", {"to_handle": "bob", "amount": 1,
                          "extra": 1}, key=key)
        self.assertEqual(201, first.status, first.body)
        changed = self.post("/payments", {"to_handle": "bob", "amount": 1,
                            "extra": True}, key=key)
        self.assert_error(changed, 409, "idempotency_key_reuse")

    def test_D1_invalid_json_constants_are_malformed_and_do_not_claim_key(self) -> None:
        for index, constant in enumerate((b"NaN", b"Infinity", b"-Infinity")):
            key = f"constant-{index}-{self.seed}"
            malformed = request("POST", "/payments", token=self.tokens["ada"], key=key,
                                raw_body=b'{"to_handle":"bob","amount":' + constant + b"}")
            self.assert_error(malformed, 400, "malformed_request")
            retry = self.post("/payments", {"to_handle": "bob", "amount": 1}, key=key)
            self.assertEqual(201, retry.status, retry.body)

    def test_D1_auth_then_missing_key_then_parse_order(self) -> None:
        unknown = request("POST", "/payments", token="unknown", raw_body=b"not-json")
        self.assert_error(unknown, 401, "unauthenticated")
        missing = request("POST", "/payments", token=self.tokens["ada"], raw_body=b"not-json")
        self.assert_error(missing, 400, "missing_idempotency_key")

    def test_I4_each_kind_of_4xx_leaves_key_reusable(self) -> None:
        failures = [
            ({"to_handle": "missing", "amount": 1}, 404, "not_found"),
            ({"to_handle": "ada", "amount": 1}, 422, "self_payment"),
            ({"to_handle": "bob", "amount": 0}, 422, "validation_failed"),
            ({"to_handle": "bob", "amount": 1001}, 409, "insufficient_funds", "dee"),
        ]
        for index, case in enumerate(failures):
            body, status, code, *handle = case
            actor = handle[0] if handle else "ada"
            key = f"failed-{index}-{self.seed}"
            with self.subTest(code=code):
                self.assert_error(self.post("/payments", body, handle=actor, key=key), status, code)
                valid = ({"to_handle": "ada", "amount": 1} if actor == "dee"
                         else {"to_handle": "bob", "amount": 1})
                self.assertEqual(201, self.post("/payments", valid, handle=actor, key=key).status)

    def test_I4_fifty_conflicting_first_uses_choose_one_body_and_one_effect(self) -> None:
        key = self.key("conflict")
        responses = self.concurrent(50, lambda index: self.post(
            "/payments", {"to_handle": "bob", "amount": 1 if index < 25 else 2}, key=key))
        self.assertEqual(1, sum(response.status == 201 for response in responses),
                         [(response.status, response.body) for response in responses])
        self.assertEqual(24, sum(response.status == 200 for response in responses))
        self.assertEqual(25, sum(response.status == 409 for response in responses))
        winner = next(response.body for response in responses if response.status == 201)
        self.assertTrue(all(response.body == winner for response in responses
                            if response.status in (200, 201)))
        self.assertTrue(all(error_code(response) == "idempotency_key_reuse"
                            for response in responses if response.status == 409))
        self.assertEqual(10000 - winner["amount"], self.get("/me", "ada").body["balance"])

    def test_R10_replay_precedes_changed_funds_and_reset_clears_receipt(self) -> None:
        key = self.key("state-change")
        body = {"to_handle": "bob", "amount": 1}
        first = self.post("/payments", body, key=key)
        self.assertEqual(201, first.status, first.body)
        self.assertEqual(201, self.post("/payments", {"to_handle": "bob", "amount": 9999},
                                             key=self.key("drain")).status)
        replay = self.post("/payments", body, key=key)
        self.assertEqual(200, replay.status, replay.body)
        self.assertEqual(first.body, replay.body)
        self.reset()
        self.tokens = {user["handle"]: self.login(user["email"], user["password"])
                       for user in BASE_USERS}
        reused_after_reset = self.post("/payments", {"to_handle": "bob", "amount": 2}, key=key)
        self.assertEqual(201, reused_after_reset.status, reused_after_reset.body)
