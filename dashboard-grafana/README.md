# dashboard-grafana/

`esxi_host_resource_grafana.json` — dashboard **MONITOR RESOURCE HOST ESXi** (uid `esxi-host-resource`).

Grafana → Dashboards → New → Import → upload file → chọn datasource Prometheus → chọn Cluster.
Đã có bản cũ: chọn **Import (Overwrite)**. Cần Prometheus đang scrape exporter (xem `../prometheus/`).

**Đã sửa tay dashboard (đổi tên row/panel) và không muốn mất?** Không Import Overwrite — dùng menu **mục 16 (Cập nhật Grafana)**: chèn thêm mục vSAN Cluster Partition vào dashboard đang chạy qua API, giữ nguyên phần đã sửa, có backup (`/opt/esxi-host-exporter/grafana-backup/`). Cần token Service account role Editor. Chạy tay: `python3 add_vsan_partition_panels.py <url-grafana> [--apply]`.
