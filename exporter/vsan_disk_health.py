#!/usr/bin/env python3
"""Lay vSAN physical disk health tu vCenter (giong cot Health o vSAN > Disk Management).

Cach dung:
  python vsan_disk_health.py <vcenter> <user> [cluster] [file_output.json | dashboard.html] [interval_giay]
  Mat khau doc tu bien moi truong VSAN_PASS, neu khong co se hoi khi chay.
  Co interval_giay -> chay lien tuc, cu moi interval giay lay lai du lieu va ghi de file (Ctrl+C de dung).
  VSAN_FRESH=1 -> bat vCenter chay lai health check moi lan (mac dinh doc cache cua vSAN health).

Prometheus exporter (cho Grafana):
  python vsan_disk_health.py <vcenter> <user> [cluster] :9810 [interval_giay, mac dinh 120]
  -> http://<may>:9810/metrics, metric vsan_disk_* (0=green,1=yellow,2=red,3=unknown)

Output: JSON list, moi phan tu la 1 disk -> dung lam master item + LLD trong Zabbix.
  health: green / yellow / red / unknown
"""
import datetime
import getpass
import json
import os
import ssl
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import SoapStubAdapter, VmomiSupport, vim

VSAN_VERSIONS = [
    "vsan.version.v9_1_0_0", "vsan.version.v9_0_0_0",
    "vsan.version.version23", "vsan.version.version22", "vsan.version.version21",
    "vsan.version.version20", "vsan.version.version19", "vsan.version.version18",
    "vsan.version.version17", "vsan.version.version16", "vsan.version.version15",
    "vsan.version.version14", "vsan.version.version13", "vsan.version.version12",
    "vsan.version.version11", "vsan.version.version10", "vsan.version.version3",
    "vim.version.version9",
]


def vsan_api_version(host, ctx):
    """Chon version vSAN API moi nhat ma ca vCenter va pyVmomi deu ho tro."""
    try:
        url = "https://%s/sdk/vsanServiceVersions.xml" % host
        root = ET.fromstring(urllib.request.urlopen(url, context=ctx, timeout=15).read())
        supported = {v.text for v in root.iter("version")}
    except Exception:
        return "vim.version.version9"
    for v in VSAN_VERSIONS:
        if VmomiSupport.versionIdMap.get(v) in supported:
            return v
    return "vim.version.version9"


def vsan_health_system(si, host, ctx):
    version = vsan_api_version(host, ctx)
    stub = SoapStubAdapter(host=host, port=443, path="/vsanHealth", version=version,
                           sslContext=ctx)
    stub.cookie = si._stub.cookie
    return vim.cluster.VsanVcClusterHealthSystem("vsan-cluster-health-system", stub)


def read_password():
    """Mat khau: bien moi truong VSAN_PASS -> file VSAN_PASS_FILE / .vsan_pass canh script -> hoi khi chay."""
    if os.environ.get("VSAN_PASS"):
        return os.environ["VSAN_PASS"]
    path = os.environ.get("VSAN_PASS_FILE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".vsan_pass")
    if os.path.isfile(path):
        with open(path, encoding="utf-8-sig") as f:  # utf-8-sig: bo BOM neu luu bang Notepad
            pwd = f.readline().rstrip("\r\n")
        if pwd:
            print("Doc mat khau tu %s" % path, flush=True)
            return pwd
    return getpass.getpass("Password: ")


def render_html(rows, out_file, meta):
    """Ghi dashboard HTML tu dashboard_template.html (cung thu muc voi script)."""
    meta = dict(meta)
    meta.setdefault("generated", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_template.html")
    with open(tpl_path, encoding="utf-8") as f:
        html = f.read()
    # Escape "</" de du lieu khong the dong the <script>
    dump = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("__VSAN_DATA__", dump(rows)).replace("__VSAN_META__", dump(meta))
    # Ghi ra file tam roi doi ten, de trinh duyet khong doc phai file dang ghi do
    with open(out_file + ".tmp", "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(out_file + ".tmp", out_file)


def host_issue(cluster, host, reason):
    return {"cluster": cluster, "host": host, "disk": "", "uuid": "",
            "health": "unknown", "op_health": "unknown", "reason": reason,
            "capacity_health": "", "congestion_health": "", "metadata_health": ""}


def collect(host, user, pwd, cluster_filter, fresh=False):
    """Dang nhap vCenter, lay health cua tung disk vSAN, roi dang xuat."""
    ctx = ssl._create_unverified_context()
    si = SmartConnect(host=host, user=user, pwd=pwd, sslContext=ctx)
    try:
        return collect_si(si, host, ctx, cluster_filter, fresh)
    finally:
        Disconnect(si)


def vsan_clusters(si, cluster_filter):
    view = si.content.viewManager.CreateContainerView(
        si.content.rootFolder, [vim.ClusterComputeResource], True)
    try:
        return [c for c in view.view
                if c.configurationEx.vsanConfigInfo.enabled
                and (cluster_filter is None or c.name == cluster_filter)]
    finally:
        view.Destroy()


def collect_si(si, host, ctx, cluster_filter, fresh=False, overall=None):
    """overall (dict, tuy chon): ghi them health tong cua tung cluster vSAN {ten cluster: green/yellow/red}."""
    """Lay health tung disk vSAN tren mot session vCenter co san."""
    hs = vsan_health_system(si, host, ctx)
    clusters = vsan_clusters(si, cluster_filter)
    out = []
    for cluster in clusters:
        summary = hs.VsanQueryVcClusterHealthSummary(
            cluster=cluster, fetchFromCache=not fresh, fields=["physicalDisksHealth", "overallHealth"])
        if overall is not None:
            overall[cluster.name] = summary.overallHealth
        reported = set()
        for h in summary.physicalDisksHealth or []:
            reported.add(h.hostname)
            if h.error or not h.disks:
                out.append(host_issue(cluster.name, h.hostname,
                                      h.error.msg if h.error else "khong co disk nao"))
            for d in h.disks or []:
                out.append({
                    "cluster": cluster.name,
                    "host": h.hostname,
                    "disk": d.name,
                    "uuid": d.uuid,
                    "health": d.summaryHealth,
                    "op_health": d.operationalHealth,
                    "reason": d.operationalHealthDescription,
                    "capacity_health": d.capacityHealth,
                    "congestion_health": d.congestionHealth,
                    "metadata_health": d.metadataHealth,
                    "congestion_value": d.congestionValue,
                    "used_ratio": (round(d.usedCapacity / d.capacity, 4)
                                   if d.capacity and d.usedCapacity is not None else None),
                    "diskgroup": getattr(d, "vsanDiskGroupUuid", None) or "",
                })
        # Host co trong cluster nhung vSAN health khong tra ve du lieu disk
        for esx in cluster.host:
            if esx.name not in reported:
                out.append(host_issue(cluster.name, esx.name,
                                      "khong co trong ket qua vSAN health (state: %s)"
                                      % esx.runtime.connectionState))
    return out


HEALTH_CODE = {"green": 0, "yellow": 1, "red": 2}  # con lai (unknown, rong) = 3


def _code(h):
    return HEALTH_CODE.get(h, 3)


def _lbl(**kv):
    esc = lambda v: str(v if v is not None else "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return "{" + ",".join('%s="%s"' % (k, esc(v)) for k, v in kv.items()) + "}"


def prometheus_text(rows, state):
    """Chuyen ket qua sang dinh dang Prometheus text exposition."""
    m = {}

    def add(name, help_, labels, value):
        m.setdefault(name, (help_, []))[1].append("%s%s %s" % (name, labels, value))

    for r in rows:
        if not r["disk"]:
            add("vsan_host_disk_unreported", "Host co trong cluster nhung vSAN health khong tra ve disk (1=co van de)",
                _lbl(cluster=r["cluster"], host=r["host"], reason=r["reason"]), 1)
            continue
        base = dict(cluster=r["cluster"], host=r["host"], disk=r["disk"])
        add("vsan_disk_health", "Health tong hop cua disk vSAN (0=green,1=yellow,2=red,3=unknown)",
            _lbl(**base), _code(r["health"]))
        for k in ("op_health", "metadata_health", "capacity_health", "congestion_health"):
            add("vsan_disk_" + k, "Health thanh phan %s (0=green,1=yellow,2=red,3=unknown)" % k,
                _lbl(**base), _code(r[k]))
        add("vsan_disk_info", "Thong tin chu cua disk (gia tri luon = 1)",
            _lbl(uuid=r["uuid"], diskgroup=r.get("diskgroup", ""), health=r["health"] or "unknown",
                 op_health=r["op_health"] or "unknown", metadata_health=r["metadata_health"] or "unknown",
                 reason=r["reason"], **base), 1)
        if r.get("congestion_value") is not None:
            add("vsan_disk_congestion_value", "Chi so congestion cua disk (0-255)", _lbl(**base), r["congestion_value"])
        if r.get("used_ratio") is not None:
            add("vsan_disk_used_ratio", "Ti le dung luong da dung (0-1)", _lbl(**base), r["used_ratio"])

    add("vsan_disk_exporter_up", "Lan lay du lieu gan nhat tu vCenter thanh cong (1) hay loi (0)", "", state["up"])
    add("vsan_disk_exporter_last_success_timestamp_seconds", "Thoi diem lay du lieu thanh cong gan nhat",
        "", state["last_success"])
    add("vsan_disk_exporter_collect_duration_seconds", "Thoi gian lay du lieu tu vCenter", "", state["duration"])

    lines = []
    for name, (help_, samples) in m.items():
        lines += ["# HELP %s %s" % (name, help_), "# TYPE %s gauge" % name] + samples
    return "\n".join(lines) + "\n"


def run_exporter(port, interval, host, user, pwd, cluster_filter, fresh):
    """Chay HTTP /metrics cho Prometheus; thread nen lay du lieu tu vCenter moi <interval> giay."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    state = {"rows": [], "up": 0, "last_success": 0, "duration": 0}
    lock = threading.Lock()

    def loop():
        while True:
            t0 = time.time()
            try:
                rows = collect(host, user, pwd, cluster_filter, fresh)
                with lock:
                    state.update(rows=rows, up=1, last_success=int(time.time()), duration=round(time.time() - t0, 2))
                bad = sum(1 for r in rows if r["health"] != "green")
                print("[%s] OK: %d dong, %d khong green" % (time.strftime("%H:%M:%S"), len(rows), bad), flush=True)
            except vim.fault.InvalidLogin:
                print("Dang nhap that bai: sai user hoac mat khau. Dung exporter.", flush=True)
                os._exit(3)  # ma 3 = sai mat khau, xem RestartPreventExitStatus trong systemd unit
            except Exception as e:  # giu du lieu cu, bao up=0 de Grafana/alert biet
                with lock:
                    state.update(up=0, duration=round(time.time() - t0, 2))
                print("[%s] LOI: %s" % (time.strftime("%H:%M:%S"), getattr(e, "msg", None) or e), flush=True)
            time.sleep(interval)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] != "/metrics":
                self.send_error(404, "Dung /metrics")
                return
            with lock:
                body = prometheus_text(state["rows"], state).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    threading.Thread(target=loop, daemon=True).start()
    print("vSAN disk exporter: http://0.0.0.0:%d/metrics (lay du lieu moi %ds)" % (port, interval), flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


def write_output(out, out_file, meta):
    bad = [x for x in out if x["health"] != "green"]
    if out_file and out_file.lower().endswith(".html"):
        render_html(out, out_file, meta)
        print("Da tao dashboard %s (%d dong, %d dong khong green)." % (out_file, len(out), len(bad)))
    elif out_file:
        with open(out_file + ".tmp", "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        os.replace(out_file + ".tmp", out_file)
        print("Da ghi %d dong vao %s, %d dong khong green." % (len(out), out_file, len(bad)))
    else:
        print(json.dumps(out, ensure_ascii=False))


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    host = sys.argv[1].replace("https://", "").split("/")[0]
    user = sys.argv[2]
    cluster_filter = sys.argv[3] if len(sys.argv) > 3 else None
    out_file = sys.argv[4] if len(sys.argv) > 4 else None
    interval = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    fresh = os.environ.get("VSAN_FRESH") == "1"
    pwd = read_password()

    if out_file and out_file.startswith(":"):  # che do Prometheus exporter, vd ":9810"
        run_exporter(int(out_file[1:]), interval or 120, host, user, pwd, cluster_filter, fresh)
        return

    if not interval:
        out = collect(host, user, pwd, cluster_filter, fresh)
        write_output(out, out_file, {"cluster": cluster_filter or "", "vcenter": host})
        return

    # Che do chay lien tuc: lap moi <interval> giay, Ctrl+C de dung
    last = []
    while True:
        meta = {"cluster": cluster_filter or "", "vcenter": host, "refresh": interval,
                "ts": int(time.time() * 1000)}
        try:
            last = collect(host, user, pwd, cluster_filter, fresh)
        except (KeyboardInterrupt, vim.fault.InvalidLogin):
            raise  # sai mat khau thi dung han, khong lap lai
        except Exception as e:  # loi mang / vCenter: giu du lieu cu, bao loi tren dashboard
            meta["error"] = "Lan lay du lieu luc %s that bai: %s" % (
                datetime.datetime.now().strftime("%H:%M:%S"), getattr(e, "msg", None) or e)
            print(meta["error"])
        print("[%s] " % datetime.datetime.now().strftime("%H:%M:%S"), end="")
        write_output(last, out_file, meta)
        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except vim.fault.InvalidLogin:
        sys.exit("Dang nhap that bai: sai user hoac mat khau (hoac tai khoan dang bi khoa).")
    except KeyboardInterrupt:
        sys.exit("Da dung.")
