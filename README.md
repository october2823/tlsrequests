# tlsrequests

Async Python facade over `github.com/bogdanfinn/tls-client` v1.16.0. The Python layer never substitutes another TLS implementation: it calls the upstream Go `cffi_src` client through a small cgo shared-library adapter. The Go client remains responsible for uTLS fingerprints, HTTP/2/3, proxies, cookies and profiles.

## Build

Requires Go 1.24.1, a C compiler, and network access for Go modules. The importable Python package lives in `tlsrequests/`; build from the `native/` directory:

```sh
cd native && go build -buildmode=c-shared -o ../tlsrequests/tlsrequests.so .
cd .. && python -m pip install -e .
```

On Windows use `-o ../tlsrequests/tlsrequests.dll`; on macOS use `.dylib`. Set `TLSREQUESTS_LIBRARY` to the resulting library path if it is elsewhere. The shared library must be built for the host OS/architecture.

See [USAGE.md](USAGE.md) for API examples, profiles, transport modes, cookies, multipart behavior, build commands, and known limitations.

Upstream license: MIT; see `UPSTREAM-LICENSE`. Profile names and JSON field spellings track upstream v1.16.0.
