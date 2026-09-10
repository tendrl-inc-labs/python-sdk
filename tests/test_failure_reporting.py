"""Undelivered messages must be loud.

The regression these lock down: with offline_storage off (the default), a failed
batch was discarded and nothing was logged unless debug=True. A client with a
bad URL, a dead network or a wrong key looked exactly like a healthy one, and
data went missing with no signal at all.
"""
import logging
import time

import pytest

from conftest import DEAD_URL


def _wait_for_record(caplog, needle, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if any(needle in r.getMessage() for r in caplog.records):
            return True
        time.sleep(0.1)
    return False


def test_dropped_messages_are_reported_without_debug(client_factory, monkeypatch, caplog):
    """The default configuration must announce data loss."""
    monkeypatch.setenv("TENDRL_APP_URL", DEAD_URL)
    caplog.set_level(logging.WARNING, logger="tendrl")

    c = client_factory()                      # debug defaults to False
    c.publish({"marker": "lost"}, tags=["sensor"])

    assert _wait_for_record(caplog, "DROPPED"), (
        "a message was discarded and nothing was logged. This is the silent-drop "
        "regression: publish() cannot report it (it is async), so the sender loop "
        "must."
    )


def test_the_drop_warning_names_the_remedy(client_factory, monkeypatch, caplog):
    monkeypatch.setenv("TENDRL_APP_URL", DEAD_URL)
    caplog.set_level(logging.WARNING, logger="tendrl")

    c = client_factory()
    c.publish({"marker": "lost-remedy"}, tags=["sensor"])
    assert _wait_for_record(caplog, "DROPPED")

    text = " ".join(r.getMessage() for r in caplog.records)
    assert "offline_storage=True" in text, (
        "the warning says data was lost but not how to stop it happening again"
    )


def test_offline_storage_reports_held_not_dropped(client_factory, monkeypatch, caplog, tmp_path):
    """With persistence on, the same failure is a retry, not a loss — and must not
    tell the operator their data is gone."""
    monkeypatch.setenv("TENDRL_APP_URL", DEAD_URL)
    caplog.set_level(logging.WARNING, logger="tendrl")

    c = client_factory(offline_storage=True, db_path=str(tmp_path / "offline.db"))
    c.publish({"marker": "held"}, tags=["sensor"])

    assert _wait_for_record(caplog, "held in offline storage"), (
        "a persisted batch was not reported as retryable"
    )
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "DROPPED" not in text, (
        "messages were safely persisted but the operator was told they were dropped"
    )


def test_healthy_client_logs_no_warnings(client_factory, server, caplog):
    """The corollary: a working client must stay quiet, or the warning is noise
    and will be filtered out by the people who need to see it."""
    caplog.set_level(logging.WARNING, logger="tendrl")

    c = client_factory()
    c.publish({"marker": "quiet"}, tags=["sensor"])
    assert server.wait_for_marker("quiet")
    time.sleep(1)

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert not warnings, f"healthy client emitted warnings: {warnings}"


def test_server_error_is_reported(client_factory, server, caplog):
    """A reachable server that rejects the batch is still a delivery failure."""
    caplog.set_level(logging.WARNING, logger="tendrl")
    server.post_status = 500

    c = client_factory()
    c.publish({"marker": "rejected"}, tags=["sensor"])

    assert _wait_for_record(caplog, "DROPPED"), (
        "the server refused the batch and the client said nothing"
    )


def test_headless_publish_reports_failure(client_factory, monkeypatch, caplog):
    """Headless mode has no sender loop, so the send happens inline — and its
    return value cannot express failure, because a successful post may also
    return None."""
    monkeypatch.setenv("TENDRL_APP_URL", DEAD_URL)
    caplog.set_level(logging.WARNING, logger="tendrl")

    c = client_factory(headless=True)
    c.publish({"marker": "headless-lost"}, tags=["sensor"])

    assert _wait_for_record(caplog, "DROPPED"), (
        "a headless publish failed and the caller got no signal at all"
    )


def test_wait_response_publish_reports_failure(client_factory, server, caplog):
    """wait_response bypasses the queue too. A server that rejects the message
    still has to be visible."""
    caplog.set_level(logging.WARNING, logger="tendrl")
    server.post_status = 500

    c = client_factory()
    c.publish({"marker": "sync-rejected"}, tags=["sensor"], wait_response=True)

    assert _wait_for_record(caplog, "DROPPED"), (
        "the server rejected a synchronous publish and the client said nothing"
    )
