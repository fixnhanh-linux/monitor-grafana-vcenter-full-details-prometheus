#!/usr/bin/env python3
"""Chen muc "vSAN Cluster Partition" vao dashboard Grafana DANG CHAY, giu nguyen moi thu da sua tay
(ten row, panel, nguong...). Chi them 1 row + 2 panel ngay duoi bang ESXi Hosts, day cac panel ben duoi xuong.

Cach dung:
  set GRAFANA_TOKEN=glsa_xxx        (Windows)   |   export GRAFANA_TOKEN=glsa_xxx   (Linux)
  python add_vsan_partition_panels.py https://42.117.4.233:3000            # xem truoc, KHONG ghi
  python add_vsan_partition_panels.py https://42.117.4.233:3000 --apply    # ghi that

  Token: Grafana > Administration > Users and access > Service accounts > Add (role Editor) > Add token.
  Tuy chon: --uid esxi-host-resource (mac dinh)   --src esxi_host_resource_grafana.json (file chua 3 panel moi)
            --backup-dir <thu muc> (mac dinh: canh script)
  Tren server: menu muc 16 (Cap nhat Grafana) chay script nay.

- Truoc khi ghi luon luu backup: backup-<uid>-<gio>.json (trong --backup-dir).
- Ghi kem "version" hien tai: neu ai vua sua dashboard trong luc chay -> Grafana tu choi, khong ghi de.
- Chay lai lan 2 khong them trung (da co row "vSAN Cluster Partition" thi dung, ma thoat 3).
- Quay lai ban cu: Dashboard > Edit > Settings > Versions > Restore.
"""
import copy
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
NEW_IDS = (40, 41, 42)          # row + stat + table trong file nguon
ROW_TITLE = "vSAN Cluster Partition"
ANCHOR_ID = 8                   # bang "ESXi Hosts": chen ngay ben duoi


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def api(base, token, path, body=None):
    req = urllib.request.Request(base.rstrip("/") + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl._create_unverified_context()) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit("Grafana tra loi %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300]))


def all_panels(panels):
    for p in panels:
        yield p
        yield from p.get("panels") or []  # panel nam trong row dang thu gon


def merge(dash, new_panels):
    """Tra ve so dong da day xuong; None neu dashboard da co muc partition."""
    if any(p.get("type") == "row" and ROW_TITLE.lower() in (p.get("title") or "").lower() for p in all_panels(dash["panels"])):
        return None
    anchor = next((p for p in dash["panels"] if p.get("id") == ANCHOR_ID), None)
    if anchor:
        y0 = anchor["gridPos"]["y"] + anchor["gridPos"]["h"]
        pos = dash["panels"].index(anchor) + 1
    else:  # khong thay bang host (da xoa / doi id): chen xuong cuoi
        y0 = max([p["gridPos"]["y"] + p["gridPos"]["h"] for p in all_panels(dash["panels"])] or [0])
        pos = len(dash["panels"])
    height = max(p["gridPos"]["y"] + p["gridPos"]["h"] for p in new_panels) - min(p["gridPos"]["y"] for p in new_panels)
    for p in all_panels(dash["panels"]):
        if p["gridPos"]["y"] >= y0:
            p["gridPos"]["y"] += height
    used = {p.get("id") for p in all_panels(dash["panels"])}
    nid = max([i for i in used if isinstance(i, int)] or [0]) + 1
    top = min(p["gridPos"]["y"] for p in new_panels)
    add = []
    for p in new_panels:
        p = copy.deepcopy(p)
        p["gridPos"]["y"] = y0 + p["gridPos"]["y"] - top
        if p["id"] in used:  # trung id voi panel ban tu them -> cap id moi
            p["id"], nid = nid, nid + 1
        add.append(p)
    dash["panels"][pos:pos] = add
    return height


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("-"):
        sys.exit(__doc__)
    base, uid = sys.argv[1], arg("--uid", "esxi-host-resource")
    token = os.environ.get("GRAFANA_TOKEN") or sys.exit("Chua dat bien moi truong GRAFANA_TOKEN (xem huong dan dau file).")
    src = json.load(open(arg("--src", os.path.join(HERE, "esxi_host_resource_grafana.json")), encoding="utf-8"))
    new_panels = [p for p in src["panels"] if p.get("id") in NEW_IDS]
    if len(new_panels) != len(NEW_IDS):
        sys.exit("File nguon chua co 3 panel partition (id %s) - lay ban moi tu GitHub." % (NEW_IDS,))

    cur = api(base, token, "/api/dashboards/uid/" + uid)
    dash, meta = cur["dashboard"], cur["meta"]
    print("Dashboard: %s (uid %s, version %s, folder %s)" % (dash["title"], uid, dash.get("version"), meta.get("folderTitle", "General")))
    height = merge(dash, new_panels)
    if height is None:
        print("Da co muc '%s' -> khong lam gi." % ROW_TITLE)
        sys.exit(3)
    print("Se them row '%s' + 2 panel, day cac panel ben duoi xuong %d dong. Ten row / panel cu giu nguyen." % (ROW_TITLE, height))
    if "--apply" not in sys.argv:
        print("Chua ghi (xem truoc). Chay lai voi --apply de ghi.")
        return

    bdir = arg("--backup-dir", HERE)
    os.makedirs(bdir, exist_ok=True)
    bk = os.path.join(bdir, "backup-%s-%s.json" % (uid, time.strftime("%Y%m%d-%H%M%S")))
    with open(bk, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)
    print("Da luu backup: %s" % bk)
    r = api(base, token, "/api/dashboards/db", {"dashboard": dash, "folderUid": meta.get("folderUid", ""),
                                                "overwrite": False, "message": "Them muc vSAN Cluster Partition (script)"})
    print("Xong: version %s -> %s. Tai lai trang dashboard (F5)." % (dash.get("version"), r.get("version")))


if __name__ == "__main__":
    main()
