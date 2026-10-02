"""Adversarial settlement and portable-state checks."""

from __future__ import annotations

import json

from support import ApiTestCase, PASSWORD, fixture, request


class SettlementTests(ApiTestCase):
    def test_R17_AC10_authorization_key_and_batch_shape_boundaries(self) -> None:
        body = {"transfers": [{"from_handle": "ada", "to_handle": "bob", "amount": 1}]}
        self.assert_error(self.post("/settlements", body, handle="bob", key=self.key()),
                          403, "forbidden")
        self.assert_error(self.post("/settlements", body, key=None),
                          400, "missing_idempotency_key")
        for transfers in ([], "not-array", [1], [body["transfers"][0]] * 33):
            with self.subTest(transfers_type=type(transfers), length=getattr(transfers, "__len__", lambda: -1)()):
                response = self.post("/settlements", {"transfers": transfers}, key=self.key())
                self.assert_error(response, 422, "validation_failed")

    def test_R17_entry_rules_and_first_failure_in_input_order(self) -> None:
        invalid_cases = [
            ({"from_handle": "missing", "to_handle": "bob", "amount": 1}, 404, "not_found"),
            ({"from_handle": "ada", "to_handle": "ada", "amount": 1}, 422, "self_payment"),
            ({"from_handle": "ada", "to_handle": "bob", "amount": 0}, 422, "validation_failed"),
            ({"from_handle": "ada", "to_handle": "bob", "amount": 1, "note": None}, 422, "validation_failed"),
            ({"from_handle": "ada", "to_handle": "bob", "amount": 1,
              "visibility": "friends"}, 422, "validation_failed"),
        ]
        for transfer, status, code in invalid_cases:
            with self.subTest(transfer=transfer):
                self.assert_error(self.post("/settlements", {"transfers": [transfer]}, key=self.key()),
                                  status, code)
        wrong_type = self.post("/settlements", {"transfers": [
            {"from_handle": 3, "to_handle": "bob", "amount": 1}]}, key=self.key())
        self.assert_error(wrong_type, 400, "malformed_request")
        ordered = self.post("/settlements", {"transfers": [
            {"from_handle": "missing", "to_handle": "bob", "amount": 1},
            {"from_handle": "ada", "to_handle": "ada", "amount": 1},
        ]}, key=self.key())
        self.assert_error(ordered, 404, "not_found")
        reusable_key = self.key("validation-reuse")
        self.assert_error(self.post("/settlements", {"transfers": []}, key=reusable_key),
                          422, "validation_failed")
        retry = self.post("/settlements", {"transfers": [
            {"from_handle": "ada", "to_handle": "bob", "amount": 1}
        ]}, key=reusable_key)
        self.assertEqual(201, retry.status, retry.body)

    def test_R17_I1_I2_net_affordability_atomicity_and_input_order_receipts(self) -> None:
        before = self.balances()
        body = {"transfers": [
            {"from_handle": "dee", "to_handle": "bob", "amount": 1500,
             "note": "out first", "visibility": "private"},
            {"from_handle": "ada", "to_handle": "dee", "amount": 600,
             "note": "funding", "visibility": "public"},
        ]}
        response = self.post("/settlements", body, key=self.key())
        self.assertEqual(201, response.status, response.body)
        self.assertEqual(["out first", "funding"], [p["note"] for p in response.body["payments"]])
        settlement_id = response.body["settlement_id"]
        for payment in response.body["payments"]:
            self.assertEqual(settlement_id, payment["settlement_id"])
            self.assertIsNone(payment["request_id"])
            self.assertEqual(response.body["committed_at"], payment["created_at"])
        after = self.balances()
        self.assertEqual(sum(before.values()), sum(after.values()))
        self.assertEqual(before["dee"] - 900, after["dee"])

        failed_before = self.balances()
        key = self.key("failed-settlement")
        failed = self.post("/settlements", {"transfers": [
            {"from_handle": "dee", "to_handle": "bob", "amount": 101}
        ]}, key=key)
        self.assert_error(failed, 409, "insufficient_funds")
        self.assertEqual(failed_before, self.balances())
        reusable = self.post("/settlements", {"transfers": [
            {"from_handle": "bob", "to_handle": "dee", "amount": 1}
        ]}, key=key)
        self.assertEqual(201, reusable.status, reusable.body)

    def test_R17_replay_and_visibility_grants_operator_no_extra_read_access(self) -> None:
        key = self.key()
        body = {"transfers": [{"from_handle": "bob", "to_handle": "cy", "amount": 5,
                                "visibility": "private"}]}
        first = self.post("/settlements", body, key=key)
        replay = self.post("/settlements", body, key=key)
        self.assertEqual((201, 200), (first.status, replay.status))
        self.assertEqual(first.body, replay.body)
        payment_id = first.body["payments"][0]["payment_id"]
        self.assertNotIn(payment_id, [p["payment_id"] for p in self.get("/activity", "ada").body["payments"]])
        self.assertIn(payment_id, [p["payment_id"] for p in self.get("/activity", "bob").body["payments"]])
        self.assertIn(payment_id, [p["payment_id"] for p in self.get("/activity", "cy").body["payments"]])
        unrelated = self.post("/requests", {"payer_handle": "cy", "amount": 1},
                              handle="bob", key=self.key()).body["request_id"]
        self.assertNotIn(unrelated, [r["request_id"] for r in self.get("/requests", "ada").body["requests"]])


class ExportImportTests(ApiTestCase):
    def test_R18_AC11_export_shape_invalid_import_is_atomic_and_malformed_is_400(self) -> None:
        exported = request("GET", "/_test/export", timeout=10)
        self.assertEqual(200, exported.status, exported.body)
        self.assertEqual("pocketful", exported.body.get("track"))
        self.assertEqual(1, exported.body.get("format_version"))
        self.assertIsInstance(exported.body.get("state"), dict)
        before = self.get("/me").body
        invalid_values = [
            {}, {"track": "wrong", "format_version": 1, "state": exported.body["state"]},
            {"track": "pocketful", "format_version": 2, "state": exported.body["state"]},
            {"track": "pocketful", "format_version": 1, "state": {}},
        ]
        for invalid in invalid_values:
            with self.subTest(invalid=invalid):
                response = request("POST", "/_test/import", invalid, timeout=10)
                self.assert_error(response, 422, "validation_failed")
                self.assertEqual(before, self.get("/me").body)
        malformed = request("POST", "/_test/import", raw_body=b'{"track":', timeout=10)
        self.assert_error(malformed, 400, "malformed_request")
        self.assertEqual(before, self.get("/me").body)

    def test_R18_tokens_passwords_receipts_operators_and_membership_survive(self) -> None:
        payment_key = self.key("receipt")
        payment_body = {"to_handle": "bob", "amount": 5, "note": "preserve"}
        original = self.post("/payments", payment_body, key=payment_key)
        settlement_key = self.key("settlement")
        settlement_body = {"transfers": [
            {"from_handle": "bob", "to_handle": "cy", "amount": 3}]}
        settlement = self.post("/settlements", settlement_body, key=settlement_key)
        old_token = self.tokens["ada"]
        exported = request("GET", "/_test/export", timeout=10).body

        self.reset(fixture(currency="JPY", minor_units=0))
        self.assertEqual(204, request("POST", "/_test/import", exported, timeout=10).status)
        self.assertEqual(200, request("GET", "/me", token=old_token).status)
        self.assertEqual(200, request("POST", "/auth/login", {
            "email": "ada@example.com", "password": PASSWORD}).status)
        replay = request("POST", "/payments", payment_body, token=old_token, key=payment_key)
        self.assertEqual(200, replay.status)
        self.assertEqual(original.body, replay.body)
        settlement_replay = request("POST", "/settlements", settlement_body,
                                    token=old_token, key=settlement_key)
        self.assertEqual(200, settlement_replay.status)
        self.assertEqual(settlement.body, settlement_replay.body)
        self.assertEqual(settlement.body["settlement_id"],
                         settlement_replay.body["payments"][0]["settlement_id"])

    def test_R18_import_replaces_repeats_without_duplicates_and_reset_clears(self) -> None:
        created = request("POST", "/auth/signup", {
            "email": "only-source@example.com", "password": PASSWORD, "display_name": "Source"})
        self.assertEqual(201, created.status, created.body)
        source_token = created.body["token"]
        exported = request("GET", "/_test/export", timeout=10).body
        self.reset()
        destination = request("POST", "/auth/signup", {
            "email": "only-destination@example.com", "password": PASSWORD, "display_name": "Dest"})
        destination_token = destination.body["token"]
        for _ in range(2):
            self.assertEqual(204, request("POST", "/_test/import", exported, timeout=10).status)
        self.assertEqual(200, request("GET", "/me", token=source_token).status)
        self.assert_error(request("GET", "/me", token=destination_token), 401, "unauthenticated")
        source_login = request("POST", "/auth/login", {
            "email": "only-source@example.com", "password": PASSWORD})
        self.assertEqual(200, source_login.status, source_login.body)
        self.assert_error(request("POST", "/auth/login", {
            "email": "only-destination@example.com", "password": PASSWORD}), 401, "unauthenticated")
        self.reset()
        self.assert_error(request("GET", "/me", token=source_token), 401, "unauthenticated")

    def test_R18_snapshot_is_read_only_and_failed_keys_remain_reusable_after_import(self) -> None:
        failed_key = self.key("failed")
        self.assert_error(self.post("/payments", {"to_handle": "missing", "amount": 1}, key=failed_key),
                          404, "not_found")
        exported = request("GET", "/_test/export", timeout=10).body
        later = self.post("/payments", {"to_handle": "bob", "amount": 99}, key=self.key())
        self.assertEqual(201, later.status)
        self.assertEqual(204, request("POST", "/_test/import", exported, timeout=10).status)
        self.assertEqual([], self.get("/activity").body["payments"])
        reusable = self.post("/payments", {"to_handle": "bob", "amount": 1}, key=failed_key)
        self.assertEqual(201, reusable.status, reusable.body)

    def test_I6_import_replacement_has_no_observable_mixed_state(self) -> None:
        from concurrent.futures import ThreadPoolExecutor
        import threading

        old_export = request("GET", "/_test/export", timeout=10).body
        old_token = self.tokens["ada"]
        self.reset(fixture(currency="JPY", minor_units=0))
        barrier = threading.Barrier(51)

        def read_me(_: int):
            barrier.wait(timeout=5)
            return request("GET", "/me", token=old_token)

        def replace_state():
            barrier.wait(timeout=5)
            return request("POST", "/_test/import", old_export, timeout=10)

        with ThreadPoolExecutor(max_workers=51) as pool:
            reads = [pool.submit(read_me, index) for index in range(50)]
            import_future = pool.submit(replace_state)
            responses = [future.result() for future in reads]
            imported = import_future.result()
        self.assertEqual(204, imported.status)
        # Requests racing before the atomic replacement may be unauthorized; none may
        # observe a partial account or produce a server error.
        for response in responses:
            self.assertIn(response.status, (200, 401), response.body)
            if response.status == 200:
                self.assertEqual(("EUR", 2, "ada"),
                                 (response.body["currency"], response.body["minor_units"],
                                  response.body["handle"]))
        self.assertEqual(200, request("GET", "/me", token=old_token).status)
