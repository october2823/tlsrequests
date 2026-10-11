"""Async requests-like API backed by bogdanfinn/tls-client's Go implementation."""
from __future__ import annotations

import asyncio
import ctypes
import json
import os
import platform
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode

__all__ = ["Session", "Response", "TLSClientError", "RequestError", "close_runtime"]

class TLSClientError(RuntimeError):
    """Base exception for native TLS client failures."""

class RequestError(TLSClientError):
    """The underlying tls-client request failed."""

_MAX_WORKERS = max(4, min(32, (os.cpu_count() or 4) * 2))
_executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="tlsrequests")
_executor_lock = threading.Lock()
_library: ctypes.CDLL | None = None


def _library_path() -> Path:
    configured = os.getenv("TLSREQUESTS_LIBRARY")
    if configured:
        return Path(configured)
    suffix = {"Windows": ".dll", "Darwin": ".dylib"}.get(platform.system(), ".so")
    return Path(__file__).with_name("tlsrequests" + suffix)


def _native() -> ctypes.CDLL:
    global _library
    with _executor_lock:
        if _library is None:
            path = _library_path()
            if not path.is_file():
                raise TLSClientError(f"Native library not found: {path}. Build native/ with go build -buildmode=c-shared.")
            lib = ctypes.CDLL(str(path))
            lib.tlsrequests_call.argtypes = [ctypes.c_char_p]
            lib.tlsrequests_call.restype = ctypes.c_void_p
            lib.tlsrequests_close.argtypes = [ctypes.c_char_p]
            lib.tlsrequests_close.restype = None
            lib.tlsrequests_free.argtypes = [ctypes.c_void_p]
            lib.tlsrequests_free.restype = None
            _library = lib
        return _library


def _call(payload: dict[str, Any]) -> dict[str, Any]:
    lib = _native()
    ptr = lib.tlsrequests_call(json.dumps(payload, separators=(",", ":")).encode())
    if not ptr:
        raise RequestError("native client returned a null response")
    try:
        result = json.loads(ctypes.string_at(ptr).decode("utf-8"))
    finally:
        lib.tlsrequests_free(ptr)
    if result.get("status", 0) == 0:
        raise RequestError(result.get("body", "request failed"))
    return result


@dataclass(slots=True)
class Response:
    status_code: int
    headers: dict[str, list[str]]
    cookies: dict[str, str]
    content: bytes
    url: str
    protocol: str = ""
    session_id: str | None = None

    @property
    def status(self) -> int: return self.status_code
    @property
    def text(self) -> str: return self.content.decode("utf-8", errors="replace")
    @property
    def ok(self) -> bool: return 200 <= self.status_code < 400
    @property
    def encoding(self) -> str: return "utf-8"
    def json(self) -> Any: return json.loads(self.text)
    def raise_for_status(self) -> None:
        if not self.ok:
            raise RequestError(f"HTTP {self.status_code} for {self.url}")
    def __getitem__(self, key: str) -> list[str]: return self.headers[key.lower()]


class Session:
    """Reusable async session. Requests are executed on a shared bounded worker pool."""
    def __init__(self, *, client_identifier: str = "", headers: Mapping[str, str] | None = None,
                 proxy: str | None = None, timeout: float = 30.0, follow_redirects: bool = True,
                 verify: bool = True, cookies: Mapping[str, str] | None = None,
                 max_workers: int | None = None, **options: Any) -> None:
        self.client_identifier = client_identifier
        self.headers = dict(headers or {})
        self.proxy = proxy
        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self.verify = verify
        self.cookies = dict(cookies or {})
        self.options = options
        self._session_id = os.urandom(16).hex()
        self._closed = False
        self._state_lock = asyncio.Lock()
        self._active: set[asyncio.Task[Any]] = set()

    async def __aenter__(self) -> "Session":
        if self._closed: raise TLSClientError("session is closed")
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def close(self) -> None:
        async with self._state_lock:
            if self._closed: return
            self._closed = True
            active = tuple(self._active)
        if active:
            await asyncio.gather(*(asyncio.shield(t) for t in active), return_exceptions=True)
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(_executor, self._close_native)
        except TLSClientError:
            pass

    def _close_native(self) -> None:
        lib = _native()
        lib.tlsrequests_close(self._session_id.encode())

    async def request(self, method: str, url: str, *, params: Mapping[str, Any] | None = None,
                      data: Any = None, json: Any = None, headers: Mapping[str, str] | None = None,
                      cookies: Mapping[str, str] | None = None, timeout: float | None = None,
                      allow_redirects: bool | None = None, **kwargs: Any) -> Response:
        async with self._state_lock:
            if self._closed: raise TLSClientError("session is closed")
            task = asyncio.current_task()
            if task: self._active.add(task)
        try:
            request_url = url
            if params:
                request_url += ("&" if "?" in request_url else "?") + urlencode(params, doseq=True)
            merged_headers = dict(self.headers)
            merged_headers.update(headers or {})
            body: str | None = None
            byte_request = False
            if json is not None:
                body = __import__("json").dumps(json, separators=(",", ":"))
                merged_headers.setdefault("Content-Type", "application/json")
            elif data is not None:
                if isinstance(data, bytes):
                    import base64
                    body, byte_request = base64.b64encode(data).decode("ascii"), True
                elif isinstance(data, (dict, list)):
                    body = urlencode(data, doseq=True)
                    merged_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
                else: body = str(data)
            jar = dict(self.cookies); jar.update(cookies or {})
            payload: dict[str, Any] = {
                "requestMethod": method.upper(), "requestUrl": request_url,
                "tlsClientIdentifier": self.client_identifier, "sessionId": self._session_id,
                "headers": merged_headers, "requestBody": body, "requestCookies": [
                    {"name": k, "value": v} for k, v in jar.items()],
                "timeoutMilliseconds": int((timeout if timeout is not None else self.timeout) * 1000),
                "followRedirects": self.follow_redirects if allow_redirects is None else allow_redirects,
                "insecureSkipVerify": not self.verify, "isByteRequest": byte_request,
                "isByteResponse": True, "withCustomCookieJar": True,
            }
            if self.proxy is not None: payload["proxyUrl"] = self.proxy
            for key, value in self.options.items():
                if key in {"force_http1", "disable_http3", "disable_session_tickets", "with_protocol_racing",
                           "disable_ipv6", "disable_ipv4", "with_random_tls_extension_order", "with_debug"}:
                    payload[{"force_http1":"forceHttp1", "disable_http3":"disableHttp3", "disable_session_tickets":"disableSessionTickets",
                             "with_protocol_racing":"withProtocolRacing", "disable_ipv6":"disableIPV6", "disable_ipv4":"disableIPV4",
                             "with_random_tls_extension_order":"withRandomTLSExtensionOrder", "with_debug":"withDebug"}[key]] = bool(value)
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(_executor, _call, payload)
            try:
                result = await asyncio.shield(future)
            except asyncio.CancelledError:
                try: await asyncio.shield(future)
                finally: raise
            import base64
            encoded_body = result.get("body", "")
            if encoded_body.startswith("data:") and ";base64," in encoded_body:
                encoded_body = encoded_body.split(";base64,", 1)[1]
            content = base64.b64decode(encoded_body)
            self.cookies.update(result.get("cookies") or {})
            return Response(int(result.get("status", 0)), result.get("headers") or {},
                            result.get("cookies") or {}, content, result.get("target", request_url),
                            result.get("usedProtocol", ""), result.get("sessionId") or self._session_id)
        finally:
            if task:
                async with self._state_lock: self._active.discard(task)

    async def get(self, url: str, **kwargs: Any) -> Response: return await self.request("GET", url, **kwargs)
    async def head(self, url: str, **kwargs: Any) -> Response: return await self.request("HEAD", url, **kwargs)
    async def post(self, url: str, **kwargs: Any) -> Response: return await self.request("POST", url, **kwargs)
    async def put(self, url: str, **kwargs: Any) -> Response: return await self.request("PUT", url, **kwargs)
    async def patch(self, url: str, **kwargs: Any) -> Response: return await self.request("PATCH", url, **kwargs)
    async def delete(self, url: str, **kwargs: Any) -> Response: return await self.request("DELETE", url, **kwargs)


async def close_runtime() -> None:
    """Wait for shared native work and stop the process-wide worker pool."""
    global _executor
    with _executor_lock:
        pool = _executor
    await asyncio.get_running_loop().run_in_executor(None, lambda: pool.shutdown(wait=True, cancel_futures=False))
