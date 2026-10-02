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


if __name__ == "__main__":
    unittest.main()
