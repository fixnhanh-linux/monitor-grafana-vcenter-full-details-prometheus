#!/usr/bin/env python3
# Copyright (c) 2026 FIX NHANH. All rights reserved. Proprietary - xem file LICENSE.
"""Diem vao cua ban NHI PHAN (Nuitka). Bien dich cung license_check + esxi_host_exporter + vsan_disk_health.

  esxi-host-exporter <vcenter> <user> ...   -> chay exporter (sau khi kiem tra license)
  esxi-host-exporter --run-menu [args]      -> chay menu quan ly
pyVmomi (ma nguon mo) khong bien dich, nap tu thu muc vendor/ canh binary luc chay.
Noi dung dashboard + menu duoc nhung vao binary luc build (xem build_binary.sh thay @...@).
"""
import os
import sys

# Thu muc chua binary (Nuitka onefile: dung argv[0] da realpath)
BIN_DIR = os.path.dirname(os.path.realpath(sys.argv[0]))
for sub in ("vendor", "vendor-py38"):
    d = os.path.join(BIN_DIR, sub)
    if os.path.isdir(d):
        sys.path.insert(0, d)
        break

import license_check  # noqa: E402

# Cac chuoi duoi day duoc build_binary.sh thay bang noi dung that (base64) luc build.
DASHBOARD_HTML_B64 = "@DASHBOARD_HTML_B64@"
MENU_SH_B64 = "@MENU_SH_B64@"


def _run_menu():
    import base64
    src = base64.b64decode(MENU_SH_B64).decode("utf-8")
    if not src or src == "@MENU_SH_B64@":
        sys.exit("Goi nay khong co menu.")
    os.execvp("bash", ["bash", "-c", src, "esxi-menu"] + sys.argv[2:])


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--run-menu":
        license_check.enforce()
        _run_menu()
        return
    license_check.enforce()
    import base64
    import esxi_host_exporter as app
    app.ASSETS["esxi_dashboard.html"] = base64.b64decode(DASHBOARD_HTML_B64)
    app.main()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Da dung.")
