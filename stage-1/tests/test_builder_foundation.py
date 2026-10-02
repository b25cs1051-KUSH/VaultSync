import importlib.util
import pathlib
import threading
import unittest
from datetime import datetime


SERVER_PATH = pathlib.Path(__file__).parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("pocketful_server", SERVER_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


def fixture(user_id="u_ada", balance=10000, minor_units=2):
    return {
        "currency": "EUR",
        "minor_units": minor_units,
        "users": [
            {
                "id": user_id,
                "email": f"{user_id}@example.com",
                "password": "correct horse",
                "display_name": "Ada",
                "handle": user_id.removeprefix("u_"),
                "balance": balance,
            }
        ],
        "payments": [],
        "requests": [],
    }


def payment_fixture():
    value = fixture()
    value["users"].append(
        {
            "id": "u_bob",
            "email": "bob@example.com",
            "password": "correct horse",
            "display_name": "Bob",
            "handle": "bob",
            "balance": 2500,
        }
    )
    return value


class ResetStateTests(unittest.TestCase):
    def test_passwords_are_hashed_and_second_reset_replaces_everything(self):
        store = SERVER.StateStore()
        store.replace_from_fixture(fixture())
        first = store.snapshot()
        user = first["users"]["u_ada"]
        self.assertNotIn("password", user)
        self.assertNotIn("correct horse", user["password_hash"])
        self.assertTrue(SERVER.password_matches("correct horse", user["password_hash"]))

        store.replace_from_fixture(fixture("u_bob", 2500))
        second = store.snapshot()
        self.assertNotIn("u_ada", second["users"])
        self.assertEqual(second["users"]["u_bob"]["balance"], 2500)
        self.assertEqual(second["settlement_operator_ids"], [])

    def test_invalid_fixture_does_not_change_state(self):
        store = SERVER.StateStore()
        store.replace_from_fixture(fixture())
        before = store.snapshot()
        with self.assertRaises(SERVER.RequestError) as caught:
            store.replace_from_fixture(fixture(balance=-1))
        self.assertEqual(caught.exception.status, 422)
        self.assertEqual(caught.exception.code, "validation_failed")
        self.assertEqual(store.snapshot(), before)

        with self.assertRaises(SERVER.RequestError):
            store.replace_from_fixture(fixture(minor_units=1))
        self.assertEqual(store.snapshot(), before)

    def test_seeded_records_receive_offset_timestamps(self):
        value = fixture()
        value["users"].append(
            {
                "id": "u_bob",
                "email": "bob@example.com",
                "password": "correct horse",
                "display_name": "Bob",
                "handle": "bob",
                "balance": 2500,
            }
        )
        value["payments"] = [
            {
                "id": "p_1",
                "from_user_id": "u_ada",
                "to_user_id": "u_bob",
                "amount": 500,
                "note": "coffee",
                "visibility": "public",
            }
        ]
        value["requests"] = [
            {
                "id": "rq_1",
                "requester_id": "u_bob",
                "payer_id": "u_ada",
                "amount": 1200,
                "note": "taxi",
                "status": "pending",
            }
        ]
        store = SERVER.StateStore()
        store.replace_from_fixture(value)
        state = store.snapshot()
        payment_time = datetime.fromisoformat(state["payments"]["p_1"]["created_at"])
        request_time = datetime.fromisoformat(state["requests"]["rq_1"]["created_at"])
        self.assertIsNotNone(payment_time.utcoffset())
        self.assertIsNotNone(request_time.utcoffset())

    def test_concurrent_readers_only_see_complete_reset_states(self):
        store = SERVER.StateStore()
        old_fixture = fixture("u_old", 10)
        new_fixture = fixture("u_new", 20)
        store.replace_from_fixture(old_fixture)
        observed = []

        def read_repeatedly():
            for _ in range(200):
                state = store.snapshot()
                observed.append((frozenset(state["users"]), state["total_seeded"]))

        readers = [threading.Thread(target=read_repeatedly) for _ in range(8)]
        for reader in readers:
            reader.start()
        store.replace_from_fixture(new_fixture)
        for reader in readers:
            reader.join()
        self.assertTrue(observed)
        self.assertTrue(
            all(value in {(frozenset({"u_old"}), 10), (frozenset({"u_new"}), 20)} for value in observed)
        )

    def test_signup_login_multiple_tokens_and_derived_handle(self):
        store = SERVER.StateStore()
        store.replace_from_fixture(fixture())
        first_login = store.login("U_ADA@example.com", "correct horse")
        second_login = store.login("u_ada@example.com", "correct horse")
        self.assertNotEqual(first_login["token"], second_login["token"])
        self.assertEqual("ada", store.authenticate(first_login["token"])["handle"])
        self.assertEqual("ada", store.authenticate(second_login["token"])["handle"])

        created = store.signup(
            "UPPER.long-local+suffix@example.com", "another horse", "Derived"
        )
        me = store.authenticate(created["token"])
        self.assertEqual("upper_long_local_suf", me["handle"])
        self.assertEqual(0, me["balance"])
        serialized = repr(store.snapshot())
        self.assertNotIn("another horse", serialized)

    def test_signup_conflicts_are_atomic(self):
        store = SERVER.StateStore()
        store.replace_from_fixture(fixture())
        before = store.snapshot()
        with self.assertRaises(SERVER.RequestError) as email_taken:
            store.signup("U_ADA@EXAMPLE.COM", "another horse", "Duplicate")
        self.assertEqual("email_taken", email_taken.exception.code)
        self.assertEqual(before, store.snapshot())

        store.signup("A-D-A@example.net", "another horse", "First")
        before_collision = store.snapshot()
        with self.assertRaises(SERVER.RequestError) as handle_taken:
            store.signup("a+d+a@example.net", "another horse", "Second")
        self.assertEqual("handle_taken", handle_taken.exception.code)
        self.assertEqual(before_collision, store.snapshot())


class IdempotencyStateTests(unittest.TestCase):
    def setUp(self):
        self.store = SERVER.StateStore()
        self.store.replace_from_fixture(payment_fixture())
        logged_in = self.store.login("u_ada@example.com", "correct horse")
        self.user_id = logged_in["user_id"]
        self.token = logged_in["token"]

    def test_canonical_replay_moves_money_once_and_precedes_validation(self):
        body = {
            "to_handle": "bob",
            "amount": 1,
            "note": "same",
            "extra": {"b": 2, "a": 1},
        }
        first_status, first = self.store.create_payment_idempotent(
            self.user_id, self.token, "same", body
        )
        replay_body = {
            "extra": {"a": 1.0, "b": 2.0},
            "note": "same",
            "amount": 1.0,
            "to_handle": "bob",
        }
        replay_status, replay = self.store.create_payment_idempotent(
            self.user_id, self.token, "same", replay_body
        )
        self.assertEqual((201, 200), (first_status, replay_status))
        self.assertEqual(first, replay)
        state = self.store.snapshot()
        self.assertEqual(9999, state["users"]["u_ada"]["balance"])
        self.assertEqual(2501, state["users"]["u_bob"]["balance"])
        self.assertEqual(1, len(state["payments"]))

        with self.assertRaises(SERVER.RequestError) as reuse:
            self.store.create_payment_idempotent(
                self.user_id,
                self.token,
                "same",
                {"to_handle": 7, "amount": True},
            )
        self.assertEqual("idempotency_key_reuse", reuse.exception.code)

    def test_failed_request_does_not_claim_key(self):
        with self.assertRaises(SERVER.RequestError) as missing:
            self.store.create_payment_idempotent(
                self.user_id,
                self.token,
                "reusable",
                {"to_handle": "missing", "amount": 1},
            )
        self.assertEqual("not_found", missing.exception.code)
        status, _ = self.store.create_payment_idempotent(
            self.user_id,
            self.token,
            "reusable",
            {"to_handle": "bob", "amount": 1},
        )
        self.assertEqual(201, status)

    def test_fifty_concurrent_identical_requests_have_one_effect(self):
        barrier = threading.Barrier(50)
        results = []
        results_lock = threading.Lock()

        def send():
            barrier.wait()
            result = self.store.create_payment_idempotent(
                self.user_id,
                self.token,
                "concurrent",
                {"to_handle": "bob", "amount": 10},
            )
            with results_lock:
                results.append(result)

        threads = [threading.Thread(target=send) for _ in range(50)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, sum(status == 201 for status, _ in results))
        self.assertEqual(49, sum(status == 200 for status, _ in results))
        self.assertEqual(1, len({repr(body) for _, body in results}))
        state = self.store.snapshot()
        self.assertEqual(9990, state["users"]["u_ada"]["balance"])
        self.assertEqual(2510, state["users"]["u_bob"]["balance"])
        self.assertEqual(1, len(state["payments"]))

    def test_key_scope_includes_user_method_and_path(self):
        def receipt(label):
            return lambda _: {"label": label}

        first = self.store.execute_idempotent(
            self.user_id,
            self.token,
            "POST",
            "/requests",
            "shared",
            {"amount": 1},
            receipt("request"),
        )
        second = self.store.execute_idempotent(
            self.user_id,
            self.token,
            "POST",
            "/splits",
            "shared",
            {"amount": 1},
            receipt("split"),
        )
        bob = self.store.login("bob@example.com", "correct horse")
        third = self.store.execute_idempotent(
            bob["user_id"],
            bob["token"],
            "POST",
            "/requests",
            "shared",
            {"amount": 1},
            receipt("other user"),
        )
        self.assertEqual([201, 201, 201], [first[0], second[0], third[0]])


if __name__ == "__main__":
    unittest.main()
