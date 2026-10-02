"""Adversarial payment, request, split, visibility, and idempotency checks."""

from __future__ import annotations

from support import ApiTestCase, assert_rfc3339_with_offset, request


class PaymentAndFeedTests(ApiTestCase):
    def test_AC5_I1_I2_payment_shape_defaults_errors_and_atomic_balances(self) -> None:
        before = self.balances()
        response = self.post("/payments", {"to_handle": "bob", "amount": 1500}, key=self.key())
        self.assertEqual(201, response.status, response.body)
        self.assertEqual("", response.body["note"])
        self.assertEqual("public", response.body["visibility"])
        self.assertIsNone(response.body["request_id"])
        self.assertIsNone(response.body["settlement_id"])
        self.assertEqual(("ada", "bob"), (response.body["from_handle"], response.body["to_handle"]))
        assert_rfc3339_with_offset(self, response.body["created_at"])
        after = self.balances()
        self.assertEqual(sum(before.values()), sum(after.values()))
        self.assertEqual(before["ada"] - 1500, after["ada"])
        self.assertEqual(before["bob"] + 1500, after["bob"])
        for body, status, code in (
            ({"to_handle": "ada", "amount": 1}, 422, "self_payment"),
            ({"to_handle": "missing", "amount": 1}, 404, "not_found"),
            ({"to_handle": "bob", "amount": 1, "note": "x" * 201}, 422, "validation_failed"),
            ({"to_handle": "bob", "amount": 1, "visibility": "friends"}, 422, "validation_failed"),
            ({"to_handle": "ada", "amount": 1001}, 422, "self_payment"),
        ):
            with self.subTest(body=body):
                self.assert_error(self.post("/payments", body, key=self.key()), status, code)
        insufficient = self.post("/payments", {"to_handle": "ada", "amount": 1001},
                                 handle="dee", key=self.key())
        self.assert_error(insufficient, 409, "insufficient_funds")
        self.assertEqual(after, self.balances())

    def test_AC8_feed_visibility_is_exact_and_requests_never_appear(self) -> None:
        public = self.post("/payments", {"to_handle": "bob", "amount": 1,
                                           "visibility": "public"}, key=self.key()).body
        private = self.post("/payments", {"to_handle": "bob", "amount": 1,
                                            "visibility": "private"}, key=self.key()).body
        requested = self.post("/requests", {"payer_handle": "cy", "amount": 1}, key=self.key()).body
        for handle, expected in (("ada", {public["payment_id"], private["payment_id"]}),
                                 ("bob", {public["payment_id"], private["payment_id"]}),
                                 ("cy", {public["payment_id"]})):
            feed = self.get("/activity?limit=1&offset=0" if handle == "cy" else "/activity", handle)
            self.assertEqual(expected, {item["payment_id"] for item in feed.body["payments"]})
            self.assertTrue(all(item.get("request_id") != requested["request_id"]
                                for item in feed.body["payments"]))

    def test_I5_failed_payment_leaves_no_feed_or_balance_trace(self) -> None:
        before = self.balances()
        feeds_before = {h: self.get("/activity", h).body for h in self.tokens}
        response = self.post("/payments", {"to_handle": "ada", "amount": 1001},
                             handle="dee", key=self.key())
        self.assert_error(response, 409, "insufficient_funds")
        self.assertEqual(before, self.balances())
        self.assertEqual(feeds_before, {h: self.get("/activity", h).body for h in self.tokens})


class RequestsAndSplitsTests(ApiTestCase):
    def test_AC6_request_can_exceed_balance_then_pay_after_funding(self) -> None:
        created = self.post("/requests", {"payer_handle": "dee", "amount": 1100,
                                           "note": "later"}, key=self.key())
        self.assertEqual(201, created.status, created.body)
        request_id = created.body["request_id"]
        short = self.post(f"/requests/{request_id}/pay", {"visibility": "private"},
                          handle="dee", key=self.key())
        self.assert_error(short, 409, "insufficient_funds")
        self.assertEqual("pending", self.get("/requests?status=pending", "dee").body["requests"][0]["status"])
        self.post("/payments", {"to_handle": "dee", "amount": 100}, key=self.key())
        paid = self.post(f"/requests/{request_id}/pay", {"visibility": "private"},
                         handle="dee", key=self.key())
        self.assertEqual(201, paid.status, paid.body)
        self.assertEqual(request_id, paid.body["request_id"])
        self.assertEqual("private", paid.body["visibility"])

    def test_R12_I3_concurrent_different_key_pays_move_money_once(self) -> None:
        created = self.post("/requests", {"payer_handle": "bob", "amount": 700}, key=self.key()).body
        before = self.balances()
        responses = self.concurrent(20, lambda index: self.post(
            f"/requests/{created['request_id']}/pay", {}, handle="bob", key=f"pay-{index}-{self.seed}"))
        self.assertEqual(1, sum(r.status == 201 for r in responses), [(r.status, r.body) for r in responses])
        self.assertEqual(19, sum(r.status == 409 for r in responses), [(r.status, r.body) for r in responses])
        for response in responses:
            if response.status == 409:
                self.assert_error(response, 409, "request_not_pending")
        after = self.balances()
        self.assertEqual(before["bob"] - 700, after["bob"])
        self.assertEqual(before["ada"] + 700, after["ada"])
        self.assertEqual(sum(before.values()), sum(after.values()))

    def test_R13_AC6_decline_cancel_terminal_and_wrong_party_rules(self) -> None:
        declining = self.post("/requests", {"payer_handle": "bob", "amount": 1}, key=self.key()).body
        rid = declining["request_id"]
        self.assert_error(self.post(f"/requests/{rid}/decline", {}, handle="cy"), 403, "forbidden")
        first = self.post(f"/requests/{rid}/decline", {}, handle="bob")
        second = self.post(f"/requests/{rid}/decline", {}, handle="bob")
        self.assertEqual((200, 200), (first.status, second.status))
        self.assertEqual("declined", second.body["status"])
        self.assert_error(self.post(f"/requests/{rid}/cancel", {}, handle="ada"),
                          409, "request_not_pending")

        cancelling = self.post("/requests", {"payer_handle": "bob", "amount": 1}, key=self.key()).body
        cid = cancelling["request_id"]
        self.assert_error(self.post(f"/requests/{cid}/cancel", {}, handle="bob"), 403, "forbidden")
        self.assertEqual(200, self.post(f"/requests/{cid}/cancel", {}, handle="ada").status)
        again = self.post(f"/requests/{cid}/cancel", {}, handle="ada")
        self.assertEqual(200, again.status)
        self.assertEqual("cancelled", again.body["status"])
        self.assert_error(self.post(f"/requests/{cid}/decline", {}, handle="bob"),
                          409, "request_not_pending")

    def test_AC7_I8_split_rounding_zero_shares_and_validation(self) -> None:
        split = self.post("/splits", {"amount": 10,
                          "participant_handles": ["bob", "ada", "cy"], "note": "dinner"}, key=self.key())
        self.assertEqual(201, split.status, split.body)
        self.assertEqual([("bob", 4), ("ada", 3), ("cy", 3)],
                         [(s["handle"], s["amount"]) for s in split.body["shares"]])
        self.assertEqual(["bob", "cy"], [r["payer_handle"] for r in split.body["requests"]])
        zeros = self.post("/splits", {"amount": 1,
                          "participant_handles": ["ada", "bob", "cy"]}, key=self.key())
        self.assertEqual([1, 0, 0], [s["amount"] for s in zeros.body["shares"]])
        self.assertEqual([0, 0], [r["amount"] for r in zeros.body["requests"]])
        caller_only = self.post("/splits", {"amount": 5, "participant_handles": ["ada"]}, key=self.key())
        self.assertEqual([], caller_only.body["requests"])
        for participants in ([], ["bob", "bob"]):
            self.assert_error(self.post("/splits", {"amount": 5,
                              "participant_handles": participants}, key=self.key()), 422, "validation_failed")
        self.assert_error(self.post("/splits", {"amount": 5,
                          "participant_handles": ["missing"]}, key=self.key()), 404, "not_found")


class IdempotencyTests(ApiTestCase):
    def test_R9_I4_requests_concurrent_replay_and_reuse(self) -> None:
        key = self.key("request")
        body = {"payer_handle": "bob", "amount": 23, "note": "same"}
        responses = self.concurrent(12, lambda _: self.post("/requests", body, key=key))
        self.assertEqual(1, sum(r.status == 201 for r in responses))
        self.assertEqual(11, sum(r.status == 200 for r in responses))
        self.assertEqual(1, len({repr(r.body) for r in responses}))
        changed = self.post("/requests", dict(body, amount=24), key=key)
        self.assert_error(changed, 409, "idempotency_key_reuse")

    def test_R9_I4_splits_concurrent_replay_and_reuse(self) -> None:
        key = self.key("split")
        body = {"amount": 7, "participant_handles": ["ada", "bob", "cy"]}
        responses = self.concurrent(12, lambda _: self.post("/splits", body, key=key))
        self.assertEqual(1, sum(r.status == 201 for r in responses))
        self.assertEqual(11, sum(r.status == 200 for r in responses))
        self.assertEqual(1, len({repr(r.body) for r in responses}))
        self.assert_error(self.post("/splits", dict(body, amount=8), key=key),
                          409, "idempotency_key_reuse")

    def test_R10_replay_survives_resource_state_change(self) -> None:
        key = self.key()
        body = {"payer_handle": "bob", "amount": 5}
        original = self.post("/requests", body, key=key)
        rid = original.body["request_id"]
        self.assertEqual(200, self.post(f"/requests/{rid}/cancel", {}, handle="ada").status)
        replay = self.post("/requests", body, key=key)
        self.assertEqual(200, replay.status)
        self.assertEqual(original.body, replay.body)
        current = self.get("/requests?status=cancelled", "ada")
        self.assertIn(rid, [item["request_id"] for item in current.body["requests"]])

    def test_R10_pay_replay_after_paid_returns_original_receipt(self) -> None:
        request_body = self.post("/requests", {"payer_handle": "bob", "amount": 5}, key=self.key()).body
        path = f"/requests/{request_body['request_id']}/pay"
        key = self.key("pay")
        first = self.post(path, {}, handle="bob", key=key)
        replay = self.post(path, {}, handle="bob", key=key)
        self.assertEqual((201, 200), (first.status, replay.status))
        self.assertEqual(first.body, replay.body)

    def test_R11_claimed_key_precedes_field_and_resource_validation(self) -> None:
        key = self.key()
        self.assertEqual(201, self.post("/payments", {"to_handle": "bob", "amount": 1}, key=key).status)
        invalid = self.post("/payments", {"to_handle": 7, "amount": True}, key=key)
        self.assert_error(invalid, 409, "idempotency_key_reuse")

    def test_AC9_I4_scope_by_user_and_path_and_failed_key_reusable(self) -> None:
        shared = self.key("shared")
        payment = {"to_handle": "bob", "amount": 1}
        self.assertEqual(201, self.post("/payments", payment, handle="ada", key=shared).status)
        self.assertEqual(201, self.post("/payments", {"to_handle": "ada", "amount": 1},
                                              handle="bob", key=shared).status)
        self.assertEqual(201, self.post("/requests", {"payer_handle": "bob", "amount": 1},
                                              handle="ada", key=shared).status)
        reusable = self.key("failed")
        self.assert_error(self.post("/payments", {"to_handle": "missing", "amount": 1}, key=reusable),
                          404, "not_found")
        self.assertEqual(201, self.post("/payments", payment, key=reusable).status)


class UnicodeTests(ApiTestCase):
    def test_R19_unicode_emoji_verbatim_across_resources_and_export_import(self) -> None:
        note = "  café 🧾 e\u0301 漢字  "
        payment = self.post("/payments", {"to_handle": "bob", "amount": 1,
                            "note": note, "visibility": "public"}, key=self.key())
        requested = self.post("/requests", {"payer_handle": "bob", "amount": 1,
                              "note": note}, key=self.key())
        split = self.post("/splits", {"amount": 1, "participant_handles": ["ada", "cy"],
                          "note": note}, key=self.key())
        self.assertEqual(note, payment.body["note"])
        self.assertEqual(note, requested.body["note"])
        self.assertEqual(note, split.body["note"])
        self.assertIn(note, [item["note"] for item in self.get("/activity", "bob").body["payments"]])
        exported = request("GET", "/_test/export", timeout=10)
        self.assertEqual(204, request("POST", "/_test/import", exported.body, timeout=10).status)
        self.assertIn(note, [item["note"] for item in self.get("/activity", "bob").body["payments"]])
        code_points = "😀" * 200
        accepted = self.post("/payments", {"to_handle": "bob", "amount": 1,
                             "note": code_points}, key=self.key())
        self.assertEqual(201, accepted.status, accepted.body)
        rejected = self.post("/payments", {"to_handle": "bob", "amount": 1,
                             "note": code_points + "x"}, key=self.key())
        self.assert_error(rejected, 422, "validation_failed")
