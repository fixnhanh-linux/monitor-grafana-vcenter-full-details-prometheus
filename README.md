# MONITOR RESOURCE HOST ESXi + vSAN Disk Health → Prometheus → Grafana

Làm theo yêu cầu trong `MONITOR RESOURCE HOST ESXi.docx`.

## Cài từ GitHub (git clone)

Repo: **https://github.com/fixnhanh-linux/monitor-grafana-vcenter-full-details-prometheus**

```bash
cd /root
git clone https://github.com/fixnhanh-linux/monitor-grafana-vcenter-full-details-prometheus.git
cd monitor-grafana-vcenter-full-details-prometheus
sudo bash deploy/install.sh
```

- Cần internet trên server: `install.sh` tự tải thư viện `pyvmomi` bằng pip
  (thiếu pip: `apt install python3-pip` hoặc `dnf install python3-pip`). Server không có internet → dùng gói zip bên dưới.
- Script hỏi tên instance, IP vCenter, user, cluster, port, chu kỳ, mật khẩu (gõ ẩn) — giống cài từ zip.
- Cài xong gõ `sudo esxi-menu` để quản lý.

Cập nhật bản mới từ GitHub:

```bash
sudo esxi-menu        # chon 13) Cap nhat ban moi tu GitHub (git pull)
```

hoặc làm tay:

```bash
cd /root/monitor-grafana-vcenter-full-details-prometheus && git pull
sudo bash deploy/install.sh           # cung ten instance, Enter de giu mat khau cu
```

Tạo gói zip cài offline (trên máy có Python + pyvmomi): `python deploy/build_zip.py`.

## Cài nhanh trên Linux từ `esxi-host-exporter-linux.zip`

Yêu cầu: Linux có systemd + Python ≥ 3.8 (Ubuntu 20.04+, Debian 11+, RHEL/Rocky 8+). **Không cần internet** — thư viện `pyvmomi` đã kèm trong gói.
Máy cài phải tới được vCenter cổng 443.

```bash
scp esxi-host-exporter-linux.zip user@<IP-server>:/tmp/
ssh user@<IP-server>
cd /tmp && unzip -o esxi-host-exporter-linux.zip     # khong co unzip: python3 -m zipfile -e esxi-host-exporter-linux.zip .
cd esxi-host-exporter
sudo bash install.sh
```

Script hỏi: tên instance, IP vCenter, user, cluster (`-` = tất cả), port (9811), chu kỳ (60s), **mật khẩu (gõ ẩn)**.
Cài xong in ra link `http://<ip>:9811/` (dashboard web) và `/metrics` (Prometheus).

### Quên lệnh? Gõ `sudo esxi-menu`

```
========= ESXi HOST EXPORTER - MENU =========
  1) Trang thai tat ca instance          7) Them vCenter / instance moi
  2) Xem log 1 instance                  8) Doi mat khau / cai lai 1 instance
  3) Restart 1 instance                  9) Sua cau hinh (.env) 1 instance
  4) Restart tat ca instance            10) Xem cau hinh InfluxDB (token da an)
  5) Kiem tra phien ban dang chay       11) Go 1 instance
  6) Cap nhat ban moi tu file zip       12) Cac lenh hay dung
  0) Thoat
```

- Mục 1 hiện bảng: instance, port, service active/inactive, **phiên bản**, số host, số host lỗi, dòng log gần nhất.
- Mục 6 tự làm đủ các bước cập nhật: `sha256sum -c` → giải nén → chép sang `/opt` → restart tất cả → in phiên bản mới.
- Mục 8 cài lại instance với thông tin cũ, chỉ hỏi mật khẩu mới.
- `install.sh` tự cài menu vào `/opt/esxi-host-exporter/menu.sh` và lệnh `/usr/local/bin/esxi-menu`.
  Server đã cài bản cũ: chạy mục 6 không có sẵn → cài 1 lần bằng `sudo bash install.sh` (cùng tên instance, Enter giữ mật khẩu)
  hoặc chép tay: `install -m 755 /home/esxi-host-exporter/menu.sh /opt/esxi-host-exporter/ && ln -sf /opt/esxi-host-exporter/menu.sh /usr/local/bin/esxi-menu`.

| Việc | Lệnh |
|---|---|
| Xem log | `journalctl -u esxi-host-exporter@pool18 -f` |
| Thêm vCenter/cluster khác | `sudo bash install.sh` với tên instance + port khác |
| Đổi mật khẩu / cập nhật code | `sudo bash install.sh` với **cùng** tên instance |
| Sửa ngưỡng cảnh báo | `sudo nano /etc/esxi-host-exporter/pool18.env` → `sudo systemctl restart esxi-host-exporter@pool18` |
| Gỡ | `sudo /opt/esxi-host-exporter/uninstall.sh` (thêm tên instance để gỡ 1 cái) |

- Chạy dưới user hệ thống `esxi-exporter` (không phải root); mật khẩu nằm ở `/etc/esxi-host-exporter/<tên>.env` quyền `600`.
- **Sai mật khẩu → service dừng hẳn** (exit 3, systemd không thử lại) để không khóa tài khoản vCenter.
- Lần lấy dữ liệu đầu với ~46 host mất 1–4 phút.

Đã test cài thật trên Ubuntu 22.04 (systemd) với vCenter <IP-vCenter>: 46 host / 73 disk, sai mật khẩu dừng đúng, gỡ sạch.

## Đẩy metric lên InfluxDB (tùy chọn, từ bản 2026.10.16-5)

Sau mỗi vòng lấy dữ liệu, exporter gửi toàn bộ metric lên InfluxDB (song song với `/metrics` cho Prometheus).
Mỗi metric → 1 measurement cùng tên (vd `esxi_host_cpu_usage_percent`), nhãn → tag (`cluster`, `host`, `nic`…),
giá trị → field `value`, timestamp = lúc lấy dữ liệu (precision giây). ~4.000 dòng / lần cho 87 host.

Bật bằng cách bỏ dấu `#` các dòng INFLUX trong `/etc/esxi-host-exporter/<instance>.env` rồi restart instance:

```bash
# InfluxDB 2.x
INFLUX_URL='http://10.16.16.x:8086'
INFLUX_ORG='fpt'
INFLUX_BUCKET='vmware'
INFLUX_TOKEN='<token co quyen write bucket>'
# InfluxDB 1.x (thay cho 4 dong tren)
INFLUX_URL='http://10.16.16.x:8086'
INFLUX_DB='vmware'
INFLUX_USER='...'        # bo trong neu khong bat xac thuc
INFLUX_PASSWORD='...'
```

```bash
systemctl restart esxi-host-exporter@pool18
journalctl -u esxi-host-exporter@pool18 -f      # phai thay "InfluxDB: da gui ... dong"
```

Lỗi InfluxDB (sai token, mất kết nối…) chỉ ghi log `InfluxDB LOI`, không ảnh hưởng `/metrics` và dashboard web.
Truy vấn mẫu (Flux): `from(bucket:"vmware") |> range(start:-1h) |> filter(fn:(r)=> r._measurement=="esxi_host_cpu_usage_percent" and r.cluster=="POOL17")`.

**Cách khác không cần sửa exporter**: dùng Telegraf `[[inputs.prometheus]] urls = ["http://<IP-server>:9811/metrics"]`
+ `[[outputs.influxdb_v2]]`.

## A. Dashboard "MONITOR RESOURCE HOST ESXi" (exporter `esxi_host_exporter.py`)

| File | Dùng để |
|---|---|
| `esxi_host_exporter.py` | Exporter tài nguyên host ESXi + vSAN (cần `vsan_disk_health.py` cùng thư mục) |
| `esxi_host_resource_grafana.json` | Dashboard Grafana |
| `alert-rules-esxi.yml` | Alert rule Prometheus theo bảng mapping cảnh báo |

Chạy (mỗi vCenter 1 service, port riêng):

```bash
VSAN_PASS='...' python3 esxi_host_exporter.py <IP-vCenter> monitor@vsphere.local POOL18-XD 9811 60
curl -s localhost:9811/metrics | grep esxi_host_status
```

`POOL18-XD` → thay bằng `-` để lấy mọi cluster của vCenter. Service systemd giống mục 1 bên dưới, chỉ đổi `ExecStart`:

```ini
ExecStart=/usr/bin/python3 /opt/vsan-disk-health/esxi_host_exporter.py <IP-vCenter> monitor@vsphere.local - 9811 60
```

Prometheus:

```yaml
  - job_name: 'esxi_host_resource_fpt_hcm'
    scrape_interval: 30s
    scrape_timeout: 20s
    static_configs:
      - targets: ['<IP-server>:9811']
rule_files:
  - /etc/prometheus/rules/alert-rules-esxi.yml
```

- **Dashboard web có sẵn, không cần Grafana**: mở `http://<máy chạy exporter>:9811/` (giao diện `esxi_dashboard.html`,
  dữ liệu `/api/state`, tự cập nhật 30s, lịch sử biểu đồ giữ trong RAM ~2 giờ — mất khi restart exporter).
- Mật khẩu: biến `VSAN_PASS`, hoặc dòng đầu file `.vsan_pass` cạnh script (đã có trong `.gitignore`), hoặc gõ khi chạy.
- Nhịp lấy dữ liệu: CPU/RAM/NIC/vmk drop/vSAN latency/resync mỗi `interval` (60s, ~26s/vòng với 46 host);
  vSAN disk health + số VM mỗi `ESXI_SLOW_INTERVAL` (mặc định 300s, ~35s/lần — vCenter cũng chỉ cập nhật health theo cache).
- **vSAN latency** lấy từ vSAN Performance Service (`host-domclient`, mẫu 5 phút) — cùng số với biểu đồ vSAN trên vCenter.
  Không dùng counter `datastore/disk` của host vì với NVMe chúng luôn = 0 (làm tròn theo ms).

**Exporter này đã gồm luôn metric `vsan_disk_*`** → không cần chạy thêm exporter 9810 (mục B chỉ dùng khi muốn chạy riêng phần disk).

### Trạng thái host (cột Status)

| Status | Khi nào |
|---|---|
| **ERROR** | Host không `connected` · vmnic uplink DOWN · có disk vSAN không green |
| **WARN** | Maintenance · CPU > 60% · RAM > 90% · write latency > 15ms · congestion > 60 · vmk vSAN drop > 0.1% |
| **OK** | Còn lại |

Ngưỡng đổi được bằng biến môi trường `ESXI_WARN_CPU`, `ESXI_WARN_RAM`, `ESXI_WARN_LATENCY_MS`, `ESXI_WARN_CONGESTION`, `ESXI_WARN_VMK_DROP_PCT`.
Cột **Lý do** ghi rõ nguyên nhân, ví dụ `NIC down: vmnic1; Disk Unhealthy: eui.C (TRANSIENT_ERROR)`.

### Dashboard Grafana — 1 file duy nhất `esxi_host_resource_grafana.json` (28 panel, 4 nhóm)

Grafana → **Dashboards → New → Import** → upload file → chọn datasource Prometheus → chọn Cluster.

- **Tổng quan**: Total host / OK / Cảnh báo / Lỗi / vSAN resync (hiện `–` khi = 0) / độ mới dữ liệu.
- **Bảng host**: Host · CPU% · RAM% · NIC `vmnic0 ▲ vmnic1 ▼` · DiskGroup vSAN · vSAN congestion · Write latency · VMs · Uptime · Status · Lý do.
  Biến **Trạng thái** = bộ lọc *Tất cả / Cảnh báo + Lỗi / Lỗi*. Bấm header để sort, **bấm tên host** → mở phần chi tiết của host đó.
- **Network**: bandwidth TX/RX từng vmnic (Mb/s, như MbTX/s của esxtop), **Packet Drop/Discard rate (%) của vmk vSAN** (tự nhận vmk gắn tag vSAN, không cần đoán vmk2), lịch sử link UP/DOWN.
- **Chi tiết host**: CPU/RAM, latency, bảng từng disk vSAN (disk group, health, congestion, dung lượng), lịch sử trạng thái.
- **vSAN Disk Health** (gộp từ dashboard disk cũ): Disks / Healthy / Unhealthy / host không có dữ liệu disk, bảng **Disk Unhealthy**
  (host, disk, health, operational, metadata, lý do), lịch sử health disk theo host, top 10 congestion & dung lượng, trạng thái exporter.

### Bảng mapping cảnh báo → rule

| Tình huống | Rule | Severity | for |
|---|---|---|---|
| vmnic Down | `EsxiVmnicDown` (`esxi_host_nic_up == 0`) | critical | 0s |
| Disk lỗi | `VsanDiskError` (`vsan_disk_health > 0`) | error | 0s |
| DiskGroup vSAN | `VsanDiskGroupUnhealthy` | unhealthy | 0s |
| Host disconnected | `EsxiHostDisconnected` | critical | 30s |
| vSAN resync > 0 | `VsanResyncInProgress` | warning | 2m |
| CPU > 60% | `EsxiCpuHigh` | warning | 5m |
| RAM > 90% | `EsxiRamHigh` | warning | 5m |
| Write latency > 15ms | `VsanWriteLatencyHigh` | warning | 10m |
| vSAN congestion | `VsanCongestion` (> 60) | warning | 30s |
| *(thêm)* vmk vSAN drop | `VsanVmkPacketDrop` (> 0.1%) | warning | 5m |

Gửi sang **Element**: route theo `severity` trong Alertmanager tới receiver Matrix/Element đang dùng.
Delay **0s / 5s** thực tế ≈ 1–2 phút (exporter lấy dữ liệu 60s/lần + scrape + evaluation). Cần gần tức thì cho vmnic down / disk lỗi → bật thêm **alarm có sẵn của vCenter** (*Network uplink redundancy lost*, *vSAN disk health*) gửi SNMP trap/webhook.

> ⚠️ `huong_dan_vsan.md` (exporter cũ) đang ghi **mật khẩu vCenter dạng chữ** trong code. Nên đổi mật khẩu đó và chuyển sang đọc từ file env như hướng dẫn ở đây.

---

## B. vSAN Disk Health

Giám sát **Health của từng disk vSAN** giống cột *Health* ở vCenter → Cluster → Configure → vSAN → Disk Management.
Dữ liệu lấy từ **vSAN Health Service của vCenter** (API `VsanQueryVcClusterHealthSummary`), chỉ đọc.

| File | Dùng để |
|---|---|
| `vsan_disk_health.py` | Script lấy dữ liệu: in JSON, xuất dashboard HTML, hoặc chạy **Prometheus exporter** |
| `dashboard_template.html` | Giao diện dashboard HTML (dùng khi xuất `.html`) |

## 1. Cài exporter trên máy Linux (vd. <IP-server> — cùng máy với các exporter vSAN đang chạy)

```bash
sudo mkdir -p /opt/vsan-disk-health
sudo cp vsan_disk_health.py dashboard_template.html /opt/vsan-disk-health/
sudo pip3 install "pyvmomi>=8.0.2"     # ban co san vSAN Health API
```

Tạo file chứa mật khẩu (chỉ root đọc được):

```bash
sudo tee /etc/vsan-disk-health.env >/dev/null <<'EOF'
VSAN_PASS='MAT_KHAU_VCENTER'
EOF
sudo chmod 600 /etc/vsan-disk-health.env
```

Tạo service systemd `/etc/systemd/system/vsan-disk-health.service`:

```ini
[Unit]
Description=vSAN Disk Health Prometheus Exporter (POOL18-XD)
After=network-online.target

[Service]
EnvironmentFile=/etc/vsan-disk-health.env
ExecStart=/usr/bin/python3 /opt/vsan-disk-health/vsan_disk_health.py <IP-vCenter> monitor@vsphere.local POOL18-XD :9810 120
Restart=always
RestartSec=30
User=nobody

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vsan-disk-health
journalctl -u vsan-disk-health -f        # phai thay dong "OK: ... dong"
curl -s localhost:9810/metrics | grep vsan_disk_health | head
```

- `:9810` là port exporter (tránh 8000–8004 đang dùng). `120` = lấy dữ liệu từ vCenter mỗi 120 giây.
- Bỏ `POOL18-XD` để lấy **tất cả** cluster vSAN của vCenter đó. Mỗi vCenter khác chạy thêm 1 service với port khác.
- Sai mật khẩu → exporter **dừng hẳn** (không thử lại, tránh khóa tài khoản); `Restart=always` sẽ chạy lại sau 30s — sửa file env rồi `systemctl restart`.
- Mặc định đọc **cache** của vSAN Health (nhẹ cho vCenter, cache được vCenter làm mới định kỳ). Thêm `VSAN_FRESH=1` vào file env để bắt chạy lại health check mỗi lần (nặng hơn, nên tăng interval lên ≥ 300).

## 2. Thêm vào Prometheus

```yaml
  - job_name: 'vsan_disk_health'
    scrape_interval: 60s
    scrape_timeout: 10s
    static_configs:
      - targets: ['<IP-server>:9810']
```

Reload Prometheus, kiểm tra target `vsan_disk_health` ở trạng thái **UP**.

## 3. Dashboard Grafana

Phần vSAN Disk Health đã **gộp vào** dashboard `esxi_host_resource_grafana.json` (mục A) — chỉ import 1 file đó.

## 4. Metric

Giá trị health: **0 = green, 1 = yellow, 2 = red, 3 = unknown**. vCenter hiển thị mọi giá trị khác 0 là *Unhealthy*.

| Metric | Nhãn |
|---|---|
| `vsan_disk_health` (+ `_op_health`, `_metadata_health`, `_capacity_health`, `_congestion_health`) | cluster, host, disk |
| `vsan_disk_info` = 1 | + uuid, diskgroup, health, op_health, metadata_health, reason |
| `vsan_disk_congestion_value` (0–255), `vsan_disk_used_ratio` (0–1) | cluster, host, disk |
| `vsan_host_disk_unreported` = 1 | cluster, host, reason |
| `vsan_disk_exporter_up`, `_last_success_timestamp_seconds`, `_collect_duration_seconds` | — |

Ví dụ alert rule (Prometheus):

```yaml
- alert: VsanDiskUnhealthy
  expr: vsan_disk_health > 0
  for: 5m
  labels: { severity: error }
  annotations:
    summary: "vSAN disk {{ $labels.disk }} tren {{ $labels.host }} Unhealthy"
- alert: VsanDiskExporterStale
  expr: time() - vsan_disk_exporter_last_success_timestamp_seconds > 1800
  labels: { severity: warning }
```

## 5. Chạy tay (không cần Prometheus)

```bash
python vsan_disk_health.py <IP-vCenter> monitor@vsphere.local POOL18-XD                 # in JSON
python vsan_disk_health.py <IP-vCenter> monitor@vsphere.local POOL18-XD result.json     # ghi file JSON
python vsan_disk_health.py <IP-vCenter> monitor@vsphere.local POOL18-XD dash.html 300   # dashboard HTML tu cap nhat
```
