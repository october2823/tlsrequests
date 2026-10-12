#!/usr/bin/env sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
out="$root/yumeclient"
mkdir -p "$out"
name="yumeclient.so"
[ "$(go env GOOS)" = darwin ] && name="yumeclient.dylib"
CGO_ENABLED=1 go -C "$root/native" build -buildmode=c-shared -o "$out/$name" .
rm -f "$out/yumeclient.h"
