from http_idempotency_check import PASSWORD, request


def login(email):
    return request(
        "POST", "/auth/login", {"email": email, "password": PASSWORD}
    )[1]["token"]


def main():
    fixture = {
        "currency": "EUR",
        "minor_units": 2,
        "users": [
            {
                "id": "u_ada",
                "email": "ada@example.com",
                "password": PASSWORD,
                "display_name": "Ada",
                "handle": "ada",
                "balance": 10000,
            },
            {
                "id": "u_bob",
                "email": "bob@example.com",
                "password": PASSWORD,
                "display_name": "Bob",
                "handle": "bob",
                "balance": 2500,
            },
            {
                "id": "u_cy",
                "email": "cy@example.com",
                "password": PASSWORD,
                "display_name": "Cy",
                "handle": "cy",
                "balance": 500,
            },
        ],
        "payments": [
            {
                "id": "p_seed_public",
                "from_user_id": "u_ada",
                "to_user_id": "u_bob",
                "amount": 1,
                "visibility": "public",
            },
            {
                "id": "p_seed_private",
                "from_user_id": "u_ada",
                "to_user_id": "u_bob",
                "amount": 1,
                "visibility": "private",
            },
        ],
        "requests": [
            {
                "id": "rq_seed",
                "requester_id": "u_ada",
                "payer_id": "u_cy",
                "amount": 1,
                "status": "pending",
            }
        ],
    }
    assert request("POST", "/_test/reset", fixture)[0] == 204
    tokens = {
        "ada": login("ada@example.com"),
        "bob": login("bob@example.com"),
        "cy": login("cy@example.com"),
    }
    public = request(
        "POST",
        "/payments",
        {"to_handle": "bob", "amount": 1, "visibility": "public"},
        tokens["ada"],
        "public",
    )[1]
    private = request(
        "POST",
        "/payments",
        {"to_handle": "bob", "amount": 1, "visibility": "private"},
        tokens["ada"],
        "private",
    )[1]

    party_expected = {
        private["payment_id"],
        public["payment_id"],
        "p_seed_public",
        "p_seed_private",
    }
    for handle in ("ada", "bob"):
        status, body = request("GET", "/activity", token=tokens[handle])
        assert status == 200
        assert {item["payment_id"] for item in body["payments"]} == party_expected
        assert [item["payment_id"] for item in body["payments"][:2]] == [
            private["payment_id"],
            public["payment_id"],
        ]
        assert all(item["payment_id"] != "rq_seed" for item in body["payments"])

    first = request("GET", "/activity?limit=1&offset=0&ignored=yes", token=tokens["cy"])
    second = request("GET", "/activity?limit=1&offset=1", token=tokens["cy"])
    assert first[0] == second[0] == 200
    assert [item["payment_id"] for item in first[1]["payments"]] == [public["payment_id"]]
    assert first[1]["has_more"] is True
    assert [item["payment_id"] for item in second[1]["payments"]] == ["p_seed_public"]
    assert second[1]["has_more"] is False

    for query in (
        "limit=1e9",
        "limit=4.0",
        "limit=%2B4",
        "limit=0",
        "limit=201",
        "offset=-1",
    ):
        status, body = request("GET", "/activity?" + query, token=tokens["ada"])
        assert (status, body["error"]["code"]) == (422, "validation_failed")
    print("HTTP_ACTIVITY_OK parties=4 third_party=2 pagination=true,false")


if __name__ == "__main__":
    main()
