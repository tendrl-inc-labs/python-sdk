"""Offline storage must actually hold messages, and give them back.

The regression these lock down: the SQLite connection was opened by whichever
thread built the Client, but every write came from the sender thread, so
sqlite3 refused all of them. The refusal was logged only under debug, so
`offline_storage=True` stored nothing while looking like it worked.
"""
import os
import time

import pytest

from conftest import DEAD_URL


@pytest.fixture
def offline_client(client_factory, monkeypatch, tmp_path):
    """A client that cannot reach its server, with persistence turned on."""
    monkeypatch.setenv("TENDRL_APP_URL", DEAD_URL)
    return client_factory(
        offline_storage=True, db_path=str(tmp_path / "offline.db")
    )


def _wait_for_count(storage, expected, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if storage.get_message_count() >= expected:
            return True
        time.sleep(0.1)
    return False


def test_failed_send_is_persisted(offline_client):
    offline_client.publish({"marker": "persisted"}, tags=["sensor"])
    assert _wait_for_count(offline_client.storage, 1), (
        "a message that could not be sent was not written to offline storage"
    )


def test_persisted_message_is_sent_when_the_server_returns(offline_client, server):
    """Store-and-forward end to end: hold it while down, deliver it when up."""
    offline_client.publish({"marker": "forwarded"}, tags=["sensor"])
    assert _wait_for_count(offline_client.storage, 1)

    # The server comes back. process_offline_messages is what the sender loop
    # calls once its connection probe succeeds again.
    offline_client.client.base_url = server.url + "/api"
    offline_client.process_offline_messages()

    assert server.wait_for_marker("forwarded"), (
        "a stored message was never delivered after the connection returned"
    )
    assert offline_client.storage.get_message_count() == 0, (
        "the message was delivered but is still queued, so it will be sent again"
    )


def test_stored_messages_survive_a_failed_retry(offline_client):
    """A retry that fails must leave the message in storage, not consume it."""
    offline_client.publish({"marker": "kept"}, tags=["sensor"])
    assert _wait_for_count(offline_client.storage, 1)

    # Still pointed at the dead port: this retry cannot succeed.
    offline_client.process_offline_messages()

    assert offline_client.storage.get_message_count() == 1, (
        "a failed retry deleted the stored message — deleting a batch regardless "
        "of whether it was sent is how a flapping connection erased data"
    )
