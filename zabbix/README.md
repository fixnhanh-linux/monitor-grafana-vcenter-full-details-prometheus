# zabbix/

Template Zabbix 6.0 giam sat ESXi / vSAN qua **ESXi Host Exporter** (lay thang `/metrics`).

| File | Ghi chu |
|---|---|
| `esxi_host_exporter_zbx60.yaml` | Template import vao Zabbix 6.0 |
| `make_template.py` | Script sinh ra file YAML tren (chay `python make_template.py`) |

## Cai dat

1. Zabbix: **Data collection > Templates > Import** → chon `esxi_host_exporter_zbx60.yaml`.
2. Tao 1 **host Zabbix cho moi instance exporter** (moi vCenter/pool 1 port), gan template **ESXi Host Exporter**.
3. Sua macro tren host:
   - `{$ESXI_EXPORTER_HOST}` = IP may chay exporter (vd `10.16.16.38`)
   - `{$ESXI_EXPORTER_PORT}` = port instance (vd `9811`, `9812`...)
4. Zabbix se tu lay `/metrics`, phat hien host + cluster (LLD) va tao item/trigger.

## Muc canh bao (bam bang muc 4)

Muc 2 = **High**, Muc 3 = **Warning**. Nguong chinh bang macro:

| Chi so | Muc 2 (High) | Muc 3 (Warning) | Macro |
|---|---|---|---|
| Host status / service / NIC / phan cung | status = ERROR | status = WARN | (tu exporter) |
| Mat ket noi vCenter | connected = 0 | — | |
| CPU | > `{$ESXI_CPU_HIGH}` (60) | > `{$ESXI_CPU_WARN}` (40) | `{$ESXI_CPU_HIGH}` `{$ESXI_CPU_WARN}` |
| RAM | > `{$ESXI_RAM_HIGH}` (90) | > `{$ESXI_RAM_WARN}` (80) | `{$ESXI_RAM_HIGH}` `{$ESXI_RAM_WARN}` |
| Disk vSAN health | red | yellow | (tu exporter) |
| vSAN network latency | > `{$ESXI_NETLAT_HIGH}` (1ms) | > `{$ESXI_NETLAT_WARN}` (0.5ms) | `{$ESXI_NETLAT_HIGH}` `{$ESXI_NETLAT_WARN}` |
| vSAN congestion | > `{$ESXI_CONGESTION}` (60) | — | `{$ESXI_CONGESTION}` |
| vSAN resync | resync > `{$ESXI_RESYNC_MIN}` (0) | — | `{$ESXI_RESYNC_MIN}` |
| Host maintenance | — | maintenance = 1 | (tu exporter) |

Doi nguong: sua macro tren host/template, khong can sua trigger.
