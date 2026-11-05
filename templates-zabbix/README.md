# templates-zabbix/

Template Zabbix **6.2** giam sat ESXi / vSAN qua **ESXi Host Exporter** (Zabbix lay thang `/metrics` cua exporter bang HTTP agent).

| File | Ghi chu |
|---|---|
| `esxi_vsan_command_center.yaml` | Template Zabbix 6.2 — ten: **ESXi & vSAN Command Center** (co san dashboard 3 trang) |
| `add_hosts.py` | Script tao host Zabbix qua API: 1 instance >= 2 cluster thi tach ra, host da co thi bo qua (chay bang `esxi-menu` muc 18) |

## Cai dat

1. Zabbix: **Data collection > Templates > Import** → chon `esxi_vsan_command_center.yaml`.
2. Tao **host Zabbix cho moi instance exporter** (moi vCenter/pool 1 port), gan template **ESXi Host Exporter by HTTP**.
   - **Tu dong:** tren server exporter chay `sudo esxi-menu` → **18** (hoac `python add_hosts.py <url-zabbix>` voi `ZABBIX_TOKEN`): doc cac instance da cai → tao host (host group + template + macro URL), HTTP agent nen khong can interface.
     - **Tach cluster:** instance nao giam sat **>= 2 cluster (POOL)** se duoc tach thanh nhieu host, moi cluster 1 host, tu dat macro `{$ESXI.CLUSTER.MATCHES}=^<ten-cluster>$`. Instance 1 cluster → 1 host (ten theo instance).
     - **Host da co:** mac dinh **bo qua** (khong dong vao). Them `--update` neu muon cap nhat host da co; `--no-split` neu khong muon tach cluster.
   - **Thu cong:** them host tay roi gan template.
3. Sua macro tren host:
   - `{$ESXI.EXPORTER.URL}` = URL `/metrics` cua instance, vd `http://10.16.16.38:9811/metrics`
   - `{$ESXI.CLUSTER.MATCHES}` / `{$ESXI.HOST.MATCHES}` = regex loc cluster / host can giam sat (mac dinh `.*` = tat ca)
4. Zabbix tu lay `/metrics`, phat hien cluster / host / disk / nic / vmk (LLD) va tao item + trigger + graph.
5. Xem dashboard: **Monitoring > Dashboards** → **ESXi & vSAN Command Center** (3 trang: Hosts / vSAN / Network).

## Tag (loc / gom su co)

Moi item + trigger deu co tag day du de loc o **Monitoring > Problems** va **Latest data**:

- `component` = loai thanh phan (`cpu`, `memory`, `vsan`, `vsan-disk`, `network`, `host`, `exporter`)
- `cluster` = ten cluster (POOL), `host` = ten host ESXi
- Tai nguyen cu the (khi co): `nic`, `disk`, `diskgroup`, `vmk`, `direction`
- `level` = `2` (Muc 2/High) hoac `3` (Muc 3/Warning)

Vd loc nhanh: `cluster = POOL18` + `level = 2` de xem su co nghiem trong cua 1 pool; hoac `component = vsan` cho rieng van de vSAN.

## Muc canh bao

Muc 1 = **Disaster** (cao nhat, mat dich vu), Muc 2 = **High**, Muc 3 = **Warning**.

**Muc 1 (Disaster):** **vSAN cluster partition** — cluster bi chia > 1 partition, hoac host co Partition khac / thay doi (mat quorum, object inaccessible, anh huong dich vu).

Cac nguong Muc 2 / Muc 3 chinh bang macro `{$ESXI.*}`:

| Chi so | Muc 2 (High) | Muc 3 (Warning) | Macro |
|---|---|---|---|
| Host mat ket noi vCenter / service | connected = 0 | — | |
| CPU | > `{$ESXI.CPU.HIGH}` (60) | > `{$ESXI.CPU.WARN}` (40) | `{$ESXI.CPU.HIGH}` `{$ESXI.CPU.WARN}` |
| RAM | > `{$ESXI.RAM.HIGH}` (90) | > `{$ESXI.RAM.WARN}` (80) | `{$ESXI.RAM.HIGH}` `{$ESXI.RAM.WARN}` |
| vSAN disk health | disk Red | disk Yellow | |
| Disk group | Unhealthy | — | |
| vSAN network latency (1 canh bao / pool, gia tri hien tai) | > `{$ESXI.NETLAT.HIGH}` (5ms) | > `{$ESXI.NETLAT.WARN}` (4ms) | `{$ESXI.NETLAT.HIGH}` `{$ESXI.NETLAT.WARN}` |
| Disk write latency | > `{$ESXI.LAT.HIGH}` (30ms) | > `{$ESXI.LAT.WARN}` (15ms) | `{$ESXI.LAT.HIGH}` `{$ESXI.LAT.WARN}` |
| vSAN congestion | > `{$ESXI.CONG.HIGH}` (60) | — | `{$ESXI.CONG.HIGH}` |
| vmk packet drop | — | > `{$ESXI.VMKDROP.WARN}` (0.1%) | `{$ESXI.VMKDROP.WARN}` |
| vSAN resync | dang resync | — | |
| vmnic down | mat link | — | |
| Host maintenance | — | maintenance = 1 | |
| Exporter mat du lieu | — | > `{$ESXI.STALE}` (900s) | `{$ESXI.STALE}` |

Doi nguong: sua macro tren host/template, khong can sua trigger.

**Doi chieu vSAN cluster partition voi vCenter:** Cluster → **Monitor** → **vSAN** → **Skyline Health** → **vSAN cluster partition** (bang Host / Partition / Host UUID). Binh thuong moi host = 1; host co Partition khac la host bi tach (kiem tra vmk vSAN / uplink / switch).

> Luu y: 2 item **Hardware Health** va **Healthy vSAN Disks (%)** can metric `esxi_host_hardware_health` / `esxi_vsan_host_disk_health_percent` — ban exporter hien tai chua xuat, nen 2 item do se trong (khong loi). Cac phan con lai chay binh thuong.
