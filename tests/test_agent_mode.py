"""Agent mode has to actually connect.

The regression: _connect_to_agent was defined and called from nowhere, so the
AF_UNIX socket was never connected. Every send in agent mode went to an
unconnected socket and failed silently, while the client looked healthy. The
nano agent listens on that same path and decodes a JSON stream, so the only
thing missing was the call.

These run against a stub Unix socket server, not the real agent.
"""
import json
import os
import shutil
import socket
import tempfile
import threading
import time

import pytest


class StubAgent:
    """A Unix socket server that decodes the JSON stream the client writes."""

    def __init__(self, path):
        self.path = path
        self.received = []
        self._lock = threading.Lock()
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(path)
        self._sock.listen(4)
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while not self._stop:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._read, args=(conn,), daemon=True).start()

    def _read(self, conn):
        buf = b""
        decoder = json.JSONDecoder()
        while not self._stop:
            try:
                chunk = conn.recv(4096)
            except OSError:
                return
            if not chunk:
                return
            buf += chunk
            text = buf.decode("utf-8", "replace").lstrip()
            while text:
                try:
                    obj, end = decoder.raw_decode(text)
                except ValueError:
                    break
                with self._lock:
                    self.received.append(obj)
                text = text[end:].lstrip()
            buf = text.encode("utf-8")

    def markers(self):
        with self._lock:
            out = set()
            for m in self.received:
                data = (m or {}).get("data")
                if isinstance(data, dict) and "marker" in data:
                    out.add(data["marker"])
            return out

    def wait_for_marker(self, marker, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if marker in self.markers():
                return True
            time.sleep(0.05)
        return False

    def close(self):
        self._stop = True
        try:
            self._sock.close()
        except OSError:
            pass
        try:
            os.unlink(self.path)
        except OSError:
            pass


@pytest.fixture
def sock_dir():
    """A short directory. AF_UNIX addresses are length-limited, and pytest's
    tmp_path is comfortably over it."""
    d = tempfile.mkdtemp(prefix="tdl", dir="/tmp")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def stub_agent(sock_dir):
    agent = StubAgent(os.path.join(sock_dir, "a.sock"))
    yield agent
    agent.close()


@pytest.fixture
def agent_client(stub_agent, monkeypatch):
    from tendrl import Client
    monkeypatch.setattr(Client, "_get_socket_path", lambda self: stub_agent.path)
    made = []

    def _make(**kwargs):
        c = Client(mode="agent", **kwargs)
        made.append(c)
        return c

    yield _make
    for c in made:
        try:
            c.stop()
        except Exception:
            pass


def test_start_connects_the_socket(agent_client, stub_agent):
    c = agent_client()
    c.start()
    assert c.sock.getpeername() == stub_agent.path, (
        "start() returned without connecting the agent socket"
    )


def test_a_published_message_reaches_the_agent(agent_client, stub_agent):
    c = agent_client()
    c.start()
    c.publish({"marker": "to-the-agent"}, tags=["sensor"])
    assert stub_agent.wait_for_marker("to-the-agent"), (
        "the agent never received the message"
    )


def test_no_agent_listening_is_reported_not_swallowed(monkeypatch, sock_dir):
    """A missing agent must fail loudly at start(), not silently at every send."""
    from tendrl import Client
    missing = os.path.join(sock_dir, "nope.sock")
    monkeypatch.setattr(Client, "_get_socket_path", lambda self: missing)

    c = Client(mode="agent")
    with pytest.raises(ConnectionError):
        c.start()
