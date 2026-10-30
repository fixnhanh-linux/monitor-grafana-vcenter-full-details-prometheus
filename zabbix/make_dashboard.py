#!/usr/bin/env python3
"""Generate a standalone Zabbix 6.0 dashboard (esxi_dashboard_zbx60.yaml).

Import under Monitoring > Dashboards (NOT inside the template - template dashboards
reject graph/problem widgets). Uses item-name patterns so it matches any host that
got the ESXi Host Exporter template items. Import the template first.
"""
import datetime
import os
import uuid

import yaml

NS = uuid.UUID("1b4e28ba-2fa1-11d2-883f-0016d3cca427")


def U(seed):
    h = uuid.uuid5(NS, "esxi-dash::" + seed).hex
    return h[:12] + "4" + h[13:16] + "89ab"[int(h[16], 16) % 4] + h[17:]


def svg(name, item_pattern, x, y, w=12, h=6, color="1A7C83"):
    """SVG graph widget, 1 dataset theo pattern ten item (moi host 1 duong)."""
    return {
        "type": "svggraph",
        "name": name,
        "x": str(x), "y": str(y), "width": str(w), "height": str(h),
        "fields": [
            {"type": "STRING", "name": "ds.0.hosts.0", "value": "*"},
            {"type": "STRING", "name": "ds.0.items.0", "value": item_pattern},
            {"type": "STRING", "name": "ds.0.color", "value": color},
            {"type": "INTEGER", "name": "ds.0.width", "value": "2"},
            {"type": "INTEGER", "name": "ds.0.transparency", "value": "2"},
            {"type": "INTEGER", "name": "ds.0.fill", "value": "2"},
            {"type": "INTEGER", "name": "legend", "value": "1"},
            {"type": "INTEGER", "name": "legend_lines", "value": "4"},
        ],
    }


problems = {
    "type": "problems",
    "name": "ESXi Problems",
    "x": "0", "y": "0", "width": "24", "height": "6",
    "fields": [
        {"type": "INTEGER", "name": "show_tags", "value": "3"},
        {"type": "INTEGER", "name": "sort_triggers", "value": "16"},
    ],
}

widgets = [
    problems,
    svg("CPU Usage (%) - all hosts", "*: CPU Usage (%)", 0, 6, color="1A7C83"),
    svg("RAM Usage (%) - all hosts", "*: RAM Usage (%)", 12, 6, color="E57373"),
    svg("vSAN Network Latency (ms)", "*: vSAN Network Latency (ms)", 0, 12, color="F2A900"),
    svg("vSAN Congestion", "*: vSAN Congestion", 12, 12, color="8E44AD"),
    svg("vSAN Disk Health (0=green..3=unknown)", "*: vSAN Disk Health*", 0, 18, color="27AE60"),
    svg("Host Status (0=OK,1=Warn,2=Error)", "*: Status (*", 12, 18, color="C0392B"),
]

doc = {
    "zabbix_export": {
        "version": "6.0",
        "date": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dashboards": [{
            "uuid": U("dashboard"),
            "name": "ESXi / vSAN Monitoring",
            "display_period": "30",
            "auto_start": "1",
            "pages": [{"name": "Overview", "widgets": widgets}],
        }],
    }
}


class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper, data):
    style = "'" if any(c in data for c in "{}=>#:*") else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str)

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "esxi_dashboard_zbx60.yaml")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(doc, f, Dumper=_Dumper, default_flow_style=False, sort_keys=False, allow_unicode=True, width=4096)
    print("Wrote", out)
