#!/usr/bin/env sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$root/tlsrequests"
mkdir -p "$out"
name="tlsrequests.so"
[ "$(go env GOOS)" = darwin ] && name="tlsrequests.dylib"
CGO_ENABLED=1 go -C "$root/native" build -buildmode=c-shared -o "$out/$name" .
rm -f "$out/tlsrequests.h"
