import asyncio
import inspect
import pytest
from tlsrequests import Session, TLSClientError, Response


def test_methods_are_async():
    for method in ("request", "get", "post", "put", "patch", "delete", "head", "close"):
        assert inspect.iscoroutinefunction(getattr(Session, method))


def test_response_helpers():
    r = Response(200, {"content-type": ["application/json"]}, {}, b'{"ok":true}', "https://example.test")
    assert r.ok and r.json() == {"ok": True} and r["content-type"] == ["application/json"]


@pytest.mark.asyncio
async def test_closed_session_rejects_request():
    session = Session()
    await session.close()
    with pytest.raises(TLSClientError):
        await session.get("https://example.test")
