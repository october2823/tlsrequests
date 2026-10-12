import asyncio
import inspect
import pytest
from yumeclient import (ALL_IDENTIFIERS, AsyncSession, CookieJar, Profiles, Response,
                         Session, SessionConfigurationError, encode_multipart, find)


def test_profiles_are_upstream_v116_profiles():
    assert len(ALL_IDENTIFIERS) == 83
    assert Profiles.CHROME_152 == "chrome_152"
    assert find("chrome_15") == ["chrome_150", "chrome_150_PSK", "chrome_152", "chrome_152_PSK"]
    with pytest.raises(SessionConfigurationError, match="chrome_152"):
        Session(client_identifier="chrome152")


def test_methods_are_async():
    for method in ("request", "get", "post", "put", "patch", "delete", "head", "close", "reset_connection"):
        assert inspect.iscoroutinefunction(getattr(Session, method))


def test_response_conveniences():
    response = Response(200, {"content-type": ["application/json"]}, {}, b'{"ok":true}', "https://example.test", "HTTP/2.0")
    assert response.ok and response.json() == {"ok": True}
    assert response.http_version == "2"
    assert response["Content-Type"] == "application/json"


def test_cookie_identity_and_domain_selection():
    jar = CookieJar()
    jar.set("token", "parent", domain=".example.com")
    jar.set("token", "host", domain="www.example.com")
    assert len(jar) == 2
    assert jar.to_dict(domain="www.example.com")["token"] == "host"
    assert jar.to_dict(domain="api.example.com")["token"] == "parent"
    jar.update({"token": "updated"}, domain=".example.com")
    assert len(jar) == 2
    assert jar.get("token") == "host"


def test_multipart_order_and_wire_format():
    body, content_type = encode_multipart([("key", "uploads/42"), ("policy", "abc")], [("file", ("blob", b"%PDF", "application/pdf"))], "----WebKitFormBoundary0123456789abcdef")
    assert content_type.endswith("0123456789abcdef")
    assert body.index(b'name="key"') < body.index(b'name="policy"') < body.index(b'name="file"')
    assert b"%PDF\r\n" in body and body.endswith(b"--\r\n")


def test_invalid_http3_proxy_rejected_before_native_call():
    session = Session(proxy="http://localhost:8080", http_version=3)
    with pytest.raises(SessionConfigurationError, match="socks5"):
        session._validate(session.proxy)


@pytest.mark.asyncio
async def test_closed_session_rejects_request():
    session = Session()
    await session.close()
    with pytest.raises(SessionConfigurationError):
        await session.get("https://example.test")


def test_executor_api_exists():
    assert callable(AsyncSession.configure_executor)
