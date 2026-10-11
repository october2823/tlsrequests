# tlsrequests

Async Python facade over `github.com/bogdanfinn/tls-client` v1.16.0. The Python layer never substitutes another TLS implementation: it calls the upstream Go `cffi_src` client through a small cgo shared-library adapter. The Go client remains responsible for uTLS fingerprints, HTTP/2/3, proxies, cookies and profiles.

## Architecture and plan

1. Pin upstream v1.16.0 and rely on its documented `RequestInput`/`Response` JSON contract.
2. Build a thin cgo ABI shim over upstream `cffi_src` (not a Python TLS reimplementation).
3. Call that synchronous ABI via one process-wide, bounded `ThreadPoolExecutor`; serialize session close against active operations and keep concurrent request calls safe.
4. Expose `Session`, `Response`, exceptions and request helpers with async context management; check in tests and build instructions.

## Build

Requires Go 1.24.1, a C compiler, and network access for Go modules. The importable Python package lives in `tlsrequests/`; build from the `native/` directory:

```sh
cd native && go build -buildmode=c-shared -o ../tlsrequests/tlsrequests.so .
cd .. && python -m pip install -e .
```

On Windows use `-o ../tlsrequests/tlsrequests.dll`; on macOS use `.dylib`. Set `TLSREQUESTS_LIBRARY` to the resulting library path if it is elsewhere. The shared library must be built for the host OS/architecture.

```python
async with Session(client_identifier="chrome_120") as s:
    r = await s.get("https://example.com", params={"q": "hello"})
    print(r.status_code, r.text)
```

Upstream license: MIT; see `LICENSE` (upstream copyright retained). Profiles are provided by upstream v1.16.0; identifiers are passed through unchanged. Exact custom-TLS JSON keys are the upstream `cffi_src/types.go` names.
