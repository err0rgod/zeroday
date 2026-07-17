import unittest
from types import SimpleNamespace
from unittest.mock import patch

from lib import blob_store


class FakeConditionalCheckFailed(Exception):
    pass


class FakeTransactionCanceled(Exception):
    pass


class FakeClient:
    exceptions = SimpleNamespace(
        ConditionalCheckFailedException=FakeConditionalCheckFailed,
        TransactionCanceledException=FakeTransactionCanceled,
    )

    def __init__(self):
        self.transactions = []

    def transact_write_items(self, **kwargs):
        self.transactions.append(kwargs)


class FakeTable:
    def __init__(self, counter=None, counter_exists=False):
        self.meta = SimpleNamespace(client=FakeClient())
        self.counter = counter or {
            "PK": "METRIC#SUBSCRIBERS",
            "SK": "COUNT",
            "value": 62,
            "initialized_at": "2026-07-18T00:00:00+00:00",
        }
        self.counter_exists = counter_exists
        self.updates = []

    def put_item(self, **kwargs):
        if self.counter_exists:
            raise FakeConditionalCheckFailed()
        self.counter = kwargs["Item"]
        self.counter_exists = True

    def get_item(self, **kwargs):
        return {"Item": self.counter}

    def update_item(self, **kwargs):
        self.updates.append(kwargs)


class SubscriberBadgeCounterTests(unittest.TestCase):
    def test_initializes_counter_at_62(self):
        table = FakeTable()
        with patch.object(blob_store, "_get_table", return_value=table):
            counter = blob_store.get_or_create_subscriber_badge_counter()

        self.assertEqual(counter["value"], 62)
        self.assertIn("initialized_at", counter)

    def test_new_verification_uses_one_transaction(self):
        table = FakeTable(counter_exists=True)
        subscriber = {
            "email": "reader@example.com",
            "created_at": "2026-07-18T00:01:00+00:00",
            "verified_email": False,
            "badge_counted": False,
        }
        with patch.object(
            blob_store, "_get_table", return_value=table
        ), patch.object(
            blob_store, "get_subscriber", return_value=subscriber
        ), patch.object(
            blob_store,
            "get_or_create_subscriber_badge_counter",
            return_value=table.counter,
        ):
            incremented = blob_store.mark_subscriber_verified("reader@example.com")

        self.assertTrue(incremented)
        self.assertEqual(len(table.meta.client.transactions), 1)
        transaction = table.meta.client.transactions[0]["TransactItems"]
        self.assertEqual(len(transaction), 2)
        self.assertIn("badge_counted = :counted", transaction[0]["Update"]["UpdateExpression"])
        self.assertEqual(transaction[1]["Update"]["UpdateExpression"], "ADD #value :one")

    def test_historical_or_repeated_verification_does_not_increment(self):
        table = FakeTable(counter_exists=True)
        historical = {
            "email": "old@example.com",
            "created_at": "2026-07-17T23:59:00+00:00",
            "verified_email": False,
            "badge_counted": False,
        }
        with patch.object(
            blob_store, "_get_table", return_value=table
        ), patch.object(
            blob_store, "get_subscriber", return_value=historical
        ), patch.object(
            blob_store,
            "get_or_create_subscriber_badge_counter",
            return_value=table.counter,
        ):
            incremented = blob_store.mark_subscriber_verified("old@example.com")

        self.assertFalse(incremented)
        self.assertEqual(table.meta.client.transactions, [])
        self.assertEqual(len(table.updates), 1)


if __name__ == "__main__":
    unittest.main()
