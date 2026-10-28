# exporter/

Code chạy trên server (được `deploy/install.sh` chép vào `/opt/esxi-host-exporter`).

| File | Vai trò |
|---|---|
| `esxi_host_exporter.py` | Exporter chính: lấy dữ liệu vCenter, phục vụ `/metrics`, `/api/state`, dashboard web `/`, đẩy InfluxDB (tuỳ chọn) |
| `vsan_disk_health.py` | Module health disk vSAN (dùng chung); chạy riêng được để xuất JSON / HTML |
| `esxi_dashboard.html` | Giao diện dashboard web tại `http://<server>:<port>/` |
| `dashboard_template.html` | Mẫu HTML khi `vsan_disk_health.py` xuất file `.html` |

Chạy thử: `VSAN_PASS='...' python3 esxi_host_exporter.py <IP-vCenter> <user> - 9811 60` (cần `pip install pyvmomi`).
