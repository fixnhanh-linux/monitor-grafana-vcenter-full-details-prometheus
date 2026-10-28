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
    arg1 = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg1 == "--version":
        import esxi_host_exporter as app
        print(app.VERSION)
        return
    if arg1 == "--license-status":   # install.sh dung de kiem tra; exit 0 = hop le
        i = license_check.check(sys.argv[2] if len(sys.argv) > 2 else None)
        if i["unlicensed"]:
            print("Ban chua khoa ban quyen (dev)")
        elif i["valid"]:
            left = "vinh vien" if not i["expiry_ts"] else "con %d ngay (het han %s)" % (i["days_left"], i["expires"])
            print("HOP LE - khach: %s | %s | host toi da: %s" % (i["customer"], left, i["max_hosts"] or "khong gioi han"))
        else:
            print("KHONG HOP LE: %s" % i["reason"])
        print("machine-id: %s" % i["machine_id"])
        sys.exit(0 if i["valid"] else 1)
    if arg1 == "--run-menu":
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
