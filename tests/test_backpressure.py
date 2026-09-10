"""A full queue must not freeze the caller, and a bad callback must not stop
the client.

Both regressions were unbounded waits or unguarded calls that turned an
ordinary hiccup into a permanent, silent stall.
"""
import logging
import threading
import time

import pytest

from conftest import DEAD_URL


def test_publish_does_not_block_forever_on_a_full_queue(client_factory, monkeypatch, caplog):
    """queue.put() with no timeout blocked the caller's loop indefinitely, with
    no exception and nothing logged."""
    monkeypatch.setenv("TENDRL_APP_URL", DEAD_URL)
    caplog.set_level(logging.WARNING, logger="tendrl")

    # A queue of one, and a sender that can never drain it.
    c = client_factory(max_queue_size=1)

    finished = threading.Event()

    def publish_twice():
        c.publish({"marker": "first"}, tags=["sensor"])
        c.publish({"marker": "second"}, tags=["sensor"])
        finished.set()

    threading.Thread(target=publish_twice, daemon=True).start()

    assert finished.wait(timeout=20), (
        "publish() never returned — a full queue blocks the caller forever"
    )


def test_a_full_queue_is_reported(client_factory, monkeypatch, caplog):
    monkeypatch.setenv("TENDRL_APP_URL", DEAD_URL)
    caplog.set_level(logging.WARNING, logger="tendrl")

    c = client_factory(max_queue_size=1)
    for i in range(5):
        c.publish({"marker": f"flood-{i}"}, tags=["sensor"])

    deadline = time.time() + 15
    while time.time() < deadline:
        if any("DROPPED" in r.getMessage() for r in caplog.records):
            break
        time.sleep(0.1)
    else:
        pytest.fail("messages were discarded at the queue and nothing was logged")


def test_a_raising_callback_does_not_kill_the_sender(client_factory, server, caplog):
    """The single-message path called the callback unguarded, so one exception
    propagated out of the sender thread and the client never sent again."""
    caplog.set_level(logging.WARNING, logger="tendrl")

    def explode(message):
        raise RuntimeError("callback blew up")

    c = client_factory(callback=explode, check_msg_rate=0.2)

    # Give the check loop time to run and the callback time to raise.
    time.sleep(2)

    # The sender must still be alive and still delivering.
    c.publish({"marker": "after-callback-error"}, tags=["sensor"])
    assert server.wait_for_marker("after-callback-error"), (
        "the sender thread died with the callback and stopped publishing"
    )


def test_stop_does_not_hang_on_a_full_queue(server, monkeypatch):
    """stop() put its shutdown sentinel on the queue with no timeout, so
    shutting down a client whose queue was full blocked forever."""
    monkeypatch.setenv("TENDRL_APP_URL", DEAD_URL)
    from tendrl import Client

    c = Client(api_key="test-key", max_queue_size=1)
    # Deliberately never started: nothing will ever drain this queue.
    c.queue.put({"filler": True})

    stopped = threading.Event()

    def stop_it():
        c.stop()
        stopped.set()

    threading.Thread(target=stop_it, daemon=True).start()
    assert stopped.wait(timeout=20), "stop() never returned on a full queue"
