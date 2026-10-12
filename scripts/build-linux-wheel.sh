#!/usr/bin/env sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
docker run --rm -v "$root:/src" -w /src quay.io/pypa/manylinux_2_28_x86_64 bash -lc '
set -eu
curl -fsSL https://go.dev/dl/go1.24.13.linux-amd64.tar.gz -o /tmp/go.tar.gz
rm -rf /usr/local/go
tar -C /usr/local -xzf /tmp/go.tar.gz
export PATH=/usr/local/go/bin:/opt/python/cp311-cp311/bin:$PATH
/usr/local/go/bin/go -C native build -buildvcs=false -buildmode=c-shared -o ../yumeclient/yumeclient.so .
rm -f yumeclient/yumeclient.h
for py in cp311 cp312 cp313 cp314; do
  pybin="/opt/python/${py}-${py}"
  "$pybin/bin/python" -m pip install --disable-pip-version-check setuptools wheel
  "$pybin/bin/python" setup.py bdist_wheel
  "$pybin/bin/python" -m pip install --disable-pip-version-check auditwheel
  mkdir -p dist/repaired
  "$pybin/bin/auditwheel" repair dist/*linux_x86_64.whl -w dist/repaired
  rm -f dist/*linux_x86_64.whl
  mv dist/repaired/*.whl dist/
  rm -rf dist/repaired build yumeclient.egg-info
 done
'
