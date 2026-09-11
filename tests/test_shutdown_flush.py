"""stop() must send what is still queued.

The regression: stop() sets _stop_event and only then enqueues its sentinel, so
the sender's `while not self._stop_event.is_set()` could be false before the
sentinel was ever collected. Anything published just before stop() then sat on
the queue forever. publish() had already returned, so the caller had no way to
notice, and nothing was logged because the thread was gone.

It only bit when the sender happened to be idle, which is why a publish-then-
stop with no pause looked fine.
"""
import time

import pytest


def _publish_then_stop(client_factory, server, label, idle, count):
    c = client_factory()
    if idle:
        time.sleep(idle)
    for i in range(count):
        c.publish({"marker": f"{label}-{i}"}, tags=["sensor"])
    c.stop()

    deadline = time.time() + 10
    expected = {f"{label}-{i}" for i in range(count)}
    while time.time() < deadline:
        if expected <= server.markers():
            return set()
        time.sleep(0.1)
    return expected - server.markers()


def test_stop_flushes_after_the_sender_has_gone_idle(client_factory, server):
    """The case that lost everything: let the loop settle, then publish."""
    lost = _publish_then_stop(client_factory, server, "idle", idle=2.0, count=10)
    assert not lost, f"stop() discarded {len(lost)} queued message(s): {sorted(lost)}"


def test_stop_flushes_a_single_late_message(client_factory, server):
    lost = _publish_then_stop(client_factory, server, "late", idle=3.0, count=1)
    assert not lost, "stop() discarded the one message published before it"


def test_stop_flushes_without_any_pause(client_factory, server):
    """The case that always worked. Kept so a fix for the above cannot break it."""
    lost = _publish_then_stop(client_factory, server, "busy", idle=0, count=10)
    assert not lost, f"stop() discarded {len(lost)} message(s) from a busy sender"


def test_the_flush_still_uses_the_shape_the_server_binds(client_factory, server):
    _publish_then_stop(client_factory, server, "shape", idle=2.0, count=3)
    bad = server.bad_batch_bodies()
    assert not bad, f"the shutdown flush posted a body the server rejects: {bad!r}"
