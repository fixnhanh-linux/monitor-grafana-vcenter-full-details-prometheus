#!/usr/bin/env python3
"""Tao / cap nhat host Zabbix cho tung instance exporter qua Zabbix API.

Exporter dung HTTP agent (Zabbix keo /metrics) nen host KHONG can interface: chi can
ten host + host group + gan template "ESXi Host Exporter by HTTP" + macro {$ESXI.EXPORTER.URL}.
Script doc cac instance da cai tren server (/etc/esxi-host-exporter/*.env) va tao host tuong ung.

Tach cluster: doc /metrics cua moi instance, dem so cluster (POOL). Neu 1 instance giam sat
>= 2 cluster thi TACH ra thanh nhieu host (moi cluster 1 host), dat them macro
{$ESXI.CLUSTER.MATCHES}=^<ten-cluster>$ de host do chi lay dung cluster cua minh.
Instance chi co 1 cluster -> 1 host, dat ten theo instance nhu cu.

Host da ton tai: MAC DINH BO QUA (khong dong vao). Them --update neu muon cap nhat host da co.

Cach dung:
  export ZABBIX_TOKEN=xxxxx                                   (Linux)   |  set ZABBIX_TOKEN=xxxxx (Windows)
  python add_hosts.py https://zabbix.example/zabbix           # xem truoc, KHONG ghi
  python add_hosts.py https://zabbix.example/zabbix --apply   # tao that (host da co: bo qua)

  Token: Zabbix > Users > API tokens (role co quyen tao host). Zabbix 6.x dung token o truong "auth".
  Tren server: menu muc 18 (Sinh / cai host Zabbix) chay script nay.

Tuy chon:
  --group "ESXi Host Exporter"             host group (tu tao neu chua co)
  --template "ESXi Host Exporter by HTTP"  ten ky thuat cua template (phai import truoc)
  --prefix "Esxi-Exporter-"                tien to ten host (ten instance/cluster viet HOA)
  --ip 10.16.16.38                         IP server exporter (mac dinh: tu dong phat hien)
  --conf /etc/esxi-host-exporter           thu muc .env cua instance
  --update                                 host da co thi CAP NHAT (giu macro/group/template khac),
                                           thay vi bo qua
  --no-split                               khong tach cluster (1 instance = 1 host nhu ban cu)
"""
import glob
import json
import os
import re
import socket
import ssl
import sys
import urllib.error
import urllib.request


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def server_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def san(name):
    """Ten cluster -> phan ten host an toan (chu HOA, chi giu chu/so/gach)."""
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").upper() or "CLUSTER"


def instances(conf):
    out = []
    for f in sorted(glob.glob(os.path.join(conf, "*.env"))):
        name = os.path.basename(f)[:-4]
        port = ""
        for line in open(f, encoding="utf-8", errors="replace"):
            m = re.match(r"\s*PORT\s*=\s*['\"]?(\d+)", line)
            if m:
                port = m.group(1)
                break
        if port:
            out.append((name, port))
    return out


def clusters_of(ip, port):
    """Doc /metrics, tra ve danh sach cluster (tu nhan esxi_host_status{...cluster="X"}).
    Tra None neu khong doc duoc /metrics (goi y: dung 1 host theo instance)."""
    url = "http://%s:%s/metrics" % (ip, port)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        return None
    cls = set()
    for line in data.splitlines():
        if line.startswith("esxi_host_status{"):
            m = re.search(r'cluster="([^"]*)"', line)
            if m and m.group(1):
                cls.add(m.group(1))
    return sorted(cls)


class Zbx:
    def __init__(self, url, token):
        self.url = url.rstrip("/") + "/api_jsonrpc.php"
        self.token = token
        self._id = 0

    def call(self, method, params=None, auth=True):
        self._id += 1
        body = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": self._id}
        if auth:
            body["auth"] = self.token
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json-rpc"})
        try:
            with urllib.request.urlopen(req, timeout=30, context=ssl._create_unverified_context()) as r:
                d = json.loads(r.read())
        except urllib.error.HTTPError as e:
            sys.exit("Zabbix HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300]))
        except urllib.error.URLError as e:
            sys.exit("Khong ket noi duoc Zabbix %s: %s" % (self.url, e))
        if "error" in d:
            err = d["error"]
            sys.exit("Zabbix API loi (%s): %s %s" % (method, err.get("message", ""), err.get("data", "")))
        return d["result"]


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("-"):
        sys.exit(__doc__)
    base = sys.argv[1]
    token = os.environ.get("ZABBIX_TOKEN")
    if not token:
        sys.exit("Chua dat ZABBIX_TOKEN (xem huong dan dau file).")
    group = arg("--group", "ESXi Host Exporter")
    template = arg("--template", "ESXi Host Exporter by HTTP")
    prefix = arg("--prefix", "Esxi-Exporter-")
    conf = arg("--conf", "/etc/esxi-host-exporter")
    ip = arg("--ip", server_ip())
    apply_ = "--apply" in sys.argv
    update_existing = "--update" in sys.argv
    no_split = "--no-split" in sys.argv

    insts = instances(conf)
    if not insts:
        sys.exit("Khong thay instance nao trong %s/*.env" % conf)

    z = Zbx(base, token)
    print("Zabbix API %s @ %s" % (z.call("apiinfo.version", {}, auth=False), base))

    tpl = z.call("template.get", {"filter": {"host": [template]}, "output": ["templateid"]})
    if not tpl:
        sys.exit("Khong thay template '%s' - import template truoc (Data collection > Templates)." % template)
    tid = tpl[0]["templateid"]

    grp = z.call("hostgroup.get", {"filter": {"name": [group]}, "output": ["groupid"]})
    gid = grp[0]["groupid"] if grp else None
    if gid is None:
        print("Host group '%s' chua co%s." % (group, " -> se tao" if apply_ else ""))
        if apply_:
            gid = z.call("hostgroup.create", {"name": group})["groupids"][0]

    MURL = "{$ESXI.EXPORTER.URL}"
    MCL = "{$ESXI.CLUSTER.MATCHES}"

    # 1 instance -> 1 hay nhieu "target" (host). Tach khi instance co >= 2 cluster.
    targets = []
    for name, port in insts:
        url = "http://%s:%s/metrics" % (ip, port)
        cls = None if no_split else clusters_of(ip, port)
        if cls and len(cls) >= 2:
            print("  %s: %d cluster -> tach ra (%s)" % (name, len(cls), ", ".join(cls)))
            for c in cls:
                targets.append({"host": prefix + san(c), "url": url, "cluster": c, "inst": name})
        else:
            targets.append({"host": prefix + name.upper(), "url": url, "cluster": None, "inst": name})

    # tra trung ten host (phong khi 2 cluster cho ra cung ten)
    seen = {}
    for t in targets:
        if t["host"] in seen:
            t["host"] = "%s-%s" % (t["host"], t["inst"].upper())
        seen[t["host"]] = True

    # kiem tra host da co chua
    for t in targets:
        ex = z.call("host.get", {"filter": {"host": [t["host"]]}, "output": ["hostid"],
                                 "selectMacros": "extend", "selectParentTemplates": ["templateid"],
                                 "selectGroups": ["groupid"]})
        t["cur"] = ex[0] if ex else None

    print("\nSe xu ly %d host (group '%s', template '%s', IP %s):" % (len(targets), group, template, ip))
    for t in targets:
        if t["cur"]:
            act = "cap nhat" if update_existing else "bo qua (da co)"
        else:
            act = "tao moi"
        extra = ("  cluster=%s" % t["cluster"]) if t["cluster"] else ""
        print("  [%-13s] %-30s %s%s" % (act, t["host"], t["url"], extra))

    if not apply_:
        print("\nXem truoc (chua ghi). Chay lai voi --apply de tao that.")
        return

    n_new = n_upd = n_skip = 0
    for t in targets:
        host, url, cluster, cur = t["host"], t["url"], t["cluster"], t["cur"]
        macros = [{"macro": MURL, "value": url}]
        if cluster:
            macros.append({"macro": MCL, "value": "^" + re.escape(cluster) + "$"})
        if cur is None:
            z.call("host.create", {"host": host, "groups": [{"groupid": gid}],
                                   "templates": [{"templateid": tid}], "macros": macros})
            print("  tao %s" % host)
            n_new += 1
        elif update_existing:
            drop = {MURL} | ({MCL} if cluster else set())
            keep = [{"macro": m["macro"], "value": m["value"]}
                    for m in cur.get("macros", []) if m["macro"] not in drop]
            keep.extend(macros)
            gids = {g["groupid"] for g in cur.get("hostgroups", cur.get("groups", []))}
            gids.add(gid)
            params = {"hostid": cur["hostid"], "macros": keep,
                      "groups": [{"groupid": g} for g in gids]}
            tids = {tt["templateid"] for tt in cur.get("parentTemplates", [])}
            if tid not in tids:
                params["templates"] = [{"templateid": x} for x in tids | {tid}]
            z.call("host.update", params)
            print("  cap nhat %s" % host)
            n_upd += 1
        else:
            print("  bo qua %s (da co)" % host)
            n_skip += 1
    print("Xong: tao %d, cap nhat %d, bo qua %d." % (n_new, n_upd, n_skip))


if __name__ == "__main__":
    main()
