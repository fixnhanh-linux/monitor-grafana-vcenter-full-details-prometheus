# scripts/

| File | Dùng để |
|---|---|
| `install.sh` | Cài / cập nhật / đổi mật khẩu 1 instance: `sudo bash scripts/install.sh` |
| `uninstall.sh` | Gỡ: `sudo /opt/esxi-host-exporter/uninstall.sh <instance>` (bỏ tên = gỡ tất cả) |
| `menu.sh` | Menu quản lý, cài thành lệnh `sudo esxi-menu` |
| `esxi-host-exporter@.service` | Unit systemd dạng template, mỗi vCenter 1 instance |
| `build_zip.py` | Tạo gói cài offline `esxi-host-exporter-linux.zip` + `.sha256`: `python scripts/build_zip.py` |
