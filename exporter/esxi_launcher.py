#!/usr/bin/env python3
# Copyright (c) 2026 FIX NHANH. All rights reserved. Proprietary - xem file LICENSE.
"""Bo khoi dong ban quyen cho ESXi host exporter (FIX NHANH).

Khi dong goi bao ve, file nay duoc cai thanh esxi_host_exporter.py. Ma nguon that nam trong app.bundle
(ma hoa). Khoa giai ma chi co trong file license hop le cua dung may nay -> khong license thi khong chay.
"""
VERSION = "@VERSION@"

import importlib.abc
import importlib.util
import json
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import license_check  # noqa: E402


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, modules):
        self.modules = modules

    def find_spec(self, name, path=None, target=None):
        if name in self.modules:
            return importlib.util.spec_from_loader(name, self, origin=os.path.join(HERE, name + ".py"))
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        name = module.__spec__.name
        module.__file__ = os.path.join(HERE, name + ".py")  # de ma nguon tim .vsan_pass canh script
        exec(compile(self.modules[name], "<esxi:%s>" % name, "exec"), module.__dict__)


def _load():
    info = license_check.enforce()
    bundle = os.path.join(HERE, "app.bundle")
    if not os.path.exists(bundle):
        sys.exit("Thieu app.bundle - cai lai tu goi zip chinh thuc.")
    if not info.get("dk"):
        print("[LICENSE] License khong co khoa giai ma goi ma nguon - xin license moi tu FIX NHANH.", flush=True)
        os._exit(4)
    try:
        with open(bundle, "rb") as f:
            data = json.loads(zlib.decompress(license_check.unseal(f.read(), info["dk"])).decode("utf-8"))
    except Exception as e:
        print("[LICENSE] Khong giai ma duoc goi ma nguon: %s" % e, flush=True)
        os._exit(4)
    sys.meta_path.insert(0, _Finder(data["modules"]))
    import esxi_host_exporter as app  # tu bundle (finder dat truoc)
    app.ASSETS.update({k: v.encode("utf-8") for k, v in data["assets"].items()})
    return app


if __name__ == "__main__":
    try:
        _load().main()
    except KeyboardInterrupt:
        sys.exit("Da dung.")
