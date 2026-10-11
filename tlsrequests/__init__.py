"""Async requests-like bindings for bogdanfinn/tls-client v1.16.0."""
from __future__ import annotations

import asyncio
import base64
import ctypes
import json
import os
import platform
import threading
import time
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode, urlsplit

from .cookies import CookieJar
from .profiles import ALL_IDENTIFIERS, ClientIdentifier, Profiles, find, validate

__all__ = ["Session", "AsyncSession", "Response", "CookieJar", "Profiles", "ALL_IDENTIFIERS", "ClientIdentifier", "find", "TLSClientError", "RequestError", "SessionConfigurationError", "close_runtime", "encode_multipart"]

class TLSClientError(RuntimeError): pass
class RequestError(TLSClientError): pass
class SessionConfigurationError(TLSClientError, ValueError): pass

_poolLock = threading.Lock()
_poolSize = 64
_executor = ThreadPoolExecutor(max_workers=_poolSize, thread_name_prefix="tlsrequests")
_library: ctypes.CDLL | None = None


def _libraryPath() -> Path:
    configured = os.getenv("TLSREQUESTS_LIBRARY")
    if configured: return Path(configured)
    suffix = {"Windows": ".dll", "Darwin": ".dylib"}.get(platform.system(), ".so")
    return Path(__file__).with_name("tlsrequests" + suffix)


def _native() -> ctypes.CDLL:
    global _library
    with _poolLock:
        if _library is None:
            path = _libraryPath()
            if not path.is_file(): raise TLSClientError(f"Native library not found: {path}; build native/ with Go 1.24+ and cgo")
            lib = ctypes.CDLL(str(path))
            lib.tlsrequests_call.argtypes = [ctypes.c_char_p]; lib.tlsrequests_call.restype = ctypes.c_void_p
            lib.tlsrequests_close.argtypes = [ctypes.c_char_p]; lib.tlsrequests_close.restype = None
            lib.tlsrequests_free.argtypes = [ctypes.c_void_p]; lib.tlsrequests_free.restype = None
            _library = lib
        return _library


def _call(payload: dict[str, Any]) -> dict[str, Any]:
    lib = _native()
    pointer = lib.tlsrequests_call(json.dumps(payload, separators=(",", ":")).encode())
    if not pointer: raise RequestError("native client returned a null response")
    try: result = json.loads(ctypes.string_at(pointer).decode("utf-8"))
    finally: lib.tlsrequests_free(pointer)
    if not result.get("status"): raise RequestError(result.get("body", "request failed"))
    return result


def _closeNative(sessionId: str) -> None:
    _native().tlsrequests_close(sessionId.encode())


def _version(value: Any) -> str:
    if value is None or str(value).lower() == "auto": return "auto"
    if value in (1, "1", "1.1", "h1"): return "1.1"
    if value in (2, "2", "h2"): return "2"
    if value in (3, "3", "h3", "quic"): return "3"
    raise SessionConfigurationError(f"invalid http_version: {value!r}")


def encode_multipart(data: Mapping[str, Any] | Sequence[tuple[str, Any]] | None,
                     files: Mapping[str, Any] | Sequence[tuple[str, Any]] | None,
                     boundary: str | None = None) -> tuple[bytes, str]:
    """Encode ordered multipart fields and files, using Chrome-style boundary and CRLF."""
    boundary = boundary or "----WebKitFormBoundary" + uuid.uuid4().hex[:16]
    parts: list[bytes] = []
    def entries(value: Any) -> list[tuple[str, Any]]:
        if value is None: return []
        return list(value.items()) if hasattr(value, "items") else list(value)
    for name, value in entries(data):
        vals = value if isinstance(value, (list, tuple)) else [value]
        for partValue in vals:
            parts.extend([f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n".encode(), str(partValue).encode(), b"\r\n"])
    for name, spec in entries(files):
        if isinstance(spec, tuple):
            filename = spec[0]
            content = spec[1] if len(spec) > 1 else b""
            contentType = spec[2] if len(spec) > 2 else "application/octet-stream"
        else:
            filename, content, contentType = getattr(spec, "name", "blob"), spec, "application/octet-stream"
        if hasattr(content, "read"): content = content.read()
        if isinstance(content, str): content = content.encode()
        parts.extend([f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\nContent-Type: {contentType}\r\n\r\n".encode(), bytes(content), b"\r\n"])
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


@dataclass(slots=True)
class Response:
    status_code: int
    headers: dict[str, list[str]]
    cookies: dict[str, str]
    content: bytes
    url: str
    used_protocol: str = ""
    history: list["Response"] = field(default_factory=list)
    elapsed: float = 0.0
    encoding: str = "utf-8"

    @property
    def status(self) -> int: return self.status_code
    @property
    def text(self) -> str:
        charset = self.encoding
        for key, values in self.headers.items():
            if key.lower() == "content-type" and values:
                for piece in values[0].split(";")[1:]:
                    if piece.strip().lower().startswith("charset="): charset = piece.split("=", 1)[1].strip(' "')
        try: return self.content.decode(charset, errors="replace")
        except LookupError: return self.content.decode("utf-8", errors="replace")
    @property
    def http_version(self) -> str:
        protocol = self.used_protocol.lower()
        if "3" in protocol or "quic" in protocol: return "3"
        if "2" in protocol: return "2"
        return "1.1" if protocol else ""
    @property
    def ok(self) -> bool: return 200 <= self.status_code < 400
    def json(self) -> Any: return json.loads(self.text)
    def raise_for_status(self) -> None:
        if not self.ok: raise RequestError(f"HTTP {self.status_code} for {self.url}")
    def __getitem__(self, key: str) -> str:
        vals = next((v for k, v in self.headers.items() if k.lower() == key.lower()), None)
        if vals is None: raise KeyError(key)
        return ", ".join(vals)


class Session:
    """Requests-style TLS session. Use async with and await each request method."""
    def __init__(self, *, client_identifier: str | None = None,
                 random_tls_extension_order: bool = True, http_version: Any = "auto",
                 proxy: str | None = None, timeout: float = 30, header_order: Sequence[str] | None = None,
                 headers: Mapping[str, str] | None = None, cookies: Any = None, verify: bool = True,
                 force_http1: bool = False, disable_http3: bool = False, disable_session_tickets: bool = False,
                 server_name_overwrite: str | None = None, local_address: str | None = None,
                 ja3_string: str | None = None, supported_signature_algorithms: Sequence[str] | None = None,
                 key_share_curves: Sequence[str] | None = None, supported_versions: Sequence[str] | None = None,
                 alpn_protocols: Sequence[str] | None = None, alps_protocols: Sequence[str] | None = None,
                 cert_compression_algos: Sequence[str] | None = None, trust_anchors_payload: str | None = None,
                 h2_settings: Mapping[str, int] | None = None, h2_settings_order: Sequence[str] | None = None,
                 connection_flow: int = 0, pseudo_header_order: Sequence[str] | None = None,
                 priority_frames: Sequence[Mapping[str, Any]] | None = None,
                 header_priority: Mapping[str, Any] | None = None, fill_custom_with_chrome_defaults: bool = True,
                 max_workers: int | None = None) -> None:
        if max_workers is not None: raise SessionConfigurationError("Use AsyncSession.configure_executor() for the shared pool")
        try: self.client_identifier = validate(client_identifier)
        except ValueError as exc: raise SessionConfigurationError(str(exc)) from exc
        self.random_tls_extension_order = random_tls_extension_order
        self.http_version = _version(http_version)
        self.proxy, self.timeout, self.header_order, self.verify = proxy, timeout, list(header_order) if header_order else None, verify
        self.force_http1, self.disable_http3, self.disable_session_tickets = force_http1, disable_http3, disable_session_tickets
        self.server_name_overwrite, self.local_address = server_name_overwrite, local_address
        self.headers = dict(headers or {})
        self.cookies = cookies if isinstance(cookies, CookieJar) else CookieJar(cookies)
        self.custom = None
        customData = {"ja3String": ja3_string, "supportedSignatureAlgorithms": supported_signature_algorithms, "keyShareCurves": key_share_curves, "supportedVersions": supported_versions, "alpnProtocols": alpn_protocols, "alpsProtocols": alps_protocols, "certCompressionAlgos": cert_compression_algos, "trustAnchorsPayload": trust_anchors_payload, "h2Settings": h2_settings, "h2SettingsOrder": h2_settings_order, "connectionFlow": connection_flow, "pseudoHeaderOrder": pseudo_header_order, "priorityFrames": priority_frames, "headerPriority": header_priority}
        customData = {key: value for key, value in customData.items() if value is not None and value != 0}
        if ja3_string:
            if client_identifier is not None: raise SessionConfigurationError("ja3_string cannot be combined with client_identifier")
            if fill_custom_with_chrome_defaults: customData["fillCustomWithChromeDefaults"] = True
            self.client_identifier = ""
            self.custom = customData
        elif any(value is not None for key, value in customData.items() if key != "connectionFlow"):
            raise SessionConfigurationError("custom TLS options require ja3_string")
        self._sessionId = str(uuid.uuid4())
        self._closed = False
        self._lock = asyncio.Lock()
        self._active: set[asyncio.Task[Any]] = set()
        self._configMark = self._transportMark()

    def _transportMark(self) -> tuple[Any, ...]:
        return (self.client_identifier, self.random_tls_extension_order, self.http_version, self.proxy, self.timeout, self.verify, self.force_http1, self.disable_http3, self.disable_session_tickets, self.server_name_overwrite, self.local_address, json.dumps(self.custom, sort_keys=True))

    async def __aenter__(self) -> "Session":
        if self._closed: raise SessionConfigurationError("session is closed")
        return self

    async def __aexit__(self, *_: Any) -> None: await self.close()

    async def reset_connection(self) -> None:
        async with self._lock:
            if self._closed: raise SessionConfigurationError("session is closed")
            oldId, self._sessionId = self._sessionId, str(uuid.uuid4())
            self._configMark = self._transportMark()
        await asyncio.get_running_loop().run_in_executor(_executor, _closeNative, oldId)

    def _validate(self, proxy: str | None) -> dict[str, Any]:
        httpVer = _version(self.http_version)
        forceHttp1 = self.force_http1 or httpVer == "1.1"
        racing = httpVer == "3"
        if forceHttp1 and racing: raise SessionConfigurationError("http_version=3 cannot be combined with force_http1")
        if self.disable_http3 and racing: raise SessionConfigurationError("http_version=3 conflicts with disable_http3")
        if racing and proxy and not proxy.lower().startswith("socks5://"):
            raise SessionConfigurationError("HTTP/3 racing with a proxy requires socks5:// to tunnel UDP")
        if racing and self.client_identifier in {"chrome_152", "chrome_152_PSK", "chrome_150", "chrome_150_PSK"}:
            warnings.warn("this profile has no browser-specific HTTP/3 settings; using library defaults", UserWarning, stacklevel=3)
        if httpVer == "2" and self.client_identifier.startswith("chrome_133"):
            warnings.warn("HTTP/2-only selection may alter this profile's ALPN fingerprint", UserWarning, stacklevel=3)
        return {"forceHttp1": forceHttp1, "disableHttp3": self.disable_http3 or httpVer == "2", "withProtocolRacing": racing}

    async def request(self, method: str, url: str, *, params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None = None,
                      data: Any = None, json: Any = None, files: Any = None, headers: Mapping[str, str] | None = None,
                      cookies: Mapping[str, str] | None = None, timeout: float | None = None,
                      proxy: str | None = None, allow_redirects: bool = True, header_order: Sequence[str] | None = None,
                      host_override: str | None = None, **kwargs: Any) -> Response:
        task = asyncio.current_task()
        async with self._lock:
            if self._closed: raise SessionConfigurationError("session is closed")
            if task: self._active.add(task)
            mark = self._transportMark()
            if mark != self._configMark:
                oldId, self._sessionId = self._sessionId, str(uuid.uuid4())
                self._configMark = mark
            else: oldId = None
            sessionId = self._sessionId
        try:
            if oldId: await asyncio.get_running_loop().run_in_executor(_executor, _closeNative, oldId)
            requestUrl = url
            if params:
                query = urlencode(params, doseq=True)
                requestUrl += ("&" if "?" in requestUrl else "?") + query
            requestHeaders = dict(self.headers); requestHeaders.update(headers or {})
            body = None; byteRequest = False
            if files is not None:
                bodyBytes, contentType = encode_multipart(data if isinstance(data, (dict, list, tuple)) else None, files)
                body = base64.b64encode(bodyBytes).decode("ascii"); byteRequest = True
                requestHeaders.setdefault("Content-Type", contentType)
            elif json is not None:
                body = __import__("json").dumps(json, separators=(",", ":"))
                requestHeaders.setdefault("Content-Type", "application/json")
            elif data is not None:
                if isinstance(data, bytes): body = base64.b64encode(data).decode(); byteRequest = True
                elif isinstance(data, (dict, list, tuple)):
                    body = urlencode(data, doseq=True); requestHeaders.setdefault("Content-Type", "application/x-www-form-urlencoded")
                else: body = str(data)
            cookieData = dict(self.cookies.to_dict(domain=(urlsplit(requestUrl).hostname or "")))
            cookieData.update(cookies or {})
            flags = self._validate(proxy if proxy is not None else self.proxy)
            order = list(header_order) if header_order is not None else self.header_order
            if order is None: order = list(requestHeaders)
            payload: dict[str, Any] = {"requestMethod": method.upper(), "requestUrl": requestUrl, "tlsClientIdentifier": self.client_identifier,
                "sessionId": sessionId, "headers": requestHeaders, "headerOrder": order, "requestBody": body,
                "requestCookies": [{"name": key, "value": value} for key, value in cookieData.items()],
                "timeoutMilliseconds": int((timeout if timeout is not None else self.timeout) * 1000),
                "followRedirects": allow_redirects, "insecureSkipVerify": not self.verify, "isByteRequest": byteRequest,
                "isByteResponse": True, "withCustomCookieJar": True, "withRandomTLSExtensionOrder": self.random_tls_extension_order,
                "forceHttp1": flags["forceHttp1"], "disableHttp3": flags["disableHttp3"], "withProtocolRacing": flags["withProtocolRacing"],
                "disableSessionTickets": self.disable_session_tickets}
            proxyValue = proxy if proxy is not None else self.proxy
            if proxyValue is not None: payload["proxyUrl"] = proxyValue
            if host_override is not None: payload["requestHostOverride"] = host_override
            if self.server_name_overwrite is not None: payload["serverNameOverwrite"] = self.server_name_overwrite
            if self.local_address is not None: payload["localAddress"] = self.local_address
            if self.custom is not None: payload["customTlsClient"] = self.custom
            start = time.perf_counter()
            future = asyncio.get_running_loop().run_in_executor(_executor, _call, payload)
            try: result = await asyncio.shield(future)
            except asyncio.CancelledError:
                try: await asyncio.shield(future)
                finally: raise
            elapsed = time.perf_counter() - start
            encoded = result.get("body", "")
            if encoded.startswith("data:") and ";base64," in encoded: encoded = encoded.split(";base64,", 1)[1]
            responseCookies = result.get("cookies") or {}
            self.cookies.update(responseCookies, domain=urlsplit(result.get("target", requestUrl)).hostname or "")
            return Response(int(result.get("status", 0)), result.get("headers") or {}, responseCookies, base64.b64decode(encoded), result.get("target", requestUrl), result.get("usedProtocol", ""), [], elapsed)
        finally:
            if task:
                async with self._lock: self._active.discard(task)

    async def close(self) -> None:
        async with self._lock:
            if self._closed: return
            self._closed = True
            active = tuple(task for task in self._active if task is not asyncio.current_task())
            sessionId = self._sessionId
        if active: await asyncio.gather(*(asyncio.shield(task) for task in active), return_exceptions=True)
        try: await asyncio.get_running_loop().run_in_executor(_executor, _closeNative, sessionId)
        except TLSClientError: pass

    async def get(self, url: str, *, params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None = None, headers: Mapping[str, str] | None = None, cookies: Mapping[str, str] | None = None, timeout: float | None = None, proxy: str | None = None, allow_redirects: bool = True, header_order: Sequence[str] | None = None, host_override: str | None = None, **kwargs: Any) -> Response: return await self.request("GET", url, params=params, headers=headers, cookies=cookies, timeout=timeout, proxy=proxy, allow_redirects=allow_redirects, header_order=header_order, host_override=host_override, **kwargs)
    async def head(self, url: str, *, params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None = None, headers: Mapping[str, str] | None = None, cookies: Mapping[str, str] | None = None, timeout: float | None = None, proxy: str | None = None, allow_redirects: bool = True, header_order: Sequence[str] | None = None, host_override: str | None = None, **kwargs: Any) -> Response: return await self.request("HEAD", url, params=params, headers=headers, cookies=cookies, timeout=timeout, proxy=proxy, allow_redirects=allow_redirects, header_order=header_order, host_override=host_override, **kwargs)
    async def post(self, url: str, *, params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None = None, data: Any = None, json: Any = None, files: Any = None, headers: Mapping[str, str] | None = None, cookies: Mapping[str, str] | None = None, timeout: float | None = None, proxy: str | None = None, allow_redirects: bool = True, header_order: Sequence[str] | None = None, host_override: str | None = None, **kwargs: Any) -> Response: return await self.request("POST", url, params=params, data=data, json=json, files=files, headers=headers, cookies=cookies, timeout=timeout, proxy=proxy, allow_redirects=allow_redirects, header_order=header_order, host_override=host_override, **kwargs)
    async def put(self, url: str, *, params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None = None, data: Any = None, json: Any = None, files: Any = None, headers: Mapping[str, str] | None = None, cookies: Mapping[str, str] | None = None, timeout: float | None = None, proxy: str | None = None, allow_redirects: bool = True, header_order: Sequence[str] | None = None, host_override: str | None = None, **kwargs: Any) -> Response: return await self.request("PUT", url, params=params, data=data, json=json, files=files, headers=headers, cookies=cookies, timeout=timeout, proxy=proxy, allow_redirects=allow_redirects, header_order=header_order, host_override=host_override, **kwargs)
    async def patch(self, url: str, *, params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None = None, data: Any = None, json: Any = None, files: Any = None, headers: Mapping[str, str] | None = None, cookies: Mapping[str, str] | None = None, timeout: float | None = None, proxy: str | None = None, allow_redirects: bool = True, header_order: Sequence[str] | None = None, host_override: str | None = None, **kwargs: Any) -> Response: return await self.request("PATCH", url, params=params, data=data, json=json, files=files, headers=headers, cookies=cookies, timeout=timeout, proxy=proxy, allow_redirects=allow_redirects, header_order=header_order, host_override=host_override, **kwargs)
    async def delete(self, url: str, *, params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None = None, data: Any = None, json: Any = None, headers: Mapping[str, str] | None = None, cookies: Mapping[str, str] | None = None, timeout: float | None = None, proxy: str | None = None, allow_redirects: bool = True, header_order: Sequence[str] | None = None, host_override: str | None = None, **kwargs: Any) -> Response: return await self.request("DELETE", url, params=params, data=data, json=json, headers=headers, cookies=cookies, timeout=timeout, proxy=proxy, allow_redirects=allow_redirects, header_order=header_order, host_override=host_override, **kwargs)


class AsyncSession(Session):
    @classmethod
    def configure_executor(cls, workers: int = 64) -> None:
        global _executor, _poolSize
        if workers < 1: raise ValueError("workers must be positive")
        with _poolLock:
            oldPool = _executor
            if getattr(oldPool, "_threads", set()): raise SessionConfigurationError("configure executor before starting requests")
            _poolSize = workers
            _executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tlsrequests")
            oldPool.shutdown(wait=False)


async def close_runtime() -> None:
    global _executor
    with _poolLock: pool = _executor
    await asyncio.get_running_loop().run_in_executor(None, lambda: pool.shutdown(wait=True, cancel_futures=False))
