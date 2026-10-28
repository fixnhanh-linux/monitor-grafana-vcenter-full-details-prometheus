#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiem tra ban quyen (license) cho ESXi host exporter - (C) 2026 FIX NHANH.

- Xac thuc chu ky Ed25519 cua file license bang KHOA CONG KHAI nhung ben duoi.
  Khoa bi mat chi nam tren may cua FIX NHANH (make_license.py) -> khach khong tu tao license duoc.
- License gan voi machine-id cua server -> chep sang may khac se khong chay.
- Co han su dung va gioi han so host.

File license mac dinh: /etc/esxi-host-exporter/license.key  (doi bang bien ESXI_LICENSE).
Ed25519 viet thuan Python theo RFC 8032 -> khong can thu vien ngoai, chay duoc tren Python 3.8+.
"""
import base64
import hashlib
import json
import os
import time

# make_license.py --init se thay chuoi nay bang khoa cong khai that (64 ky tu hex).
# Rong = ban CHUA khoa ban quyen (dung de phat trien / build mo): bo qua kiem tra.
PUBLIC_KEY_HEX = "004a38d0a62bc9f221045414b167513949e10f278c6749053075eb86f356b7f5"

DEFAULT_PATH = "/etc/esxi-host-exporter/license.key"

# ----------------------------------------------------------------------------
# Ed25519 (RFC 8032) - chi can cho xac thuc chu ky; ky nam o make_license.py.
_b = 256
_q = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493


def _H(m):
    return hashlib.sha512(m).digest()


def _inv(x):
    return pow(x, _q - 2, _q)


_d = (-121665 * _inv(121666)) % _q
_I = pow(2, (_q - 1) // 4, _q)


def _xrecover(y):
    xx = (y * y - 1) * _inv(_d * y * y + 1)
    x = pow(xx, (_q + 3) // 8, _q)
    if (x * x - xx) % _q != 0:
        x = (x * _I) % _q
    if x % 2 != 0:
        x = _q - x
    return x


_By = (4 * _inv(5)) % _q
_Bx = _xrecover(_By)
_B = [_Bx % _q, _By % _q]


def _edwards(P, Q):
    x1, y1 = P
    x2, y2 = Q
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + _d * x1 * x2 * y1 * y2)
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - _d * x1 * x2 * y1 * y2)
    return [x3 % _q, y3 % _q]


def _scalarmult(P, e):
    if e == 0:
        return [0, 1]
    Q = _scalarmult(P, e // 2)
    Q = _edwards(Q, Q)
    if e & 1:
        Q = _edwards(Q, P)
    return Q


def _bit(h, i):
    return (h[i // 8] >> (i % 8)) & 1


def _decodeint(s):
    return sum(2 ** i * _bit(s, i) for i in range(0, _b))


def _decodepoint(s):
    y = sum(2 ** i * _bit(s, i) for i in range(0, _b - 1))
    x = _xrecover(y)
    if x & 1 != _bit(s, _b - 1):
        x = _q - x
    P = [x, y]
    if not _isoncurve(P):
        raise ValueError("diem khong nam tren duong cong")
    return P


def _isoncurve(P):
    x, y = P
    return (-x * x + y * y - 1 - _d * x * x * y * y) % _q == 0


def _checkvalid(sig, msg, pk):
    if len(sig) != _b // 4:
        return False
    if len(pk) != _b // 8:
        return False
    try:
        R = _decodepoint(sig[0:_b // 8])
        A = _decodepoint(pk)
    except ValueError:
        return False
    S = _decodeint(sig[_b // 8:_b // 4])
    h = _decodeint(_H(sig[0:_b // 8] + pk + msg))
    if _scalarmult(_B, S) != _edwards(R, _scalarmult(A, h)):
        return False
    return True


# ----------------------------------------------------------------------------
def machine_id():
    """Dinh danh on dinh cua may (bam SHA-256), dung de gan license vao 1 server."""
    raw = ""
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(p) as f:
                raw = f.read().strip()
            if raw:
                break
        except OSError:
            continue
    if not raw:
        raw = os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "unknown")
    return hashlib.sha256(("esxi-exporter:" + raw).encode("utf-8")).hexdigest()[:32]


def _read_token(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "." in line:
                return line
    raise ValueError("file license khong co dong chu ky")


def verify_file(path, pub_hex=None):
    """Doc + xac thuc file license. Tra ve (payload_dict, ly_do_loi). Loi -> (None, 'ly do')."""
    pub_hex = PUBLIC_KEY_HEX if pub_hex is None else pub_hex
    try:
        token = _read_token(path)
        p_b64, s_b64 = token.split(".", 1)
        payload_raw = base64.urlsafe_b64decode(p_b64 + "=" * (-len(p_b64) % 4))
        sig = base64.urlsafe_b64decode(s_b64 + "=" * (-len(s_b64) % 4))
    except (OSError, ValueError) as e:
        return None, "khong doc duoc file license: %s" % e
    if not _checkvalid(sig, payload_raw, bytes.fromhex(pub_hex)):
        return None, "chu ky license khong hop le (file bi sua hoac khong phai cua FIX NHANH)"
    try:
        payload = json.loads(payload_raw.decode("utf-8"))
    except ValueError as e:
        return None, "noi dung license hong: %s" % e
    return payload, ""


def _expiry_ts(payload):
    exp = payload.get("expires", "never")
    if exp in ("never", "", None):
        return 0  # 0 = vinh vien
    return int(time.mktime(time.strptime(exp, "%Y-%m-%d"))) + 86399  # het han cuoi ngay


def check(path=None):
    """Tra ve dict trang thai license. Ban chua khoa ban quyen -> valid=True, unlicensed=True."""
    info = {"valid": False, "unlicensed": False, "reason": "", "customer": "", "machine_ok": False,
            "expires": "", "expiry_ts": 0, "days_left": None, "max_hosts": 0, "machine_id": machine_id()}
    if not PUBLIC_KEY_HEX:
        info.update(valid=True, unlicensed=True, customer="DEV (ban chua khoa ban quyen)", expires="never")
        return info
    path = path or os.environ.get("ESXI_LICENSE", DEFAULT_PATH)
    if not os.path.exists(path):
        info["reason"] = "khong tim thay file license: %s" % path
        return info
    payload, err = verify_file(path)
    if err:
        info["reason"] = err
        return info
    info.update(customer=payload.get("customer", ""), expires=payload.get("expires", "never"),
                max_hosts=int(payload.get("max_hosts", 0) or 0))
    lic_machine = payload.get("machine", "ANY")
    info["machine_ok"] = (lic_machine == "ANY") or (lic_machine == info["machine_id"])
    if not info["machine_ok"]:
        info["reason"] = "license cap cho may khac (machine-id khong khop)"
        return info
    ts = _expiry_ts(payload)
    info["expiry_ts"] = ts
    if ts:
        info["days_left"] = int((ts - time.time()) // 86400)
        if time.time() > ts:
            info["reason"] = "license het han ngay %s" % payload.get("expires")
            return info
    info["valid"] = True
    return info


def enforce():
    """Goi luc khoi dong exporter. License hong -> in huong dan + thoat ma 4. Tra ve dict trang thai."""
    info = check()
    if info["valid"]:
        if info.get("unlicensed"):
            print("[LICENSE] Ban build chua khoa ban quyen (dung cho phat trien).", flush=True)
        else:
            left = "vinh vien" if not info["expiry_ts"] else "con %d ngay (het han %s)" % (info["days_left"], info["expires"])
            print("[LICENSE] OK - khach: %s | %s | host toi da: %s"
                  % (info["customer"], left, info["max_hosts"] or "khong gioi han"), flush=True)
        return info
    print("=" * 64, flush=True)
    print("[LICENSE] KHONG HOP LE: %s" % info["reason"], flush=True)
    print("  machine-id may nay: %s" % info["machine_id"], flush=True)
    print("  Gui machine-id tren cho FIX NHANH de xin/gia han license,", flush=True)
    print("  luu file license vao: %s" % (os.environ.get("ESXI_LICENSE", DEFAULT_PATH)), flush=True)
    print("=" * 64, flush=True)
    os._exit(4)  # 4 = loi license; systemd RestartPreventExitStatus=3 4 -> khong thu lai


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "id":
        print(machine_id())
    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        i = check(sys.argv[2] if len(sys.argv) > 2 else None)
        if i["unlicensed"]:
            print("Ban chua khoa ban quyen (dev)")
        elif i["valid"]:
            print("HOP LE - khach: %s | %s | host toi da: %s" % (
                i["customer"], "vinh vien" if not i["expiry_ts"] else "con %d ngay (het han %s)" % (i["days_left"], i["expires"]),
                i["max_hosts"] or "khong gioi han"))
        else:
            print("KHONG HOP LE: %s" % i["reason"])
        print("machine-id: %s" % i["machine_id"])
        sys.exit(0 if i["valid"] else 1)
    else:
        i = check(sys.argv[1] if len(sys.argv) > 1 else None)
        print(json.dumps(i, ensure_ascii=False, indent=2))
