#!/usr/bin/env bash
# Copyright (c) 2026 FIX NHANH. All rights reserved.
# Bien dich ban NHI PHAN (Nuitka) cho exporter: code cua minh -> binary, kho doc nguoc hon .py.
# CHAY TREN LINUX co glibc BANG hoac CU HON server dich (vd build tren Ubuntu 20.04 de chay 20.04+).
# Can: python3-dev, gcc, patchelf, nuitka.  pyVmomi (ma nguon mo) khong bien dich, giu o vendor/.
#
# Dung:  bash deploy/build_binary.sh [thu-muc-du-an]
# Ket qua: .build/esxi-host-exporter (binary)  +  nhac buoc dong goi zip.
set -e
PROJ="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
EXP="$PROJ/exporter"; DEP="$PROJ/deploy"; OUT="$PROJ/.build"

grep -Eq 'PUBLIC_KEY_HEX = "[0-9a-f]{64}"' "$EXP/license_check.py" \
  || { echo "LOI: chua khoa ban quyen. Chay: python make_license.py init"; exit 1; }
command -v patchelf >/dev/null || { echo "LOI: thieu patchelf (apt install patchelf)"; exit 1; }
python3 -c 'import nuitka' 2>/dev/null || { echo "LOI: thieu nuitka (pip install nuitka)"; exit 1; }

B=$(mktemp -d); trap 'rm -rf "$B"' EXIT
cp "$EXP/license_check.py" "$EXP/esxi_host_exporter.py" "$EXP/vsan_disk_health.py" "$EXP/esxi_main.py" "$B/"
# Nhung dashboard HTML + menu.sh (base64) vao esxi_main.py
python3 - "$B/esxi_main.py" "$EXP/esxi_dashboard.html" "$DEP/menu.sh" <<'PY'
import base64, sys
main, dash, menu = sys.argv[1:4]
s = open(main, encoding="utf-8").read()
s = s.replace("@DASHBOARD_HTML_B64@", base64.b64encode(open(dash, "rb").read()).decode())
s = s.replace("@MENU_SH_B64@", base64.b64encode(open(menu, "rb").read().replace(b"\r\n", b"\n")).decode())
open(main, "w", encoding="utf-8").write(s)
PY

echo "-> Bien dich Nuitka (vai phut)..."
cd "$B"
# stdlib ma pyVmomi (nap luc chay, khong bien dich) can -> phai goi gon san vao binary
STDLIB="http.cookies http.client cgi html urllib.parse urllib.request uuid ssl logging hashlib zlib json pyexpat email"
INC=""; for m in $STDLIB; do INC="$INC --include-module=$m"; done; INC="$INC --include-package=xml"
python3 -m nuitka --onefile --standalone --assume-yes-for-downloads --no-pyi-file --remove-output \
  --include-module=license_check --include-module=esxi_host_exporter --include-module=vsan_disk_health \
  $INC \
  --nofollow-import-to=pyVmomi --nofollow-import-to=pyVim --nofollow-import-to=cryptography --nofollow-import-to=lxml \
  --output-filename=esxi-host-exporter esxi_main.py

mkdir -p "$OUT"
install -m 755 "$B/esxi-host-exporter" "$OUT/esxi-host-exporter"
echo
echo "XONG: $OUT/esxi-host-exporter ($(du -h "$OUT/esxi-host-exporter" | cut -f1))"
echo "glibc can toi thieu: $(objdump -T "$OUT/esxi-host-exporter" 2>/dev/null | grep -oE 'GLIBC_[0-9.]+' | sort -V | tail -1)"
echo "Dong goi: python3 deploy/build_zip.py --binary   (dua binary + vendor + stub vao zip)"
