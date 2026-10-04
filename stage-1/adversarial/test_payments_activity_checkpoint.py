"""Focused WP2 payment and activity-feed attacks."""

from __future__ import annotations

from support import ApiTestCase, assert_rfc3339_with_offset, fixture, request


class PaymentsActivityCheckpointTests(ApiTestCase):
    def test_AC5_R19_receipt_defaults_shape_and_unicode_round_trip(self) -> None:
        note = "  café 🧾 e\u0301 漢字  "
        response = self.post("/payments", {"to_handle": "bob", "amount": 7,
                             "note": note}, key=self.key())
        self.assertEqual(201, response.status, response.body)
        expected_fields = {"payment_id", "from_user_id", "from_handle", "to_user_id",
                           "to_handle", "amount", "currency", "note", "visibility",
                           "request_id", "settlement_id", "created_at"}
        self.assertEqual(expected_fields, set(response.body))
        self.assertEqual(note, response.body["note"])
        self.assertEqual("public", response.body["visibility"])
        self.assertIsNone(response.body["request_id"])
        self.assertIsNone(response.body["settlement_id"])
        assert_rfc3339_with_offset(self, response.body["created_at"])
        feed = self.get("/activity", "bob")
        self.assertEqual(note, feed.body["payments"][0]["note"])

    def test_AC8_visibility_newest_first_and_page_boundaries(self) -> None:
        receipts = []
        for index, visibility in enumerate(("public", "private", "public"), start=1):
            receipts.append(self.post("/payments", {"to_handle": "bob", "amount": 1,
                            "note": str(index), "visibility": visibility}, key=self.key()).body)
        party = self.get("/activity?limit=2&offset=0&ignored=yes", "bob")
        self.assertEqual([receipts[2]["payment_id"], receipts[1]["payment_id"]],
                         [item["payment_id"] for item in party.body["payments"]])
        self.assertIs(party.body["has_more"], True)
        boundary = self.get("/activity?limit=2&offset=2", "bob")
        self.assertEqual([receipts[0]["payment_id"]],
                         [item["payment_id"] for item in boundary.body["payments"]])
        self.assertIs(boundary.body["has_more"], False)
        beyond = self.get("/activity?limit=2&offset=3", "bob")
        self.assertEqual([], beyond.body["payments"])
        self.assertIs(beyond.body["has_more"], False)
        third_party = self.get("/activity", "cy")
        self.assertEqual([receipts[2]["payment_id"], receipts[0]["payment_id"]],
                         [item["payment_id"] for item in third_party.body["payments"]])

    def test_AC8_strict_ascii_decimal_queries_and_duplicate_values(self) -> None:
        for query in ("limit=", "limit=01&limit=2", "offset=0&offset=1",
                      "limit=%D9%A1", "limit=1e0", "limit=4.0", "limit=%2B4",
                      "limit=%204", "limit=0", "limit=201", "offset=-1"):
            with self.subTest(query=query):
                self.assert_error(self.get("/activity?" + query), 422, "validation_failed")
        accepted = self.get("/activity?limit=%31&offset=0000&LIMIT=bad")
        self.assertEqual(200, accepted.status, accepted.body)

    def test_R15_seeded_private_visibility_and_server_timestamps(self) -> None:
        seeded = fixture(payments=[
            {"id": "p_public", "from_user_id": "u_ada", "to_user_id": "u_bob",
             "amount": 1, "note": "public", "visibility": "public"},
            {"id": "p_private", "from_user_id": "u_ada", "to_user_id": "u_bob",
             "amount": 1, "note": "private", "visibility": "private"},
        ])
        self.reset(seeded)
        self.tokens = {user["handle"]: self.login(user["email"], user["password"])
                       for user in seeded["users"]}
        self.assertEqual({"p_private", "p_public"},
                         {p["payment_id"] for p in self.get("/activity", "ada").body["payments"]})
        self.assertEqual(["p_public"],
                         [p["payment_id"] for p in self.get("/activity", "cy").body["payments"]])
        for payment in self.get("/activity", "bob").body["payments"]:
            assert_rfc3339_with_offset(self, payment["created_at"])

    def test_I1_I2_I5_concurrent_burst_is_complete_in_both_party_feeds(self) -> None:
        before = self.balances()
        responses = self.concurrent(50, lambda index: self.post(
            "/payments", {"to_handle": "bob", "amount": 1,
                           "visibility": "private" if index % 2 else "public"},
            key=f"feed-burst-{self.seed}-{index}"))
        self.assertTrue(all(response.status == 201 for response in responses),
                        [(response.status, response.body) for response in responses])
        payment_ids = {response.body["payment_id"] for response in responses}
        self.assertEqual(payment_ids,
                         {p["payment_id"] for p in self.get("/activity", "ada").body["payments"]})
        self.assertEqual(payment_ids,
                         {p["payment_id"] for p in self.get("/activity", "bob").body["payments"]})
        self.assertEqual(25, len(self.get("/activity", "cy").body["payments"]))
        after = self.balances()
        self.assertEqual(sum(before.values()), sum(after.values()))
        self.assertEqual(before["ada"] - 50, after["ada"])
        self.assertEqual(before["bob"] + 50, after["bob"])

    def test_I5_failed_payment_leaves_feed_and_balances_unchanged(self) -> None:
        before_balances = self.balances()
        before_feeds = {handle: self.get("/activity", handle).body for handle in self.tokens}
        failed = self.post("/payments", {"to_handle": "ada", "amount": 1001},
                           handle="dee", key=self.key())
        self.assert_error(failed, 409, "insufficient_funds")
        self.assertEqual(before_balances, self.balances())
        self.assertEqual(before_feeds,
                         {handle: self.get("/activity", handle).body for handle in self.tokens})
