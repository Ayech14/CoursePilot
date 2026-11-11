"""Downloads a calendar from a link the student pasted, without letting that link reach inside.

Fetching a user-supplied URL from the server is a classic way to probe private networks. So:

- Only HTTPS on the default port. `webcal://` links, which calendar apps use, are read as HTTPS.
- Every address the host name resolves to must be a public one.
- The connection goes to the address that was checked, so a second DNS answer cannot swap in a
  private one between the check and the request.
- Redirects are followed by hand, each one checked the same way, at most three.
- Size and total time are capped, so a hostile server cannot tie up a worker.
"""

import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit

MAX_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = 10.0
TOTAL_SECONDS = 20.0
MAX_REDIRECTS = 3
_USER_AGENT = "CoursePilot calendar sync"


class FeedFetchError(Exception):
    """A problem worth telling the student about, in words they can act on."""


def normalize_url(raw: str) -> str:
    url = raw.strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://") :]
    parts = urlsplit(url)
    if parts.scheme.lower() != "https":
        raise FeedFetchError("Use a link that starts with https:// or webcal://.")
    if not parts.hostname:
        raise FeedFetchError("That link has no website in it.")
    if parts.username or parts.password:
        raise FeedFetchError("Links with a user name or password in them are not supported.")
    if parts.port not in (None, 443):
        raise FeedFetchError("Only standard HTTPS links are supported.")
    return url


def is_public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def public_address_for(host: str) -> str:
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FeedFetchError("We could not find that website.") from exc
    addresses = [str(info[4][0]) for info in infos]
    if not addresses or not all(is_public_address(a) for a in addresses):
        raise FeedFetchError("That link points to a private network address.")
    return addresses[0]


class _PinnedConnection(http.client.HTTPSConnection):
    """Connects to an address chosen in advance, while still verifying the site's certificate."""

    def __init__(self, host: str, address: str) -> None:
        super().__init__(host, 443, timeout=TIMEOUT_SECONDS, context=ssl.create_default_context())
        self._address = address

    def connect(self) -> None:
        raw = socket.create_connection((self._address, 443), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)  # type: ignore[attr-defined]


def _read_capped(response: http.client.HTTPResponse, started: float) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := response.read(64 * 1024):
        size += len(chunk)
        if size > MAX_BYTES:
            raise FeedFetchError("That calendar is too large to import (over 5 MB).")
        if time.monotonic() - started > TOTAL_SECONDS:
            raise FeedFetchError("That calendar took too long to download.")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_calendar(url: str) -> bytes:
    started = time.monotonic()
    current = normalize_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        parts = urlsplit(current)
        host = parts.hostname
        assert host is not None  # noqa: S101  # normalize_url guarantees it.
        connection = _PinnedConnection(host, public_address_for(host))
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        try:
            connection.request(
                "GET", target, headers={"User-Agent": _USER_AGENT, "Accept": "text/calendar"}
            )
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise FeedFetchError("That link redirected nowhere.")
                current = normalize_url(urljoin(current, location))
                continue
            if response.status != 200:
                raise FeedFetchError(
                    f"The calendar's website answered with error {response.status}."
                )
            return _read_capped(response, started)
        except (OSError, http.client.HTTPException) as exc:
            raise FeedFetchError("We could not reach that calendar. Check the link.") from exc
        finally:
            connection.close()
    raise FeedFetchError("That link redirected too many times.")
