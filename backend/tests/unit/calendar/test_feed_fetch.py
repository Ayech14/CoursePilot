"""The fetcher refuses links that could reach private networks, and caps what it downloads."""

import socket
from typing import Any

import pytest

from app.services import feed_fetch
from app.services.feed_fetch import FeedFetchError, fetch_calendar, is_public_address, normalize_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://eclass.yorku.ca/calendar/export.php?t=abc",
            "https://eclass.yorku.ca/calendar/export.php?t=abc",
        ),
        ("  webcal://example.com/a.ics ", "https://example.com/a.ics"),
        ("WEBCAL://example.com/a.ics", "https://example.com/a.ics"),
        ("https://example.com:443/a.ics", "https://example.com:443/a.ics"),
    ],
)
def test_accepted_links(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "http://example.com/a.ics",
        "ftp://example.com/a.ics",
        "file:///etc/passwd",
        "https:///a.ics",
        "https://user:pw@example.com/a.ics",
        "https://example.com:8443/a.ics",
        "example.com/a.ics",
    ],
)
def test_refused_links(raw: str) -> None:
    with pytest.raises(FeedFetchError):
        normalize_url(raw)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",  # Cloud metadata services live here.
        "100.64.0.1",
        "0.0.0.0",  # noqa: S104  # A value under test, not a bind address.
        "224.0.0.1",
        "::1",
        "fd00::1",
        "fe80::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
    ],
)
def test_private_addresses_are_not_public(address: str) -> None:
    assert not is_public_address(address)


@pytest.mark.parametrize("address", ["8.8.8.8", "130.63.236.1", "2606:4700:4700::1111"])
def test_public_addresses(address: str) -> None:
    assert is_public_address(address)


def _resolve_to(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, list[str]]) -> None:
    def fake(host: str, *_: Any, **__: Any) -> list[Any]:
        if host not in mapping:
            raise socket.gaierror("unknown")
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 443)) for ip in mapping[host]]

    monkeypatch.setattr(socket, "getaddrinfo", fake)


def test_a_host_with_any_private_address_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolve_to(monkeypatch, {"mixed.example": ["93.184.216.34", "10.0.0.1"]})
    with pytest.raises(FeedFetchError, match="private network"):
        feed_fetch.public_address_for("mixed.example")


def test_an_unknown_host_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolve_to(monkeypatch, {})
    with pytest.raises(FeedFetchError, match="could not find"):
        feed_fetch.public_address_for("nowhere.example")


class FakeResponse:
    def __init__(self, status: int, body: bytes = b"", location: str | None = None) -> None:
        self.status = status
        self._body = body
        self._location = location

    def getheader(self, name: str) -> str | None:
        return self._location if name == "Location" else None

    def read(self, size: int) -> bytes:
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk


class FakeServer:
    """Stands in for the network: answers by host, and records where it was asked to connect."""

    def __init__(self, answers: dict[str, FakeResponse]) -> None:
        self.answers = answers
        self.connections: list[tuple[str, str, str]] = []

    def connection(self, host: str, address: str) -> Any:
        server = self

        class Connection:
            def request(self, method: str, target: str, headers: dict[str, str]) -> None:
                server.connections.append((host, address, target))

            def getresponse(self) -> FakeResponse:
                return server.answers[host]

            def close(self) -> None:
                pass

        return Connection()


def _serve(monkeypatch: pytest.MonkeyPatch, answers: dict[str, FakeResponse]) -> FakeServer:
    server = FakeServer(answers)
    monkeypatch.setattr(feed_fetch, "_PinnedConnection", server.connection)
    return server


def test_downloads_from_the_checked_address(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolve_to(monkeypatch, {"cal.example": ["93.184.216.34"]})
    server = _serve(monkeypatch, {"cal.example": FakeResponse(200, b"BEGIN:VCALENDAR")})
    assert fetch_calendar("webcal://cal.example/x.ics?t=1") == b"BEGIN:VCALENDAR"
    assert server.connections == [("cal.example", "93.184.216.34", "/x.ics?t=1")]


def test_redirects_are_checked_again(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolve_to(monkeypatch, {"cal.example": ["93.184.216.34"], "inside.example": ["10.1.1.1"]})
    _serve(monkeypatch, {"cal.example": FakeResponse(302, location="https://inside.example/")})
    with pytest.raises(FeedFetchError, match="private network"):
        fetch_calendar("https://cal.example/x.ics")


def test_redirect_to_plain_http_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolve_to(monkeypatch, {"cal.example": ["93.184.216.34"]})
    _serve(monkeypatch, {"cal.example": FakeResponse(301, location="http://cal.example/x.ics")})
    with pytest.raises(FeedFetchError, match="https"):
        fetch_calendar("https://cal.example/x.ics")


def test_a_followed_redirect_works(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolve_to(monkeypatch, {"a.example": ["93.184.216.34"], "b.example": ["93.184.216.35"]})
    _serve(
        monkeypatch,
        {
            "a.example": FakeResponse(302, location="https://b.example/final.ics"),
            "b.example": FakeResponse(200, b"ok"),
        },
    )
    assert fetch_calendar("https://a.example/x.ics") == b"ok"


def test_redirect_loops_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolve_to(monkeypatch, {"a.example": ["93.184.216.34"]})
    _serve(monkeypatch, {"a.example": FakeResponse(302, location="/again")})
    with pytest.raises(FeedFetchError, match="too many"):
        fetch_calendar("https://a.example/x.ics")


def test_error_statuses_are_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolve_to(monkeypatch, {"a.example": ["93.184.216.34"]})
    _serve(monkeypatch, {"a.example": FakeResponse(403)})
    with pytest.raises(FeedFetchError, match="403"):
        fetch_calendar("https://a.example/x.ics")


def test_oversized_downloads_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolve_to(monkeypatch, {"a.example": ["93.184.216.34"]})
    monkeypatch.setattr(feed_fetch, "MAX_BYTES", 100)
    _serve(monkeypatch, {"a.example": FakeResponse(200, b"x" * 101)})
    with pytest.raises(FeedFetchError, match="too large"):
        fetch_calendar("https://a.example/x.ics")


def test_network_failures_are_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    _resolve_to(monkeypatch, {"a.example": ["93.184.216.34"]})

    def broken(host: str, address: str) -> Any:
        class Connection:
            def request(self, *args: Any, **kwargs: Any) -> None:
                raise ConnectionRefusedError

            def close(self) -> None:
                pass

        return Connection()

    monkeypatch.setattr(feed_fetch, "_PinnedConnection", broken)
    with pytest.raises(FeedFetchError, match="could not reach"):
        fetch_calendar("https://a.example/x.ics")
