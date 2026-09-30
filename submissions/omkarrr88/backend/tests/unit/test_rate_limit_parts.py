"""Rate-limit windows and the client IP behind a proxy."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.ratelimit.deps import _duration, client_ip
from app.ratelimit.limiter import window_start
from tests.conftest import make_test_settings


def test_windows_are_aligned() -> None:
    now = datetime(2026, 9, 30, 10, 17, 42, 500_000, tzinfo=UTC)
    assert window_start(now, 60) == datetime(2026, 9, 30, 10, 17, tzinfo=UTC)
    assert window_start(now, 86_400) == datetime(2026, 9, 30, tzinfo=UTC)


def _request(peer: str, forwarded: str | None = None) -> SimpleNamespace:
    headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def test_without_a_trusted_proxy_the_peer_address_is_used() -> None:
    settings = make_test_settings(trust_proxy_headers=False)
    request = _request("10.0.0.5", forwarded="1.2.3.4")
    assert client_ip(request, settings) == "10.0.0.5"  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("forwarded", "proxies", "expected"),
    [
        ("203.0.113.9", 1, "203.0.113.9"),
        ("6.6.6.6, 203.0.113.9", 1, "203.0.113.9"),  # the client made up the first entry
        ("6.6.6.6, 203.0.113.9, 10.1.1.1", 2, "203.0.113.9"),
        ("2001:db8::1", 1, "2001:db8::1"),
        ("", 1, "10.0.0.5"),
        ("not-an-ip", 1, "10.0.0.5"),
        ("203.0.113.9", 2, "10.0.0.5"),  # fewer entries than proxies: do not guess
    ],
)
def test_behind_a_proxy_the_right_most_untrusted_entry_is_used(
    forwarded: str, proxies: int, expected: str
) -> None:
    settings = make_test_settings(trust_proxy_headers=True, trusted_proxy_count=proxies)
    assert client_ip(_request("10.0.0.5", forwarded), settings) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(1, "1 second"), (42, "42 seconds"), (119, "119 seconds"), (150, "2 minutes"),
     (3599, "60 minutes"), (7200, "2 hours"), (86_399, "24 hours")],
)  # fmt: skip
def test_waits_are_worded_in_a_sensible_unit(seconds: int, text: str) -> None:
    assert _duration(seconds) == text
