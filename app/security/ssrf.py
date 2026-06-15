"""SSRF guard for outbound requests in the untrusted analysis zone.

The analysis zone fetches third-party/scraped content; an attacker-influenced
URL must not be able to reach internal services (cloud metadata, localhost,
private ranges). :func:`validate_public_url` rejects non-HTTP schemes and any
host that resolves to a non-public address. The DNS resolver is injectable so
the classification logic is testable without the network.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Callable
from urllib.parse import urlparse

# (host, port) -> list of getaddrinfo-style tuples.
Resolver = Callable[[str, int | None], list]


class SSRFError(ValueError):
    """Raised when a URL is unsafe to fetch from the untrusted zone."""


def is_public_ip(ip: str) -> bool:
    """True only for globally-routable unicast addresses."""
    addr = ipaddress.ip_address(ip)
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local  # e.g. 169.254.0.0/16 (cloud metadata)
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def validate_public_url(
    url: str,
    *,
    allowed_schemes: tuple[str, ...] = ("https", "http"),
    resolver: Resolver = socket.getaddrinfo,
) -> str:
    """Return ``url`` if safe to fetch; otherwise raise :class:`SSRFError`."""
    parsed = urlparse(url)
    if parsed.scheme not in allowed_schemes:
        raise SSRFError(f"Scheme not allowed: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise SSRFError("URL has no host")

    # Host given as an IP literal: check it directly.
    try:
        if not is_public_ip(host):
            raise SSRFError(f"Non-public address: {host}")
        return url
    except ValueError:
        pass  # not a literal IP — resolve the name below

    try:
        infos = resolver(host, parsed.port)
    except Exception as exc:  # resolution failure is treated as unsafe
        raise SSRFError(f"Could not resolve host {host!r}: {exc}") from exc

    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise SSRFError(f"No addresses for host {host!r}")
    for ip in addresses:
        if not is_public_ip(ip):
            raise SSRFError(f"Host {host!r} resolves to non-public {ip}")
    return url
