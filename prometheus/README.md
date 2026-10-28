# prometheus/

| File | Chép vào | Ghi chú |
|---|---|---|
| `scrape-esxi-host-resource.yml` | `/etc/prometheus/scrape_configs/` (hoặc dán vào `prometheus.yml`) | Thay `<IP-server>`, port từng instance, nhãn `site` / `pool` |
| `alert-rules-esxi.yml` | Thư mục khai báo ở `rule_files` | 12 rule theo bảng mapping cảnh báo |

Sau khi chép: `promtool check config /etc/prometheus/prometheus.yml && systemctl reload prometheus`.
