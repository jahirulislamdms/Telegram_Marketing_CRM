"""Unit tests for the proxy string parser (pure, no DB)."""

import pytest

from app.services.proxies import ProxyParseError, parse_proxy_line


def test_host_port():
    r = parse_proxy_line("1.2.3.4:1080")
    assert r["type"] == "socks5"
    assert r["host"] == "1.2.3.4"
    assert r["port"] == 1080
    assert r["username"] is None
    assert r["password"] is None


def test_host_port_user_pass():
    r = parse_proxy_line("1.2.3.4:1080:alice:secret")
    assert (r["host"], r["port"], r["username"], r["password"]) == (
        "1.2.3.4",
        1080,
        "alice",
        "secret",
    )


def test_socks5_url():
    r = parse_proxy_line("socks5://alice:secret@proxy.example.com:1080")
    assert r["type"] == "socks5"
    assert r["host"] == "proxy.example.com"
    assert r["port"] == 1080
    assert r["username"] == "alice"
    assert r["password"] == "secret"


def test_socks5h_scheme_maps_to_socks5():
    assert parse_proxy_line("socks5h://h:9")["type"] == "socks5"


def test_http_url():
    r = parse_proxy_line("http://h:8080")
    assert r["type"] == "http"
    assert r["port"] == 8080


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "nonsense",
        "host:notaport",
        "host:70000",
        "host:0",
        "ftp://h:21",
        "a:b:c",
    ],
)
def test_invalid(bad):
    with pytest.raises(ProxyParseError):
        parse_proxy_line(bad)
