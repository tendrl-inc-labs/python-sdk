"""The core promise: a published message reaches the server.

These assert on what the recording server RECEIVED, never on the absence of an
exception. publish() is asynchronous by design and returns "" immediately, so
"it didn't raise" says nothing about delivery — that gap is exactly how silent
drops went unnoticed.
"""


def test_publish_reaches_the_server(client_factory, server):
    c = client_factory()
    c.publish({"marker": "basic", "temperature": 23.5}, tags=["sensor"])
    assert server.wait_for_marker("basic"), (
        "publish() returned but the server never received the message"
    )


def test_payload_survives_the_round_trip(client_factory, server):
    c = client_factory()
    c.publish({"marker": "payload", "temperature": 23.5, "humidity": 65}, tags=["sensor"])
    assert server.wait_for_marker("payload")

    sent = [m for m in server.messages() if (m.get("data") or {}).get("marker") == "payload"]
    assert sent, "message recorded but could not be found again"
    data = sent[0]["data"]
    assert data["temperature"] == 23.5
    assert data["humidity"] == 65


def test_tags_are_sent_as_context(client_factory, server):
    c = client_factory()
    c.publish({"marker": "tagged"}, tags=["sensor", "environment"])
    assert server.wait_for_marker("tagged")

    sent = [m for m in server.messages() if (m.get("data") or {}).get("marker") == "tagged"][0]
    context = sent.get("context") or {}
    assert context.get("tags") == ["sensor", "environment"], (
        f"tags did not arrive as context.tags — got {context!r}. Tags are what route "
        f"a message to flows and connectors, so losing them silently breaks routing."
    )


def test_msg_type_is_publish(client_factory, server):
    c = client_factory()
    c.publish({"marker": "typed"}, tags=["sensor"])
    assert server.wait_for_marker("typed")
    sent = [m for m in server.messages() if (m.get("data") or {}).get("marker") == "typed"][0]
    assert sent.get("msg_type") == "publish"


def test_many_messages_all_arrive(client_factory, server):
    """Batching must not drop anything on the floor."""
    c = client_factory()
    for i in range(25):
        c.publish({"marker": f"bulk-{i}"}, tags=["sensor"])

    for i in range(25):
        assert server.wait_for_marker(f"bulk-{i}"), f"bulk-{i} never arrived"


def test_bearer_token_is_sent(client_factory, server):
    c = client_factory(api_key="sekrit-key")
    c.publish({"marker": "auth"}, tags=["sensor"])
    assert server.wait_for_marker("auth")

    auth = [h.get("Authorization") for _, _, h in server.requests if h.get("Authorization")]
    assert auth, "no Authorization header was ever sent"
    assert auth[0] == "Bearer sekrit-key"
