#!/usr/bin/env python3
"""Sinh template Zabbix 6.0 (esxi_host_exporter_zbx60.yaml) cho ESXi Host Exporter.

Zabbix lay thang /metrics cua exporter (HTTP agent) roi:
  - LLD "Host" tu metric esxi_host_status  -> item + trigger tung host.
  - LLD "Cluster" tu metric esxi_vsan_resync_bytes -> trigger resync tung cluster.
Muc canh bao bam theo bang: Muc 2 = High, Muc 3 = Warning. Nguong la macro ({$ESXI_*}).

Chay:  python make_template.py   ->  ghi esxi_host_exporter_zbx60.yaml canh file nay.
"""
import datetime
import os
import uuid

import yaml

TPL = "ESXi Host Exporter"
NS = uuid.UUID("1b4e28ba-2fa1-11d2-883f-0016d3cca427")  # namespace co dinh -> uuid on dinh


def U(seed):
    return uuid.uuid5(NS, "esxi-zbx::" + seed).hex


def ref(key):  # tham chieu item trong bieu thuc trigger
    return "/%s/%s" % (TPL, key)


def pattern(metric, by_host=True):
    sel = '{cluster="{#CLUSTER}",host="{#HOST}"}' if by_host else '{cluster="{#CLUSTER}"}'
    return [metric + sel, "value", ""]


def host_item(key, name, metric, units=None):
    it = {
        "uuid": U("item:" + key),
        "name": name,
        "type": "DEPENDENT",
        "key": "esxi.host.%s[{#CLUSTER},{#HOST}]" % key,
        "value_type": "FLOAT",
        "master_item": {"key": "esxi.metrics.raw"},
        "preprocessing": [{
            "type": "PROMETHEUS_PATTERN",
            "parameters": pattern(metric),
            # metric co the vang o 1 so host (vd net latency) -> bo qua, khong bao loi
            "error_handler": "DISCARD_VALUE",
        }],
        "tags": [{"tag": "cluster", "value": "{#CLUSTER}"}, {"tag": "host", "value": "{#HOST}"}],
    }
    if units:
        it["units"] = units
    return it


def trig(seed, expr, name, priority, description=""):
    t = {
        "uuid": U("trig:" + seed),
        "expression": expr,
        "name": name,
        "priority": priority,
    }
    if description:
        t["description"] = description
    return t


# ---------------- master item: lay /metrics ----------------
master = {
    "uuid": U("item:master"),
    "name": "ESXi exporter: raw metrics (/metrics)",
    "type": "HTTP_AGENT",
    "key": "esxi.metrics.raw",
    "delay": "1m",
    "history": "0",
    "trends": "0",
    "value_type": "TEXT",
    "url": "http://{$ESXI_EXPORTER_HOST}:{$ESXI_EXPORTER_PORT}/metrics",
    "timeout": "30s",
    "tags": [{"tag": "component", "value": "raw"}],
}

# ---------------- item prototypes (theo host) ----------------
H = "esxi.host.%s[{#CLUSTER},{#HOST}]"
items = [
    host_item("status", "Host [{#HOST}] {#CLUSTER}: Trang thai (0=OK,1=WARN,2=ERROR)", "esxi_host_status"),
    host_item("connected", "Host [{#HOST}] {#CLUSTER}: Ket noi vCenter (1/0)", "esxi_host_connected"),
    host_item("maintenance", "Host [{#HOST}] {#CLUSTER}: Maintenance mode (1/0)", "esxi_host_maintenance"),
    host_item("cpu", "Host [{#HOST}] {#CLUSTER}: CPU dung (%)", "esxi_host_cpu_usage_percent", "%"),
    host_item("ram", "Host [{#HOST}] {#CLUSTER}: RAM dung (%)", "esxi_host_mem_usage_percent", "%"),
    host_item("disk_health", "Host [{#HOST}] {#CLUSTER}: Disk vSAN health (0=green,1=yellow,2=red,3=unknown)",
              "esxi_vsan_host_disk_health"),
    host_item("congestion", "Host [{#HOST}] {#CLUSTER}: vSAN congestion", "esxi_vsan_host_congestion"),
    host_item("net_latency", "Host [{#HOST}] {#CLUSTER}: vSAN network latency (ms)", "esxi_vsan_network_latency_ms", "ms"),
]

# ---------------- trigger prototypes (theo host) ----------------
host_triggers = [
    # Host Status / ESXi service: down / service / NIC / phan cung -> Muc 2 (High)
    trig("status-err", "last(%s)=2" % ref(H % "status"),
         "Host [{#HOST}] {#CLUSTER}: Loi (ERROR) - host down / service / NIC / phan cung [Muc 2]", "HIGH"),
    trig("status-warn", "last(%s)=1" % ref(H % "status"),
         "Host [{#HOST}] {#CLUSTER}: Canh bao (WARN) [Muc 3]", "WARNING"),
    # Mat ket noi vCenter -> Muc 2
    trig("disconnected", "last(%s)=0" % ref(H % "connected"),
         "Host [{#HOST}] {#CLUSTER}: Mat ket noi vCenter [Muc 2]", "HIGH"),
    # CPU: >60% Muc 2, 40-60% Muc 3 (min 5 phut tranh nhieu)
    trig("cpu-high", "min(%s,5m)>{$ESXI_CPU_HIGH}" % ref(H % "cpu"),
         "Host [{#HOST}] {#CLUSTER}: CPU > {$ESXI_CPU_HIGH}% [Muc 2]", "HIGH"),
    trig("cpu-warn", "min(%s,5m)>{$ESXI_CPU_WARN} and min(%s,5m)<={$ESXI_CPU_HIGH}" % (ref(H % "cpu"), ref(H % "cpu")),
         "Host [{#HOST}] {#CLUSTER}: CPU > {$ESXI_CPU_WARN}% [Muc 3]", "WARNING"),
    # RAM: >90% Muc 2, 80-90% Muc 3
    trig("ram-high", "min(%s,5m)>{$ESXI_RAM_HIGH}" % ref(H % "ram"),
         "Host [{#HOST}] {#CLUSTER}: RAM > {$ESXI_RAM_HIGH}% [Muc 2]", "HIGH"),
    trig("ram-warn", "min(%s,5m)>{$ESXI_RAM_WARN} and min(%s,5m)<={$ESXI_RAM_HIGH}" % (ref(H % "ram"), ref(H % "ram")),
         "Host [{#HOST}] {#CLUSTER}: RAM > {$ESXI_RAM_WARN}% [Muc 3]", "WARNING"),
    # Disk Group / Disk Health: red -> Muc 2, yellow -> Muc 3
    trig("disk-red", "last(%s)>=2 and last(%s)<=2" % (ref(H % "disk_health"), ref(H % "disk_health")),
         "Host [{#HOST}] {#CLUSTER}: Disk vSAN Unhealthy (red) [Muc 2]", "HIGH"),
    trig("disk-yellow", "last(%s)=1" % ref(H % "disk_health"),
         "Host [{#HOST}] {#CLUSTER}: Disk vSAN Unhealthy (yellow) [Muc 3]", "WARNING"),
    # vSAN network latency: >1ms Muc 2, 0.5-1ms Muc 3
    trig("netlat-high", "last(%s)>{$ESXI_NETLAT_HIGH}" % ref(H % "net_latency"),
         "Host [{#HOST}] {#CLUSTER}: vSAN network latency > {$ESXI_NETLAT_HIGH}ms [Muc 2]", "HIGH"),
    trig("netlat-warn", "last(%s)>{$ESXI_NETLAT_WARN} and last(%s)<={$ESXI_NETLAT_HIGH}" % (ref(H % "net_latency"), ref(H % "net_latency")),
         "Host [{#HOST}] {#CLUSTER}: vSAN network latency > {$ESXI_NETLAT_WARN}ms [Muc 3]", "WARNING"),
    # vSAN congestion -> Muc 2
    trig("congestion", "min(%s,5m)>{$ESXI_CONGESTION}" % ref(H % "congestion"),
         "Host [{#HOST}] {#CLUSTER}: vSAN congestion > {$ESXI_CONGESTION} [Muc 2]", "HIGH"),
    # Host maintenance -> Muc 3
    trig("maintenance", "last(%s)=1" % ref(H % "maintenance"),
         "Host [{#HOST}] {#CLUSTER}: dang o che do bao tri [Muc 3]", "WARNING"),
]

host_lld = {
    "uuid": U("lld:host"),
    "name": "ESXi host discovery",
    "type": "DEPENDENT",
    "key": "esxi.host.discovery",
    "delay": "0",
    "master_item": {"key": "esxi.metrics.raw"},
    "preprocessing": [{"type": "PROMETHEUS_TO_JSON", "parameters": ["esxi_host_status"]}],
    "lld_macro_paths": [
        {"lld_macro": "{#HOST}", "path": "$.labels['host']"},
        {"lld_macro": "{#CLUSTER}", "path": "$.labels['cluster']"},
    ],
    "item_prototypes": items,
    "trigger_prototypes": host_triggers,
}

# ---------------- LLD cluster: resync ----------------
C = "esxi.vsan.resync_bytes[{#CLUSTER}]"
cluster_lld = {
    "uuid": U("lld:cluster"),
    "name": "ESXi cluster discovery (resync)",
    "type": "DEPENDENT",
    "key": "esxi.cluster.discovery",
    "delay": "0",
    "master_item": {"key": "esxi.metrics.raw"},
    "preprocessing": [{"type": "PROMETHEUS_TO_JSON", "parameters": ["esxi_vsan_resync_bytes"]}],
    "lld_macro_paths": [{"lld_macro": "{#CLUSTER}", "path": "$.labels['cluster']"}],
    "item_prototypes": [{
        "uuid": U("item:resync"),
        "name": "Cluster [{#CLUSTER}]: vSAN resync con lai (bytes)",
        "type": "DEPENDENT",
        "key": C,
        "value_type": "FLOAT",
        "units": "B",
        "master_item": {"key": "esxi.metrics.raw"},
        "preprocessing": [{
            "type": "PROMETHEUS_PATTERN",
            "parameters": ["esxi_vsan_resync_bytes{cluster=\"{#CLUSTER}\"}", "value", ""],
            "error_handler": "DISCARD_VALUE",
        }],
        "tags": [{"tag": "cluster", "value": "{#CLUSTER}"}],
    }],
    "trigger_prototypes": [
        trig("resync", "last(%s)>{$ESXI_RESYNC_MIN}" % ref(C),
             "Cluster [{#CLUSTER}]: vSAN dang resync [Muc 2]", "HIGH"),
    ],
}

macros = [
    {"macro": "{$ESXI_EXPORTER_HOST}", "value": "127.0.0.1", "description": "IP may chay exporter"},
    {"macro": "{$ESXI_EXPORTER_PORT}", "value": "9811", "description": "Port instance exporter"},
    {"macro": "{$ESXI_CPU_HIGH}", "value": "60", "description": "CPU % -> Muc 2 (High)"},
    {"macro": "{$ESXI_CPU_WARN}", "value": "40", "description": "CPU % -> Muc 3 (Warning)"},
    {"macro": "{$ESXI_RAM_HIGH}", "value": "90", "description": "RAM % -> Muc 2 (High)"},
    {"macro": "{$ESXI_RAM_WARN}", "value": "80", "description": "RAM % -> Muc 3 (Warning)"},
    {"macro": "{$ESXI_NETLAT_HIGH}", "value": "1", "description": "vSAN network latency ms -> Muc 2"},
    {"macro": "{$ESXI_NETLAT_WARN}", "value": "0.5", "description": "vSAN network latency ms -> Muc 3"},
    {"macro": "{$ESXI_CONGESTION}", "value": "60", "description": "vSAN congestion -> Muc 2"},
    {"macro": "{$ESXI_RESYNC_MIN}", "value": "0", "description": "Resync bytes vuot nguong -> Muc 2"},
]

template = {
    "uuid": U("template"),
    "template": TPL,
    "name": TPL,
    "description": ("Giam sat ESXi / vSAN qua ESXi Host Exporter (/metrics). "
                    "LLD theo host + cluster. Muc 2 = High, Muc 3 = Warning; nguong la macro {$ESXI_*}."),
    "groups": [{"name": "Templates/Applications"}],
    "items": [master],
    "discovery_rules": [host_lld, cluster_lld],
    "macros": macros,
}

doc = {
    "zabbix_export": {
        "version": "6.0",
        "date": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "groups": [{"uuid": U("group"), "name": "Templates/Applications"}],
        "templates": [template],
    }
}


class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper, data):
    # ep cac chuoi co ky tu dac biet ({, }, =, >) ra dang nhay don cho an toan
    style = "'" if any(c in data for c in "{}=>#:") else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str)

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "esxi_host_exporter_zbx60.yaml")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(doc, f, Dumper=_Dumper, default_flow_style=False, sort_keys=False, allow_unicode=True, width=4096)
    print("Da ghi", out)
