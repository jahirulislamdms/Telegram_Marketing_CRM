"""Convert a proxy record into the tuple Telethon expects.

Telethon accepts a python-socks style proxy tuple:
    (proxy_type, host, port, rdns, username, password)
"""

from typing import Any


def to_telethon_proxy(proxy: dict[str, Any] | None):
    """Return a Telethon proxy tuple, or None for a direct connection."""
    if not proxy:
        return None

    try:
        from python_socks import ProxyType
    except ImportError:  # pragma: no cover - dependency always present in engine
        return None

    proxy_type_map = {
        "socks5": ProxyType.SOCKS5,
        "http": ProxyType.HTTP,
    }
    ptype = proxy_type_map.get(proxy.get("type", "socks5"))
    if ptype is None:
        # mtproxy and unknown types are not handled by the plain socks tuple.
        return None

    host = proxy["host"]
    port = int(proxy["port"])
    username = proxy.get("username") or None
    password = proxy.get("password") or None
    return (ptype, host, port, True, username, password)
