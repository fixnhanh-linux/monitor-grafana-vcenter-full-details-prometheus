#!/usr/bin/env python3
"""Generate the Zabbix 6.0 template (esxi_host_exporter_zbx60.yaml) for the ESXi Host Exporter.

Zabbix pulls the exporter /metrics directly (HTTP agent) and then:
  - Host LLD from esxi_host_status  -> per-host items + triggers.
  - Cluster LLD from esxi_vsan_resync_bytes -> per-cluster resync trigger.
A template dashboard (Problems + graph prototypes) is included.
Severity: Level 2 = High, Level 3 = Warning. Thresholds are macros ({$ESXI_*}).

Run:  python make_template.py   ->  writes esxi_host_exporter_zbx60.yaml next to this file.
"""
import datetime
import os
import uuid

import yaml

TPL = "ESXi Host Exporter"
NS = uuid.UUID("1b4e28ba-2fa1-11d2-883f-0016d3cca427")  # fixed namespace -> stable uuids


def U(seed):
    return uuid.uuid5(NS, "esxi-zbx::" + seed).hex


def ref(key):
    return "/%s/%s" % (TPL, key)


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
            "parameters": [metric + '{cluster="{#CLUSTER}",host="{#HOST}"}', "value", ""],
            "error_handler": "DISCARD_VALUE",  # metric may be absent on some hosts
        }],
        "tags": [{"tag": "cluster", "value": "{#CLUSTER}"}, {"tag": "host", "value": "{#HOST}"}],
    }
    if units:
        it["units"] = units
    return it


def trig(seed, expr, name, priority):
    return {"uuid": U("trig:" + seed), "expression": expr, "name": name, "priority": priority}


# ---------------- master item: pull /metrics ----------------
master = {
    "uuid": U("item:master"),
    "name": "ESXi Exporter: Raw Metrics (/metrics)",
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

# ---------------- per-host item prototypes ----------------
H = "esxi.host.%s[{#CLUSTER},{#HOST}]"
items = [
    host_item("status", "Host [{#HOST}] {#CLUSTER}: Status (0=OK, 1=Warn, 2=Error)", "esxi_host_status"),
    host_item("connected", "Host [{#HOST}] {#CLUSTER}: vCenter Connection (1/0)", "esxi_host_connected"),
    host_item("maintenance", "Host [{#HOST}] {#CLUSTER}: Maintenance Mode (1/0)", "esxi_host_maintenance"),
    host_item("cpu", "Host [{#HOST}] {#CLUSTER}: CPU Usage (%)", "esxi_host_cpu_usage_percent", "%"),
    host_item("ram", "Host [{#HOST}] {#CLUSTER}: RAM Usage (%)", "esxi_host_mem_usage_percent", "%"),
    host_item("disk_health", "Host [{#HOST}] {#CLUSTER}: vSAN Disk Health (0=Green, 1=Yellow, 2=Red, 3=Unknown)",
              "esxi_vsan_host_disk_health"),
    host_item("congestion", "Host [{#HOST}] {#CLUSTER}: vSAN Congestion", "esxi_vsan_host_congestion"),
    host_item("net_latency", "Host [{#HOST}] {#CLUSTER}: vSAN Network Latency (ms)", "esxi_vsan_network_latency_ms", "ms"),
]

# ---------------- per-host trigger prototypes (no level suffix; severity = Zabbix priority) ----------------
host_triggers = [
    trig("status-err", "last(%s)=2" % ref(H % "status"),
         "Host [{#HOST}] {#CLUSTER}: Error (Host Down / Service / NIC / Hardware)", "HIGH"),
    trig("status-warn", "last(%s)=1" % ref(H % "status"),
         "Host [{#HOST}] {#CLUSTER}: Warning", "WARNING"),
    trig("disconnected", "last(%s)=0" % ref(H % "connected"),
         "Host [{#HOST}] {#CLUSTER}: Disconnected From vCenter", "HIGH"),
    trig("cpu-high", "min(%s,5m)>{$ESXI_CPU_HIGH}" % ref(H % "cpu"),
         "Host [{#HOST}] {#CLUSTER}: CPU Above {$ESXI_CPU_HIGH}%", "HIGH"),
    trig("cpu-warn", "min(%s,5m)>{$ESXI_CPU_WARN} and min(%s,5m)<={$ESXI_CPU_HIGH}" % (ref(H % "cpu"), ref(H % "cpu")),
         "Host [{#HOST}] {#CLUSTER}: CPU Above {$ESXI_CPU_WARN}%", "WARNING"),
    trig("ram-high", "min(%s,5m)>{$ESXI_RAM_HIGH}" % ref(H % "ram"),
         "Host [{#HOST}] {#CLUSTER}: RAM Above {$ESXI_RAM_HIGH}%", "HIGH"),
    trig("ram-warn", "min(%s,5m)>{$ESXI_RAM_WARN} and min(%s,5m)<={$ESXI_RAM_HIGH}" % (ref(H % "ram"), ref(H % "ram")),
         "Host [{#HOST}] {#CLUSTER}: RAM Above {$ESXI_RAM_WARN}%", "WARNING"),
    trig("disk-red", "last(%s)=2" % ref(H % "disk_health"),
         "Host [{#HOST}] {#CLUSTER}: vSAN Disk Unhealthy (Red)", "HIGH"),
    trig("disk-yellow", "last(%s)=1" % ref(H % "disk_health"),
         "Host [{#HOST}] {#CLUSTER}: vSAN Disk Unhealthy (Yellow)", "WARNING"),
    trig("netlat-high", "last(%s)>{$ESXI_NETLAT_HIGH}" % ref(H % "net_latency"),
         "Host [{#HOST}] {#CLUSTER}: vSAN Network Latency Above {$ESXI_NETLAT_HIGH}ms", "HIGH"),
    trig("netlat-warn", "last(%s)>{$ESXI_NETLAT_WARN} and last(%s)<={$ESXI_NETLAT_HIGH}" % (ref(H % "net_latency"), ref(H % "net_latency")),
         "Host [{#HOST}] {#CLUSTER}: vSAN Network Latency Above {$ESXI_NETLAT_WARN}ms", "WARNING"),
    trig("congestion", "min(%s,5m)>{$ESXI_CONGESTION}" % ref(H % "congestion"),
         "Host [{#HOST}] {#CLUSTER}: vSAN Congestion Above {$ESXI_CONGESTION}", "HIGH"),
    trig("maintenance", "last(%s)=1" % ref(H % "maintenance"),
         "Host [{#HOST}] {#CLUSTER}: In Maintenance Mode", "WARNING"),
]

host_lld = {
    "uuid": U("lld:host"),
    "name": "ESXi Host Discovery",
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

# ---------------- cluster LLD: resync ----------------
C = "esxi.vsan.resync_bytes[{#CLUSTER}]"
cluster_lld = {
    "uuid": U("lld:cluster"),
    "name": "ESXi Cluster Discovery (Resync)",
    "type": "DEPENDENT",
    "key": "esxi.cluster.discovery",
    "delay": "0",
    "master_item": {"key": "esxi.metrics.raw"},
    "preprocessing": [{"type": "PROMETHEUS_TO_JSON", "parameters": ["esxi_vsan_resync_bytes"]}],
    "lld_macro_paths": [{"lld_macro": "{#CLUSTER}", "path": "$.labels['cluster']"}],
    "item_prototypes": [{
        "uuid": U("item:resync"),
        "name": "Cluster [{#CLUSTER}]: vSAN Resync Remaining (bytes)",
        "type": "DEPENDENT",
        "key": C,
        "value_type": "FLOAT",
        "units": "B",
        "master_item": {"key": "esxi.metrics.raw"},
        "preprocessing": [{
            "type": "PROMETHEUS_PATTERN",
            "parameters": ['esxi_vsan_resync_bytes{cluster="{#CLUSTER}"}', "value", ""],
            "error_handler": "DISCARD_VALUE",
        }],
        "tags": [{"tag": "cluster", "value": "{#CLUSTER}"}],
    }],
    "trigger_prototypes": [
        trig("resync", "last(%s)>{$ESXI_RESYNC_MIN}" % ref(C),
             "Cluster [{#CLUSTER}]: vSAN Resync In Progress", "HIGH"),
    ],
}

# ---------------- template dashboard ----------------
def gp(name, key, x, y, w=12, h=6, columns=2):
    return {
        "type": "graphprototype",
        "name": name,
        "x": str(x), "y": str(y), "width": str(w), "height": str(h),
        "fields": [
            {"type": "INTEGER", "name": "source_type", "value": "1"},  # simple graph prototype
            {"type": "ITEM_PROTOTYPE", "name": "itemid", "value": {"host": TPL, "key": key}},
            {"type": "INTEGER", "name": "columns", "value": str(columns)},
        ],
    }

dashboard = {
    "uuid": U("dashboard"),
    "name": "ESXi Host Overview",
    "pages": [{
        "name": "Overview",
        "widgets": [
            gp("Host Status", H % "status", 0, 0),
            gp("CPU Usage (%)", H % "cpu", 12, 0),
            gp("RAM Usage (%)", H % "ram", 0, 6),
            gp("vSAN Disk Health", H % "disk_health", 12, 6),
            gp("vSAN Network Latency (ms)", H % "net_latency", 0, 12),
            gp("vSAN Congestion", H % "congestion", 12, 12),
        ],
    }],
}

macros = [
    {"macro": "{$ESXI_EXPORTER_HOST}", "value": "127.0.0.1", "description": "IP of the exporter host"},
    {"macro": "{$ESXI_EXPORTER_PORT}", "value": "9811", "description": "Exporter instance port"},
    {"macro": "{$ESXI_CPU_HIGH}", "value": "60", "description": "CPU % -> Level 2 (High)"},
    {"macro": "{$ESXI_CPU_WARN}", "value": "40", "description": "CPU % -> Level 3 (Warning)"},
    {"macro": "{$ESXI_RAM_HIGH}", "value": "90", "description": "RAM % -> Level 2 (High)"},
    {"macro": "{$ESXI_RAM_WARN}", "value": "80", "description": "RAM % -> Level 3 (Warning)"},
    {"macro": "{$ESXI_NETLAT_HIGH}", "value": "1", "description": "vSAN network latency ms -> Level 2 (High)"},
    {"macro": "{$ESXI_NETLAT_WARN}", "value": "0.5", "description": "vSAN network latency ms -> Level 3 (Warning)"},
    {"macro": "{$ESXI_CONGESTION}", "value": "60", "description": "vSAN congestion -> Level 2 (High)"},
    {"macro": "{$ESXI_RESYNC_MIN}", "value": "0", "description": "Resync bytes above this -> Level 2 (High)"},
]

template = {
    "uuid": U("template"),
    "template": TPL,
    "name": TPL,
    "description": ("Monitor ESXi / vSAN via the ESXi Host Exporter (/metrics). "
                    "Host and cluster LLD. Level 2 = High, Level 3 = Warning; thresholds are {$ESXI_*} macros."),
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
    style = "'" if any(c in data for c in "{}=>#:") else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str)

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "esxi_host_exporter_zbx60.yaml")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(doc, f, Dumper=_Dumper, default_flow_style=False, sort_keys=False, allow_unicode=True, width=4096)
    print("Wrote", out)
