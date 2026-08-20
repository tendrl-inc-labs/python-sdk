"""Where the client points, and how TENDRL_APP_URL is interpreted.

The published 0.1.6 hardcoded https://app.tendrl.com/api with no env var and no
kwarg, so it could only ever talk to production and could not be tried locally.
These lock in the escape hatch, and lock the normalisation to the same rule the
Go and nano-agent clients use so one variable works for all of them.
"""
import pytest

from tendrl import Client
from tendrl.client import APIException


def _base_url(c):
    return str(c.client.base_url).rstrip("/")


@pytest.mark.parametrize("value,expected", [
    ("http://localhost:8000",      "http://localhost:8000/api"),
    ("http://localhost:8000/",     "http://localhost:8000/api"),
    ("http://localhost:8000/api",  "http://localhost:8000/api"),
    ("http://localhost:8000/api/", "http://localhost:8000/api"),
])
def test_env_var_accepts_origin_or_api_url(monkeypatch, value, expected):
    """A bare origin gets /api appended; a URL that already ends in /api is left
    alone. Without the second case, sharing TENDRL_APP_URL with the nano-agent
    (which wants the /api form) produces .../api/api."""
    monkeypatch.setenv("TENDRL_APP_URL", value)
    c = Client(api_key="k")
    assert _base_url(c) == expected


def test_explicit_arg_beats_the_env_var(monkeypatch):
    monkeypatch.setenv("TENDRL_APP_URL", "http://from-env:1111")
    c = Client(api_key="k", app_url="http://from-arg:2222")
    assert _base_url(c) == "http://from-arg:2222/api"


def test_defaults_to_production(monkeypatch):
    monkeypatch.delenv("TENDRL_APP_URL", raising=False)
    c = Client(api_key="k")
    assert _base_url(c) == "https://app.tendrl.com/api"


def test_missing_api_key_raises(monkeypatch):
    """Documented behaviour: with no key and no TENDRL_KEY, the constructor fails
    immediately rather than at first send."""
    monkeypatch.delenv("TENDRL_KEY", raising=False)
    with pytest.raises(APIException):
        Client()


def test_api_key_from_env(monkeypatch):
    """TENDRL_KEY is accepted in place of the api_key argument.

    Asserted through the Authorization header the client will actually send —
    the key is baked into the httpx client's headers and never kept as an
    attribute, so there is nothing else to check that reflects reality.
    """
    monkeypatch.setenv("TENDRL_KEY", "from-env-key")
    c = Client()
    assert c.client.headers.get("Authorization") == "Bearer from-env-key"
