#!/usr/bin/env python3
"""Dong goi esxi-host-exporter-linux.zip (+ .sha256) de cai len Linux.

Chay tu thu muc du an:  python deploy/build_zip.py
- File text chuyen sang LF, .sh co quyen 755 (giu khi giai nen bang unzip).
- Kem thu vien pyVmomi -> server khong can internet:
    vendor/      pyVmomi dang cai tren may build (9.x, can Python >= 3.10 tren server)
    vendor-py38/ pyVmomi 8.0.3.0.1 cho server Python 3.8 / 3.9 (tai bang pip, cache o .build/)
- Ghi VERSION (lay tu esxi_host_exporter.py) va file .sha256 dinh dang chuan cua sha256sum.
- KHONG BAO GIO dua .vsan_pass / *.env vao goi.
"""
import hashlib
import os
import re
import subprocess
import sys
import zipfile

import pyVmomi

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(PROJ, "esxi-host-exporter-linux.zip")
ROOT = "esxi-host-exporter/"
TEXT = (".py", ".sh", ".service", ".md", ".json", ".yml", ".html", ".txt", ".typed", ".pyi")
STAMP = (2026, 10, 28, 0, 0, 0)
PY38_PYVMOMI = "pyvmomi==8.0.3.0.1"
PY38_CACHE = os.path.join(PROJ, ".build", "pyvmomi-8.0.3.0.1")

ENTRIES = [
    ("deploy/install.sh", "install.sh"), ("deploy/uninstall.sh", "uninstall.sh"), ("deploy/menu.sh", "menu.sh"),
    ("deploy/esxi-host-exporter@.service", "esxi-host-exporter@.service"),
    ("README.md", "README.md"), ("grafana/esxi_host_resource_grafana.json", "esxi_host_resource_grafana.json"),
    ("prometheus/alert-rules-esxi.yml", "alert-rules-esxi.yml"),
    ("prometheus/scrape-esxi-host-resource.yml", "scrape-esxi-host-resource.yml"),
    ("docs/Huong-Dan-Monitor-Resource-Host-ESXi-vSAN.docx", "Huong-Dan-Monitor-Resource-Host-ESXi-vSAN.docx"),
    ("exporter/esxi_host_exporter.py", "app/esxi_host_exporter.py"), ("exporter/vsan_disk_health.py", "app/vsan_disk_health.py"),
    ("exporter/esxi_dashboard.html", "app/esxi_dashboard.html"), ("exporter/dashboard_template.html", "app/dashboard_template.html"),
]


def main():
    version = re.search(r'^VERSION = "([^"]+)"', open(os.path.join(PROJ, "exporter", "esxi_host_exporter.py"),
                                                      encoding="utf-8").read(), re.M).group(1)
    files = [(os.path.join(PROJ, s), d) for s, d in ENTRIES]
    if not os.path.isdir(os.path.join(PY38_CACHE, "pyVmomi")):
        print("Tai %s cho Python 3.8/3.9 vao %s ..." % (PY38_PYVMOMI, PY38_CACHE))
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "--target", PY38_CACHE, PY38_PYVMOMI])
    for site, prefix in ((os.path.dirname(os.path.dirname(pyVmomi.__file__)), "vendor/"), (PY38_CACHE, "vendor-py38/")):
        for pkg in ("pyVmomi", "pyVim"):
            for dp, dns, fns in os.walk(os.path.join(site, pkg)):
                dns[:] = [d for d in dns if d != "__pycache__"]
                for fn in fns:
                    full = os.path.join(dp, fn)
                    files.append((full, prefix + os.path.relpath(full, site).replace(os.sep, "/")))
        for d in os.listdir(site):
            if d.lower().startswith("pyvmomi-") and d.endswith(".dist-info"):
                for dp, _, fns in os.walk(os.path.join(site, d)):
                    for fn in fns:
                        if fn.upper().startswith("LICENSE"):
                            files.append((os.path.join(dp, fn), prefix + "LICENSE-pyvmomi.txt"))

    bad = [d for _, d in files if ".vsan_pass" in d or d.endswith(".env")]
    assert not bad, "co file mat khau trong goi: %s" % bad

    def info(name, mode):
        zi = zipfile.ZipInfo(ROOT + name, date_time=STAMP)
        zi.create_system, zi.external_attr, zi.compress_type = 3, mode << 16, zipfile.ZIP_DEFLATED
        return zi

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(info("VERSION", 0o100644), version + "\n")
        for src, dst in files:
            data = open(src, "rb").read()
            if dst.endswith(TEXT):
                data = data.replace(b"\r\n", b"\n")
            z.writestr(info(dst, 0o100755 if dst.endswith(".sh") else 0o100644), data)

    digest = hashlib.sha256(open(OUT, "rb").read()).hexdigest()
    with open(OUT + ".sha256", "w", encoding="ascii", newline="\n") as f:
        f.write("%s  %s\n" % (digest, os.path.basename(OUT)))
    print("%s  %d file  %.1f MB  version=%s" % (OUT, len(files) + 1, os.path.getsize(OUT) / 1048576, version))
    print("sha256:", digest)


if __name__ == "__main__":
    main()
