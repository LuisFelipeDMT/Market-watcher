"""Tests for the SSRF guard."""

from __future__ import annotations

import pytest

from app.security import SSRFError, is_public_ip, validate_public_url


def _resolver_to(ip: str):
    def _resolve(host, port):
        return [(2, 1, 6, "", (ip, port or 443))]

    return _resolve


def test_public_vs_private_classification():
    assert is_public_ip("8.8.8.8") is True
    assert is_public_ip("1.1.1.1") is True
    for blocked in ("127.0.0.1", "10.0.0.1", "192.168.1.1", "169.254.169.254", "::1"):
        assert is_public_ip(blocked) is False


def test_rejects_non_http_scheme():
    with pytest.raises(SSRFError):
        validate_public_url("file:///etc/passwd")
    with pytest.raises(SSRFError):
        validate_public_url("ftp://example.com/x")


def test_rejects_ip_literal_in_private_range():
    with pytest.raises(SSRFError):
        validate_public_url("http://127.0.0.1/admin")
    with pytest.raises(SSRFError):
        validate_public_url("http://169.254.169.254/latest/meta-data/")


def test_allows_public_ip_literal():
    assert validate_public_url("https://8.8.8.8/") == "https://8.8.8.8/"


def test_hostname_resolving_to_private_is_blocked():
    with pytest.raises(SSRFError):
        validate_public_url(
            "https://evil.example.com/x", resolver=_resolver_to("10.1.2.3")
        )


def test_hostname_resolving_to_public_is_allowed():
    url = "https://api.example.com/data"
    assert validate_public_url(url, resolver=_resolver_to("93.184.216.34")) == url
