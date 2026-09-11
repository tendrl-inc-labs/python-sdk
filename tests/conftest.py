"""Test harness for the Tendrl Python SDK.

Everything here runs against a local recording HTTP server, not a Tendrl stack.
That is deliberate: a suite that needs a live backend is a suite that gets
skipped, and a skipped suite reports green while testing nothing.

The server speaks the three routes the client actually uses — `HEAD /` for the
connectivity probe and `POST /entities/{message,messages,status}` — and records
every request so a test can assert on what was really sent.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):        # keep pytest output clean
        pass

    @property
    def _rec(self):
        return self.server.recorder

    def do_HEAD(self):
        self.send_response(self._rec.head_status)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = raw.decode("utf-8", "replace")
        self._rec.record(self.path, body, dict(self.headers))

        status = self._rec.post_status
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        payload = json.dumps({"code": status, "content": []}).encode()
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class Recorder:
    """A tiny stand-in for Contact that remembers what it was sent."""

    def __init__(self):
        self.requests = []           # list of (path, body, headers)
        self.post_status = 200
        self.head_status = 200
        self._lock = threading.Lock()

    def record(self, path, body, headers):
        with self._lock:
            self.requests.append((path, body, headers))

    def bad_batch_bodies(self):
        """Batch posts whose shape the real server would reject.

        Contact's WriteMessages does `var messages []models.Message` followed by
        Bind, so the batch endpoint takes a bare JSON array. Anything else is a
        400 and the messages are gone.
        """
        bad = []
        with self._lock:
            reqs = list(self.requests)
        for path, body, _ in reqs:
            if path.rstrip("/").endswith("/messages") and not isinstance(body, list):
                bad.append((path, body))
        return bad

    # -- assertions the tests actually care about ---------------------------
    def messages(self):
        """Every message body posted to a message route, flattened."""
        out = []
        with self._lock:
            reqs = list(self.requests)
        for path, body, _ in reqs:
            if "message" not in path:
                continue
            if isinstance(body, list):
                # The batch endpoint. Contact binds []models.Message, so a bare
                # array is the only shape it accepts.
                out.extend(body)
            elif isinstance(body, dict):
                # A single publish posts one message on its own object.
                # Deliberately NOT unwrapping {"messages": [...]} here: this
                # recorder previously accepted that envelope, which is how the
                # client shipped a batch body the real server rejects while the
                # suite stayed green. The harness must not be more permissive
                # than the server.
                out.append(body)
        return out

    def markers(self):
        found = set()
        for m in self.messages():
            data = (m or {}).get("data")
            if isinstance(data, dict) and "marker" in data:
                found.add(data["marker"])
        return found

    def wait_for_marker(self, marker, timeout=15.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if marker in self.markers():
                return True
            time.sleep(0.1)
        return False


@pytest.fixture
def server():
    """A recording server on an ephemeral port. Yields the Recorder."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    rec = Recorder()
    httpd.recorder = rec
    rec.url = f"http://127.0.0.1:{httpd.server_address[1]}"
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield rec
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture
def client_factory(server, monkeypatch):
    """Build clients pointed at the recording server; stop them on teardown."""
    monkeypatch.setenv("TENDRL_APP_URL", server.url)
    made = []

    def _make(**kwargs):
        from tendrl import Client
        kwargs.setdefault("api_key", "test-key")
        c = Client(**kwargs)
        made.append(c)
        c.start()
        return c

    yield _make

    for c in made:
        try:
            c.stop()
        except Exception:
            pass


# A dead port nothing is listening on — used for the failure-path tests.
DEAD_URL = "http://127.0.0.1:9"
