$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$out = Join-Path $root "tlsrequests"
New-Item -ItemType Directory -Force $out | Out-Null
$env:CGO_ENABLED = "1"
go -C (Join-Path $root "native") build -buildmode=c-shared -o (Join-Path $out "tlsrequests.dll") .
Remove-Item (Join-Path $out "tlsrequests.h") -Force -ErrorAction SilentlyContinue
