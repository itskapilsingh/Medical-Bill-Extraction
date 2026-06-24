"""client_ip(): X-Forwarded-For is trusted only from a configured proxy."""

from types import SimpleNamespace

from app.core.common.net import client_ip


def _req(peer, xff=None):
    headers = {} if xff is None else {"x-forwarded-for": xff}
    client = SimpleNamespace(host=peer) if peer is not None else None
    return SimpleNamespace(client=client, headers=headers)


def test_ignores_xff_from_untrusted_peer():
    req = _req("203.0.113.9", xff="1.2.3.4")
    assert client_ip(req, set()) == "203.0.113.9"            # nothing trusted
    assert client_ip(req, {"10.0.0.1"}) == "203.0.113.9"     # peer not in set


def test_honors_xff_from_trusted_peer():
    req = _req("10.0.0.1", xff="1.2.3.4, 10.0.0.1")
    assert client_ip(req, {"10.0.0.1"}) == "1.2.3.4"         # left-most original


def test_falls_back_to_peer_without_xff():
    assert client_ip(_req("10.0.0.1"), {"10.0.0.1"}) == "10.0.0.1"


def test_blank_xff_falls_back_to_peer():
    req = _req("10.0.0.1", xff="   ")
    assert client_ip(req, {"10.0.0.1"}) == "10.0.0.1"


def test_unknown_when_no_client():
    assert client_ip(_req(None), set()) == "unknown"
