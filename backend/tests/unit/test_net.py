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


def test_honors_real_client_from_trusted_peer():
    # Single trusted proxy appends the real client; we trust the right-most entry.
    req = _req("10.0.0.1", xff="203.0.113.5")
    assert client_ip(req, {"10.0.0.1"}) == "203.0.113.5"


def test_client_prepended_spoof_is_ignored():
    # Attacker pre-sets X-Forwarded-For; the proxy appends their REAL ip. We must
    # return the appended (right-most) value, never the spoofed left-most one.
    req = _req("10.0.0.1", xff="9.9.9.9, 203.0.113.5")
    assert client_ip(req, {"10.0.0.1"}) == "203.0.113.5"


def test_skips_chained_trusted_proxies():
    # client -> proxy(203 added) -> proxy(10.0.0.2 added) -> app(peer 10.0.0.1).
    req = _req("10.0.0.1", xff="9.9.9.9, 203.0.113.5, 10.0.0.2")
    assert client_ip(req, {"10.0.0.1", "10.0.0.2"}) == "203.0.113.5"


def test_all_entries_trusted_falls_back_to_peer():
    req = _req("10.0.0.1", xff="10.0.0.2, 10.0.0.1")
    assert client_ip(req, {"10.0.0.1", "10.0.0.2"}) == "10.0.0.1"


def test_falls_back_to_peer_without_xff():
    assert client_ip(_req("10.0.0.1"), {"10.0.0.1"}) == "10.0.0.1"


def test_blank_xff_falls_back_to_peer():
    req = _req("10.0.0.1", xff="   ")
    assert client_ip(req, {"10.0.0.1"}) == "10.0.0.1"


def test_unknown_when_no_client():
    assert client_ip(_req(None), set()) == "unknown"
