# zabbix/

Template Zabbix **6.2** giam sat ESXi / vSAN qua **ESXi Host Exporter** (Zabbix lay thang `/metrics` cua exporter bang HTTP agent).

| File | Ghi chu |
|---|---|
| `esxi_vsan_command_center.yaml` | Template Zabbix 6.2 — ten: **ESXi & vSAN Command Center** (co san dashboard 3 trang) |

## Cai dat

1. Zabbix: **Data collection > Templates > Import** → chon `esxi_vsan_command_center.yaml`.
2. Tao 1 **host Zabbix cho moi instance exporter** (moi vCenter/pool 1 port), gan template **ESXi Host Exporter by HTTP**.
3. Sua macro tren host:
   - `{$ESXI.EXPORTER.URL}` = URL `/metrics` cua instance, vd `http://10.16.16.38:9811/metrics`
   - `{$ESXI.CLUSTER.MATCHES}` / `{$ESXI.HOST.MATCHES}` = regex loc cluster / host can giam sat (mac dinh `.*` = tat ca)
4. Zabbix tu lay `/metrics`, phat hien cluster / host / disk / nic / vmk (LLD) va tao item + trigger + graph.
5. Xem dashboard: **Monitoring > Dashboards** → **ESXi & vSAN Command Center** (3 trang: Hosts / vSAN / Network).

## Muc canh bao

Muc 2 = **High**, Muc 3 = **Warning**. Nguong chinh bang macro `{$ESXI.*}`:

| Chi so | Muc 2 (High) | Muc 3 (Warning) | Macro |
|---|---|---|---|
| Host mat ket noi vCenter / service | connected = 0 | — | |
| CPU | > `{$ESXI.CPU.HIGH}` (60) | > `{$ESXI.CPU.WARN}` (40) | `{$ESXI.CPU.HIGH}` `{$ESXI.CPU.WARN}` |
| RAM | > `{$ESXI.RAM.HIGH}` (90) | > `{$ESXI.RAM.WARN}` (80) | `{$ESXI.RAM.HIGH}` `{$ESXI.RAM.WARN}` |
| vSAN disk health | disk Red | disk Yellow | |
| Disk group | Unhealthy | — | |
| vSAN network latency | > `{$ESXI.NETLAT.HIGH}` (1ms) | > `{$ESXI.NETLAT.WARN}` (0.5ms) | `{$ESXI.NETLAT.HIGH}` `{$ESXI.NETLAT.WARN}` |
| Disk write latency | > `{$ESXI.LAT.HIGH}` (30ms) | > `{$ESXI.LAT.WARN}` (15ms) | `{$ESXI.LAT.HIGH}` `{$ESXI.LAT.WARN}` |
| vSAN congestion | > `{$ESXI.CONG.HIGH}` (60) | — | `{$ESXI.CONG.HIGH}` |
| vmk packet drop | — | > `{$ESXI.VMKDROP.WARN}` (0.1%) | `{$ESXI.VMKDROP.WARN}` |
| vSAN resync | dang resync | — | |
| vmnic down | mat link | — | |
| Host maintenance | — | maintenance = 1 | |
| Exporter mat du lieu | — | > `{$ESXI.STALE}` (900s) | `{$ESXI.STALE}` |

Doi nguong: sua macro tren host/template, khong can sua trigger.

> Luu y: 2 item **Hardware Health** va **Healthy vSAN Disks (%)** can metric `esxi_host_hardware_health` / `esxi_vsan_host_disk_health_percent` — ban exporter hien tai chua xuat, nen 2 item do se trong (khong loi). Cac phan con lai chay binh thuong.
