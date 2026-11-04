#!/usr/bin/env python3
"""Tao / cap nhat host Zabbix cho tung instance exporter qua Zabbix API.

Exporter dung HTTP agent (Zabbix keo /metrics) nen host KHONG can interface: chi can
ten host + host group + gan template "ESXi Host Exporter by HTTP" + macro {$ESXI.EXPORTER.URL}.
Script doc cac instance da cai tren server (/etc/esxi-host-exporter/*.env) va tao host tuong ung.

Cach dung:
  export ZABBIX_TOKEN=xxxxx                                   (Linux)   |  set ZABBIX_TOKEN=xxxxx (Windows)
  python add_hosts.py https://zabbix.example/zabbix           # xem truoc, KHONG ghi
  python add_hosts.py https://zabbix.example/zabbix --apply   # tao/cap nhat that

  Token: Zabbix > Users > API tokens (role co quyen tao host). Zabbix 6.x dung token o truong "auth".
  Tren server: menu muc 18 (Sinh / cai host Zabbix) chay script nay.

Tuy chon:
  --group "ESXi Host Exporter"             host group (tu tao neu chua co)
  --template "ESXi Host Exporter by HTTP"  ten ky thuat cua template (phai import truoc)
  --prefix "Esxi-Exporter-"                tien to ten host (ten instance viet HOA)
  --ip 10.16.16.38                         IP server exporter (mac dinh: tu dong phat hien)
  --conf /etc/esxi-host-exporter           thu muc .env cua instance

An toan: host da co thi CAP NHAT (giu nguyen host group / template / macro khac da co, chi
set lai {$ESXI.EXPORTER.URL}); chua co thi tao moi. Chay lai nhieu lan khong tao trung.
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
    plan = []
    for name, port in insts:
        host = prefix + name.upper()
        url = "http://%s:%s/metrics" % (ip, port)
        ex = z.call("host.get", {"filter": {"host": [host]}, "output": ["hostid"],
                                 "selectMacros": "extend", "selectParentTemplates": ["templateid"],
                                 "selectGroups": ["groupid"]})
        plan.append(("cap nhat" if ex else "tao moi", host, url, ex[0] if ex else None))

    print("\nSe xu ly %d host (group '%s', template '%s', IP %s):" % (len(plan), group, template, ip))
    for action, host, url, _ in plan:
        print("  [%s] %-26s %s" % (action, host, url))
    if not apply_:
        print("\nXem truoc (chua ghi). Chay lai voi --apply de tao/cap nhat that.")
        return

    for action, host, url, cur in plan:
        if cur is None:
            z.call("host.create", {"host": host, "groups": [{"groupid": gid}],
                                   "templates": [{"templateid": tid}],
                                   "macros": [{"macro": MURL, "value": url}]})
            print("  tao %s" % host)
        else:
            macros = [{"macro": m["macro"], "value": m["value"]}
                      for m in cur.get("macros", []) if m["macro"] != MURL]
            macros.append({"macro": MURL, "value": url})
            gids = {g["groupid"] for g in cur.get("hostgroups", cur.get("groups", []))}
            gids.add(gid)
            params = {"hostid": cur["hostid"], "macros": macros,
                      "groups": [{"groupid": g} for g in gids]}
            tids = {t["templateid"] for t in cur.get("parentTemplates", [])}
            if tid not in tids:
                params["templates"] = [{"templateid": t} for t in tids | {tid}]
            z.call("host.update", params)
            print("  cap nhat %s" % host)
    print("Xong: %d host." % len(plan))


if __name__ == "__main__":
    main()
