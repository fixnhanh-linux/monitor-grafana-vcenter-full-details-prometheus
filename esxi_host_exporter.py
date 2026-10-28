#!/usr/bin/env python3
"""Prometheus exporter: tai nguyen tung host ESXi + vSAN cho dashboard "MONITOR RESOURCE HOST ESXi".

Cach dung:
  python esxi_host_exporter.py <vcenter> <user> [cluster|-] [port, mac dinh 9811] [interval_giay, mac dinh 60]
  Mat khau: bien moi truong VSAN_PASS, hoac dong dau file .vsan_pass canh script, neu khong co se hoi khi chay.
  cluster = "-" -> lay tat ca cluster cua vCenter.

Nguong trang thai (doi bang bien moi truong):
  ESXI_WARN_CPU=60  ESXI_WARN_RAM=90  ESXI_WARN_LATENCY_MS=15  ESXI_WARN_CONGESTION=60  ESXI_WARN_VMK_DROP_PCT=0.1
  ESXI_NIC_MIN_MBPS=10000  (chi theo doi vmnic >= 10GB; 0 = tat ca)

Day len InfluxDB (tuy chon) sau moi vong lay du lieu:
  InfluxDB 2.x: INFLUX_URL=http://ip:8086 INFLUX_TOKEN=... INFLUX_ORG=... INFLUX_BUCKET=vmware
  InfluxDB 1.x: INFLUX_URL=http://ip:8086 INFLUX_DB=vmware [INFLUX_USER=... INFLUX_PASSWORD=...]

Metric xuat ra:
  esxi_host_*        CPU, RAM, uptime, VM, latency, trang thai tong hop (0=OK,1=WARN,2=ERROR)
  esxi_host_nic_*    tung vmnic uplink: link up/down, toc do, Mb/s TX/RX
  esxi_host_vmk_*    tung vmk: % drop/discard, danh dau vmk dung cho vSAN
  esxi_vsan_*        health disk group, congestion, resync cua cluster
  vsan_disk_*        health tung disk (giong vsan_disk_health.py)
"""
import base64
import datetime
import json
import os
import re
import urllib.parse
import urllib.request
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import SoapStubAdapter, vim, vmodl

import vsan_disk_health as vdh

# Tang moi lan phat hanh goi zip; kiem tra ban dang chay: curl -s localhost:9811/metrics | grep build_info
VERSION = "2026.10.28-1"

WARN = {
    "cpu": float(os.environ.get("ESXI_WARN_CPU", 60)),
    "ram": float(os.environ.get("ESXI_WARN_RAM", 90)),
    "latency": float(os.environ.get("ESXI_WARN_LATENCY_MS", 15)),
    "congestion": float(os.environ.get("ESXI_WARN_CONGESTION", 60)),
    "vmk_drop": float(os.environ.get("ESXI_WARN_VMK_DROP_PCT", 0.1)),
}

# Chi theo doi vmnic uplink co toc do toi da >= nguong nay (mac dinh 10GB). 0 = theo doi tat ca.
NIC_MIN_MBPS = int(os.environ.get("ESXI_NIC_MIN_MBPS", 10000))

PERF_COUNTERS = [
    "net.transmitted.average", "net.received.average",          # KBps
    "net.packetsTx.summation", "net.packetsRx.summation",       # goi / 20s
    "net.droppedTx.summation", "net.droppedRx.summation",       # goi / 20s
]
# Latency KHONG lay tu counter datastore/disk cua host: voi NVMe chung luon = 0 (lam tron ms).
# Dung vSAN Performance Service (host-domclient) - cung so lieu voi bieu do vSAN tren vCenter.

HOST_PROPS = [
    "name", "parent", "runtime.connectionState", "runtime.inMaintenanceMode",
    "summary.quickStats", "summary.hardware", "config.network",
    "config.virtualNicManagerInfo.netConfig", "config.vsanHostConfig.clusterInfo.nodeUuid",
]

# Phan nang (vSAN disk health ~35s, dem VM ~9s) chi lay moi SLOW_INTERVAL giay;
# vSAN health cung chi duoc vCenter cap nhat theo cache nen lay day hon khong co loi.
SLOW_INTERVAL = int(os.environ.get("ESXI_SLOW_INTERVAL", 300))


def retrieve(si, obj_type, props):
    """Lay nhieu thuoc tinh cua moi doi tuong trong 1-2 lan goi (thay vi goi tung thuoc tinh)."""
    pc = si.content.propertyCollector
    view = si.content.viewManager.CreateContainerView(si.content.rootFolder, [obj_type], True)
    PC = vmodl.query.PropertyCollector
    try:
        spec = PC.FilterSpec(
            objectSet=[PC.ObjectSpec(obj=view, skip=True, selectSet=[
                PC.TraversalSpec(name="v", path="view", skip=False, type=vim.view.ContainerView)])],
            propSet=[PC.PropertySpec(type=obj_type, pathSet=props)])
        out = []
        res = pc.RetrievePropertiesEx([spec], PC.RetrieveOptions())
        while res:
            for o in res.objects:
                out.append((o.obj, {p.name: p.val for p in o.propSet or []}))
            res = pc.ContinueRetrievePropertiesEx(res.token) if res.token else None
        return out
    finally:
        view.Destroy()


def vsan_mo(si, vc, ctx, mo_type, mo_id):
    stub = SoapStubAdapter(host=vc, port=443, path="/vsanHealth",
                           version=vdh.vsan_api_version(vc, ctx), sslContext=ctx)
    stub.cookie = si._stub.cookie
    return mo_type(mo_id, stub)


def query_perf(si, hosts):
    """Mau realtime (20s) moi nhat cho cac counter mang/latency cua host."""
    pm = si.content.perfManager
    wanted = {}
    for c in pm.perfCounter:
        name = "%s.%s.%s" % (c.groupInfo.key, c.nameInfo.key, c.rollupType)
        if name in PERF_COUNTERS:
            wanted[c.key] = name
    if not wanted or not hosts:
        return {}
    mids = [vim.PerformanceManager.MetricId(counterId=k, instance="*") for k in wanted]
    result = {}
    for i in range(0, len(hosts), 10):  # chia lo nho: vCenter hay tra "Service Unavailable" khi lo lon
        specs = [vim.PerformanceManager.QuerySpec(entity=h, metricId=mids, intervalId=20, maxSample=1)
                 for h in hosts[i:i + 10]]
        for attempt in (1, 2):
            try:
                for em in pm.QueryPerf(specs):
                    d = result.setdefault(em.entity._moId, {})
                    for s in em.value:
                        if s.value:
                            d[(wanted[s.id.counterId], s.id.instance)] = float(s.value[-1])
                break
            except Exception as e:
                print("QueryPerf loi (lan %d): %s" % (attempt, getattr(e, "msg", None) or e), flush=True)
                time.sleep(2)
    return result


def vsan_perf(si, vc, ctx, clusters):
    """vSAN latency/congestion moi nhat cua tung host (mau 5 phut). Tra ve {nodeUuid: {...}}."""
    out = {}
    try:
        pm = vsan_mo(si, vc, ctx, vim.cluster.VsanPerformanceManager, "vsan-performance-manager")
        end = datetime.datetime.now(datetime.timezone.utc)
        for c in clusters:
            res = pm.VsanPerfQueryPerf(querySpecs=[vim.cluster.VsanPerfQuerySpec(
                entityRefId="host-domclient:*", startTime=end - datetime.timedelta(minutes=15), endTime=end,
                labels=["latencyAvgWrite", "latencyAvgRead", "congestion"])], cluster=c)
            for e in res or []:
                vals = {}
                for v in e.value or []:
                    last = [x for x in (v.values or "").split(",") if x not in ("", "None")]
                    if last:
                        vals[v.metricId.label] = float(last[-1])
                out[e.entityRefId.split(":", 1)[1]] = vals
    except Exception as e:
        print("Khong lay duoc vSAN performance: %s" % (getattr(e, "msg", None) or e), flush=True)
    return out


def host_network(cfg_net, nic_mgr):
    """Tra ve (uplinks {device: speedMb|None}, vmks {device: is_vsan})."""
    uplink_keys = set()
    for sw in (cfg_net.vswitch or []):
        uplink_keys.update(sw.pnic or [])
    for psw in (cfg_net.proxySwitch or []):
        uplink_keys.update(psw.pnic or [])
    uplinks = {}
    for p in cfg_net.pnic or []:
        if p.key not in uplink_keys:  # chi theo doi vmnic dang gan vao vSwitch/DVS, bo cong khong dung
            continue
        cur = p.linkSpeed.speedMb if p.linkSpeed else None
        # Toc do toi da NIC ho tro (van co khi link DOWN) -> bo NIC cham hon NIC_MIN_MBPS (vd 1GB).
        cap = max([cur or 0] + [s.speedMb for s in (getattr(p, "validLinkSpecification", None) or [])])
        if cap and cap < NIC_MIN_MBPS:
            continue
        uplinks[p.device] = cur
    vsan_vmks = set()
    for nc in nic_mgr or []:
        if nc.nicType == "vsan":
            sel = set(nc.selectedVnic or [])
            vsan_vmks.update(c.device for c in nc.candidateVnic or [] if c.key in sel)
    vmks = {v.device: v.device in vsan_vmks for v in cfg_net.vnic or []}
    return uplinks, vmks


CLUSTER_PROPS = ["name", "summary", "overallStatus", "configurationEx", "datastore"]
DRS_CODE = {"manual": 1, "partiallyAutomated": 2, "fullyAutomated": 3}  # 0 = DRS tat
COLOR_CODE = {"green": 0, "yellow": 1, "red": 2}  # con lai (gray/unknown) = 3


def cluster_stats(si, cl_props, hosts, cluster_filter, vsan_overall):
    """So lieu tong cua tung cluster cho dashboard luoi o (DRS, tong CPU/RAM, vSAN datastore, so VM)."""
    ds = {o._moId: p for o, p in retrieve(si, vim.Datastore, ["summary.type", "summary.capacity",
                                                               "summary.freeSpace"])}
    used = {}
    for _, p in hosts:
        if p["runtime.connectionState"] != "connected":
            continue
        qs = p["summary.quickStats"]
        u = used.setdefault(p["parent"]._moId, [0, 0])
        u[0] += (qs.overallCpuUsage or 0) * 1e6          # MHz -> Hz
        u[1] += (qs.overallMemoryUsage or 0) * 1048576   # MB -> bytes
    out = []
    for o, p in cl_props:
        if cluster_filter is not None and p["name"] != cluster_filter:
            continue
        s, cfg = p["summary"], p.get("configurationEx")
        drs = getattr(cfg, "drsConfig", None)
        vsan_ds = [ds[d._moId] for d in p.get("datastore") or [] if ds.get(d._moId, {}).get("summary.type") == "vsan"]
        us = getattr(s, "usageSummary", None)
        out.append({
            "cluster": p["name"],
            "status": COLOR_CODE.get(str(p.get("overallStatus")), 3),
            "vsan_health": COLOR_CODE.get(vsan_overall.get(p["name"]), 3) if p["name"] in vsan_overall else None,
            "drs": DRS_CODE.get(str(drs.defaultVmBehavior), 1) if drs and drs.enabled else 0,
            "hosts": s.numHosts or 0,
            "hosts_effective": s.numEffectiveHosts or 0,
            "vms_total": us.totalVmCount if us else None,
            "vms_off": us.poweredOffVmCount if us else None,
            "cpu_total_hz": (s.totalCpu or 0) * 1e6,
            "mem_total_bytes": s.totalMemory or 0,
            "cpu_used_hz": used.get(o._moId, [0, 0])[0],
            "mem_used_bytes": used.get(o._moId, [0, 0])[1],
            "vsan_capacity": sum(d["summary.capacity"] for d in vsan_ds) if vsan_ds else None,
            "vsan_free": sum(d["summary.freeSpace"] for d in vsan_ds) if vsan_ds else None,
        })
    return out


def collect(vc, user, pwd, cluster_filter, fresh=False, cache=None):
    """Lay du lieu 1 vong. cache giu phan nang (disk health, so VM) giua cac vong, lam moi moi SLOW_INTERVAL."""
    cache = cache if cache is not None else {}
    ctx = ssl._create_unverified_context()
    si = SmartConnect(host=vc, user=user, pwd=pwd, sslContext=ctx)
    try:
        cl_props = retrieve(si, vim.ClusterComputeResource, CLUSTER_PROPS)
        clusters = {o._moId: p["name"] for o, p in cl_props}
        hosts = [(o, p) for o, p in retrieve(si, vim.HostSystem, HOST_PROPS)
                 if cluster_filter is None or clusters.get(p["parent"]._moId) == cluster_filter]
        vsan_cl = vdh.vsan_clusters(si, cluster_filter)

        if time.time() - cache.get("slow_ts", 0) >= SLOW_INTERVAL:
            running = {}
            for _, p in retrieve(si, vim.VirtualMachine, ["runtime.host", "runtime.powerState"]):
                if p.get("runtime.powerState") == "poweredOn" and p.get("runtime.host") is not None:
                    running[p["runtime.host"]._moId] = running.get(p["runtime.host"]._moId, 0) + 1
            overall = {}
            cache.update(running=running, disks=vdh.collect_si(si, vc, ctx, cluster_filter, fresh, overall),
                         vsan_overall=overall, slow_ts=time.time())
        running, disks = cache["running"], cache["disks"]
        cl_stats = cluster_stats(si, cl_props, hosts, cluster_filter, cache.get("vsan_overall", {}))

        connected = [o for o, p in hosts if p["runtime.connectionState"] == "connected"]
        perf = query_perf(si, connected)
        vperf = vsan_perf(si, vc, ctx, vsan_cl)

        resync = {}
        try:
            obj_sys = vsan_mo(si, vc, ctx, vim.cluster.VsanObjectSystem, "vsan-cluster-object-system")
            for c in vsan_cl:
                r = obj_sys.QuerySyncingVsanObjectsSummary(cluster=c)
                resync[c.name] = (r.totalObjectsToSync or 0, r.totalBytesToSync or 0, r.totalRecoveryETA or 0)
        except Exception as e:
            print("Khong lay duoc resync: %s" % (getattr(e, "msg", None) or e), flush=True)

        out = []
        for o, p in hosts:
            qs, hw = p["summary.quickStats"], p["summary.hardware"]
            cpu_cap = (hw.cpuMhz or 0) * (hw.numCpuCores or 0)
            pf = perf.get(o._moId, {})
            uplinks, vmks = host_network(p["config.network"], p.get("config.virtualNicManagerInfo.netConfig")) \
                if p.get("config.network") else ({}, {})

            nics = {}
            for dev, speed in uplinks.items():
                nics[dev] = {"up": speed is not None, "speed": speed or 0,
                             "tx_mbps": pf.get(("net.transmitted.average", dev), 0) * 8.192 / 1000,
                             "rx_mbps": pf.get(("net.received.average", dev), 0) * 8.192 / 1000}
            vmk_ip = {v.device: getattr(getattr(v.spec, "ip", None), "ipAddress", "") or ""
                      for v in (p["config.network"].vnic or [])} if p.get("config.network") else {}
            vmk = {}
            for dev, is_vsan in vmks.items():
                d = {"vsan": is_vsan, "ip": vmk_ip.get(dev, "")}
                for dirn, pk, dr in (("rx", "net.packetsRx.summation", "net.droppedRx.summation"),
                                     ("tx", "net.packetsTx.summation", "net.droppedTx.summation")):
                    pk_v, dr_v = pf.get((pk, dev), 0), pf.get((dr, dev), 0)
                    d["drop_" + dirn] = dr_v
                    d["drop_pct_" + dirn] = (dr_v / (pk_v + dr_v) * 100) if (pk_v + dr_v) else 0
                vmk[dev] = d

            vp = vperf.get(p.get("config.vsanHostConfig.clusterInfo.nodeUuid") or "-", {})
            lat = lambda k: vp[k] / 1000 if k in vp else None  # micro-giay -> ms
            out.append({
                "cluster": clusters.get(p["parent"]._moId, "Standalone"),
                "host": p["name"],
                "state": str(p["runtime.connectionState"]),
                "maintenance": bool(p.get("runtime.inMaintenanceMode")),
                "cpu_pct": (qs.overallCpuUsage or 0) / cpu_cap * 100 if cpu_cap else 0,
                "ram_pct": (qs.overallMemoryUsage or 0) / (hw.memorySize / 1048576) * 100 if hw.memorySize else 0,
                "uptime_s": qs.uptime or 0,
                "vms": running.get(o._moId, 0),
                "lat_read_ms": lat("latencyAvgRead"),
                "lat_write_ms": lat("latencyAvgWrite"),
                "vsan_congestion": vp.get("congestion"),
                "nics": nics,
                "vmks": vmk,
            })
        return out, disks, resync, cl_stats
    finally:
        Disconnect(si)


def evaluate(h, host_disks):
    """Trang thai tong hop cua host: 0=OK, 1=WARN, 2=ERROR, kem ly do."""
    err, warn = [], []
    if h["state"] != "connected":
        err.append("Host %s" % h["state"])
    down = [n for n, v in sorted(h["nics"].items()) if not v["up"]]
    if down:
        err.append("NIC down: " + ", ".join(down))
    bad = [d for d in host_disks if d["health"] != "green"]
    if bad:
        err.append("Disk Unhealthy: " + ", ".join("%s (%s)" % (d["disk"], d["reason"] or d["health"]) for d in bad))
    if h["maintenance"]:
        warn.append("Maintenance mode")
    if h["cpu_pct"] > WARN["cpu"]:
        warn.append("CPU %.0f%%" % h["cpu_pct"])
    if h["ram_pct"] > WARN["ram"]:
        warn.append("RAM %.0f%%" % h["ram_pct"])
    if (h["lat_write_ms"] or 0) > WARN["latency"]:
        warn.append("vSAN write latency %.0fms" % h["lat_write_ms"])
    cong = max([d.get("congestion_value") or 0 for d in host_disks] + [h.get("vsan_congestion") or 0])
    if cong > WARN["congestion"] or any(d["congestion_health"] not in ("green", None, "") for d in host_disks):
        warn.append("vSAN congestion %d" % cong)
    drops = ["%s %.2f%%" % (n, max(v["drop_pct_rx"], v["drop_pct_tx"])) for n, v in sorted(h["vmks"].items())
             if v["vsan"] and max(v["drop_pct_rx"], v["drop_pct_tx"]) > WARN["vmk_drop"]]
    if drops:
        warn.append("vSAN vmk drop: " + ", ".join(drops))
    status = 2 if err else 1 if warn else 0
    return status, "; ".join(err + warn) or "OK", cong


def prometheus_text(hosts, disks, resync, state, cl=None):
    m = {}

    def add(name, help_, labels, value):
        m.setdefault(name, (help_, []))[1].append("%s%s %s" % (name, vdh._lbl(**labels) if labels else "", value))

    by_host = {}
    for d in disks:
        if d["disk"]:
            by_host.setdefault((d["cluster"], d["host"]), []).append(d)

    for h in hosts:
        L = {"cluster": h["cluster"], "host": h["host"]}
        hd = by_host.get((h["cluster"], h["host"]), [])
        status, reason, cong = evaluate(h, hd)
        # ▲ = UP, ▼ = DOWN; dashboard Grafana to ca o do neu co "▼", xanh neu chi co "▲"
        nic_txt = "  ".join("%s %s" % (n, "▲" if v["up"] else "▼") for n, v in sorted(h["nics"].items())) or "N/A"
        add("esxi_host_status", "Trang thai tong hop (0=OK,1=WARN,2=ERROR)", L, status)
        # nics_up / nics_down tach rieng: Grafana to moi cot 1 mau (UP xanh, DOWN do)
        # "-" thay cho rong: Prometheus bo nhan rong -> cot se bien mat khoi bang Grafana
        nics_up = "  ".join("%s ▲" % n for n, v in sorted(h["nics"].items()) if v["up"]) or "-"
        nics_down = "  ".join("%s ▼" % n for n, v in sorted(h["nics"].items()) if not v["up"]) or "-"
        add("esxi_host_info", "Thong tin chu cua host (gia tri = 1)",
            dict(L, nics=nic_txt, nics_up=nics_up, nics_down=nics_down, reason=reason, connection=h["state"]), 1)
        add("esxi_host_connected", "Host connected voi vCenter (1/0)", L, int(h["state"] == "connected"))
        add("esxi_host_maintenance", "Host dang maintenance mode (1/0)", L, int(h["maintenance"]))
        if h["state"] == "connected":
            add("esxi_host_cpu_usage_percent", "CPU dang dung (%)", L, round(h["cpu_pct"], 2))
            add("esxi_host_mem_usage_percent", "RAM dang dung (%)", L, round(h["ram_pct"], 2))
            add("esxi_host_uptime_seconds", "Thoi gian host chay", L, h["uptime_s"])
            add("esxi_host_vms_running", "So VM dang bat", L, h["vms"])
            if h["lat_write_ms"] is not None:
                add("esxi_vsan_write_latency_ms", "vSAN write latency trung binh cua host (ms, mau 5 phut)", L,
                    round(h["lat_write_ms"], 3))
            if h["lat_read_ms"] is not None:
                add("esxi_vsan_read_latency_ms", "vSAN read latency trung binh cua host (ms, mau 5 phut)", L,
                    round(h["lat_read_ms"], 3))
            for n, v in h["nics"].items():
                NL = dict(L, nic=n)
                add("esxi_host_nic_up", "vmnic uplink co link (1) hay down (0)", NL, int(v["up"]))
                add("esxi_host_nic_speed_mbps", "Toc do link vmnic (Mb/s)", NL, v["speed"])
                add("esxi_host_nic_transmit_mbps", "Bang thong TX cua vmnic (Mb/s, giong MbTX/s esxtop)", NL, round(v["tx_mbps"], 3))
                add("esxi_host_nic_receive_mbps", "Bang thong RX cua vmnic (Mb/s)", NL, round(v["rx_mbps"], 3))
            for n, v in h["vmks"].items():
                VL = dict(L, vmk=n, vsan="true" if v["vsan"] else "false")
                for dirn in ("rx", "tx"):
                    add("esxi_host_vmk_drop_percent", "Ti le goi bi drop/discard tren vmk (%)", dict(VL, direction=dirn),
                        round(v["drop_pct_" + dirn], 4))
                    add("esxi_host_vmk_dropped_packets", "So goi bi drop trong 20s gan nhat", dict(VL, direction=dirn),
                        v["drop_" + dirn])
        if hd:
            add("esxi_vsan_host_disk_health", "Health xau nhat cac disk vSAN cua host (0=green,1=yellow,2=red,3=unknown)",
                L, max(vdh._code(d["health"]) for d in hd))
            add("esxi_vsan_host_disks", "So disk vSAN dang dung", L, len(hd))
            add("esxi_vsan_host_disks_healthy", "So disk vSAN healthy", L, sum(1 for d in hd if d["health"] == "green"))
            add("esxi_vsan_host_congestion", "Congestion cao nhat cac disk cua host (0-255)", L, cong)
            groups = {}
            for d in hd:
                groups.setdefault(d.get("diskgroup") or "storage-pool", []).append(d)
            for g, gd in groups.items():
                add("esxi_vsan_diskgroup_health", "Health disk group (0=green,1=yellow,2=red,3=unknown)",
                    dict(L, diskgroup=g), max(vdh._code(d["health"]) for d in gd))

    for c, (objs, size, eta) in resync.items():
        add("esxi_vsan_resync_objects", "So object vSAN dang resync", {"cluster": c}, objs)
        add("esxi_vsan_resync_bytes", "Dung luong con phai resync (bytes)", {"cluster": c}, size)
        add("esxi_vsan_resync_eta_seconds", "Uoc tinh thoi gian resync con lai", {"cluster": c}, eta)

    for c in cl or []:
        C = {"cluster": c["cluster"]}
        add("esxi_cluster_status", "Trang thai cluster tren vCenter (0=green,1=yellow,2=red,3=gray)", C, c["status"])
        if c["vsan_health"] is not None:
            add("esxi_cluster_vsan_health", "Health tong vSAN cua cluster - Skyline (0=green,1=yellow,2=red,3=unknown)",
                C, c["vsan_health"])
        add("esxi_cluster_drs_mode", "DRS (0=tat,1=manual,2=partiallyAutomated,3=fullyAutomated)", C, c["drs"])
        add("esxi_cluster_hosts", "So host trong cluster", C, c["hosts"])
        add("esxi_cluster_hosts_effective", "So host dang hoat dong (effective)", C, c["hosts_effective"])
        if c["vms_total"] is not None:
            add("esxi_cluster_vms_total", "Tong so VM trong cluster", C, c["vms_total"])
            add("esxi_cluster_vms_powered_off", "So VM dang tat", C, c["vms_off"])
        add("esxi_cluster_cpu_total_hz", "Tong CPU cua cluster (Hz)", C, int(c["cpu_total_hz"]))
        add("esxi_cluster_cpu_used_hz", "CPU dang dung cua cac host (Hz)", C, int(c["cpu_used_hz"]))
        add("esxi_cluster_mem_total_bytes", "Tong RAM cua cluster (bytes)", C, c["mem_total_bytes"])
        add("esxi_cluster_mem_used_bytes", "RAM dang dung cua cac host (bytes)", C, int(c["mem_used_bytes"]))
        if c["vsan_capacity"] is not None:
            add("esxi_cluster_vsan_capacity_bytes", "Dung luong vSAN datastore (bytes)", C, c["vsan_capacity"])
            add("esxi_cluster_vsan_free_bytes", "Dung luong vSAN con trong (bytes)", C, c["vsan_free"])

    add("esxi_exporter_build_info", "Phien ban exporter dang chay (gia tri = 1)", {"version": VERSION}, 1)

    lines = []
    for name, (help_, samples) in m.items():
        lines += ["# HELP %s %s" % (name, help_), "# TYPE %s gauge" % name] + samples
    return "\n".join(lines) + "\n" + vdh.prometheus_text(disks, state)


# ---------- Day metric len InfluxDB (tuy chon, bat khi co INFLUX_URL) ----------
# InfluxDB 2.x: INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET
# InfluxDB 1.x: INFLUX_URL, INFLUX_DB (+ INFLUX_USER, INFLUX_PASSWORD neu co xac thuc)
# Moi metric Prometheus -> 1 measurement cung ten, nhan -> tag, gia tri -> field "value".
INFLUX = {k: os.environ.get(k, "") for k in ("INFLUX_URL", "INFLUX_TOKEN", "INFLUX_ORG", "INFLUX_BUCKET",
                                             "INFLUX_DB", "INFLUX_USER", "INFLUX_PASSWORD")}
_SAMPLE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*)\})? (\S+)$')
_LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')


def _tag_escape(v):
    return v.replace("\\", "\\\\").replace(",", "\\,").replace("=", "\\=").replace(" ", "\\ ")


def influx_lines(prom_text, ts):
    """Chuyen Prometheus text -> InfluxDB line protocol (precision = giay)."""
    out = []
    for line in prom_text.splitlines():
        m = _SAMPLE.match(line)
        if not m:
            continue
        name, labels, value = m.groups()
        try:
            v = float(value)
        except ValueError:
            continue
        if v != v or v in (float("inf"), float("-inf")):  # bo NaN/Inf: Influx khong nhan
            continue
        tags = []
        for k, raw in _LABEL.findall(labels or ""):
            val = raw.replace('\\"', '"').replace("\\\\", "\\")
            if val:  # Influx khong nhan tag rong
                tags.append("%s=%s" % (k, _tag_escape(val)))
        out.append("%s%s value=%r %d" % (name, "," + ",".join(sorted(tags)) if tags else "", v, ts))
    return out


def push_influx(prom_text, ts):
    """Gui 1 lan toan bo metric. Tra ve so dong da gui; loi thi raise de vong lap ghi log."""
    if not INFLUX["INFLUX_URL"]:
        return 0
    base = INFLUX["INFLUX_URL"].rstrip("/")
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    if INFLUX["INFLUX_BUCKET"]:  # InfluxDB 2.x
        url = "%s/api/v2/write?%s" % (base, urllib.parse.urlencode(
            {"org": INFLUX["INFLUX_ORG"], "bucket": INFLUX["INFLUX_BUCKET"], "precision": "s"}))
        headers["Authorization"] = "Token " + INFLUX["INFLUX_TOKEN"]
    else:  # InfluxDB 1.x
        url = "%s/write?%s" % (base, urllib.parse.urlencode({"db": INFLUX["INFLUX_DB"] or "vmware", "precision": "s"}))
        if INFLUX["INFLUX_USER"]:
            cred = base64.b64encode(("%s:%s" % (INFLUX["INFLUX_USER"], INFLUX["INFLUX_PASSWORD"])).encode()).decode()
            headers["Authorization"] = "Basic " + cred
    lines = influx_lines(prom_text, ts)
    for i in range(0, len(lines), 5000):  # chia lo cho Influx de chiu
        req = urllib.request.Request(url, data="\n".join(lines[i:i + 5000]).encode("utf-8"), headers=headers)
        urllib.request.urlopen(req, timeout=20, context=ssl._create_unverified_context()).read()
    return len(lines)


HISTORY_LEN = int(os.environ.get("ESXI_HISTORY_POINTS", 120))  # so diem lich su giu trong RAM cho dashboard web
DASHBOARD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "esxi_dashboard.html")


def host_views(hosts, disks):
    """Gom du lieu tung host + disk + trang thai cho dashboard web."""
    by_host = {}
    for d in disks:
        if d["disk"]:
            by_host.setdefault((d["cluster"], d["host"]), []).append(d)
    views = []
    for h in hosts:
        hd = by_host.get((h["cluster"], h["host"]), [])
        status, reason, cong = evaluate(h, hd)
        views.append(dict(h, status=status, reason=reason, congestion=cong, disks=hd,
                          disk_health=max([vdh._code(d["health"]) for d in hd] or [None]) if hd else None))
    return views


def record_history(history, hosts, ts):
    """Luu 1 diem lich su moi host: CPU, RAM, latency, TX/RX tung vmnic, drop vmk vSAN."""
    for h in hosts:
        if h["state"] != "connected":
            continue
        drop = max([max(v["drop_pct_rx"], v["drop_pct_tx"]) for v in h["vmks"].values() if v["vsan"]] or [0])
        pt = {"t": ts, "cpu": round(h["cpu_pct"], 1), "ram": round(h["ram_pct"], 1),
              "lat": None if h["lat_write_ms"] is None else round(h["lat_write_ms"], 2), "drop": round(drop, 4),
              "nic": {n: [round(v["tx_mbps"], 2), round(v["rx_mbps"], 2)] for n, v in h["nics"].items()}}
        q = history.setdefault(h["host"], [])
        q.append(pt)
        del q[:-HISTORY_LEN]


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    vc = sys.argv[1].replace("https://", "").split("/")[0]
    user = sys.argv[2]
    cluster = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else None
    port = int(sys.argv[4]) if len(sys.argv) > 4 else 9811
    interval = int(sys.argv[5]) if len(sys.argv) > 5 else 60
    fresh = os.environ.get("VSAN_FRESH") == "1"
    pwd = vdh.read_password()

    state = {"hosts": [], "disks": [], "resync": {}, "clusters": [], "up": 0, "last_success": 0, "duration": 0, "error": ""}
    history = {}
    lock = threading.Lock()
    cache = {}

    def loop():
        while True:
            t0 = time.time()
            try:
                hosts, disks, resync, cl_stats = collect(vc, user, pwd, cluster, fresh, cache)
                with lock:
                    state.update(hosts=hosts, disks=disks, resync=resync, clusters=cl_stats, up=1, error="",
                                 last_success=int(time.time()), duration=round(time.time() - t0, 2))
                    record_history(history, hosts, int(time.time()))
                print("[%s] OK: %d host, %d disk (%.1fs)" % (time.strftime("%H:%M:%S"), len(hosts), len(disks),
                                                             time.time() - t0), flush=True)
                if INFLUX["INFLUX_URL"]:
                    try:  # loi InfluxDB khong anh huong /metrics va dashboard web
                        with lock:
                            text = prometheus_text(state["hosts"], state["disks"], state["resync"], state,
                                                   state["clusters"])
                        n = push_influx(text, state["last_success"])
                        print("[%s] InfluxDB: da gui %d dong" % (time.strftime("%H:%M:%S"), n), flush=True)
                    except Exception as e:
                        detail = e.read().decode("utf-8", "replace")[:200] if hasattr(e, "read") else ""
                        print("[%s] InfluxDB LOI: %s %s" % (time.strftime("%H:%M:%S"), e, detail), flush=True)
            except vim.fault.InvalidLogin:
                print("Dang nhap that bai: sai user hoac mat khau. Dung exporter.", flush=True)
                os._exit(3)  # ma 3 = sai mat khau; systemd RestartPreventExitStatus=3 -> khong thu lai, tranh khoa tai khoan
            except Exception as e:  # giu du lieu cu, bao up=0
                with lock:
                    state.update(up=0, duration=round(time.time() - t0, 2), error=str(getattr(e, "msg", None) or e))
                print("[%s] LOI: %s" % (time.strftime("%H:%M:%S"), getattr(e, "msg", None) or e), flush=True)
            time.sleep(max(1, interval - (time.time() - t0)))

    class Handler(BaseHTTPRequestHandler):
        def send(self, body, ctype):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/metrics":
                with lock:
                    body = prometheus_text(state["hosts"], state["disks"], state["resync"], state, state["clusters"])
                self.send(body.encode("utf-8"), "text/plain; version=0.0.4; charset=utf-8")
            elif path == "/api/state":
                with lock:
                    body = json.dumps({
                        "version": VERSION,
                        "vcenter": vc, "cluster": cluster or "", "interval": interval, "slow_interval": SLOW_INTERVAL,
                        "now": int(time.time()), "up": state["up"], "last_success": state["last_success"],
                        "duration": state["duration"], "error": state["error"], "warn": WARN,
                        "resync": {c: {"objects": o, "bytes": b, "eta": e} for c, (o, b, e) in state["resync"].items()},
                        "hosts": host_views(state["hosts"], state["disks"]), "history": history,
                    }, ensure_ascii=False)
                self.send(body.encode("utf-8"), "application/json; charset=utf-8")
            elif path in ("/", "/index.html"):
                with open(DASHBOARD_FILE, "rb") as f:
                    self.send(f.read(), "text/html; charset=utf-8")
            else:
                self.send_error(404, "Dung / (dashboard), /api/state hoac /metrics")

        def log_message(self, *a):
            pass

    threading.Thread(target=loop, daemon=True).start()
    print("ESXi host exporter v%s: dashboard http://localhost:%d/  |  Prometheus http://0.0.0.0:%d/metrics "
          "(lay du lieu moi %ds)" % (VERSION, port, port, interval), flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Da dung.")
