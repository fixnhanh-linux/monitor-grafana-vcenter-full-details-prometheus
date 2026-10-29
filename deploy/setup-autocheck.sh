#!/usr/bin/env bash
# (C) 2026 FIX NHANH. Bat "tu dong kiem tra ban moi" (chi bao, khong tu cai).
# Dung cho server DANG CHAY: chi can chay 1 lan.
#   sudo bash deploy/setup-autocheck.sh          # bat
#   sudo bash deploy/setup-autocheck.sh off      # tat
set -e
[ "$(id -u)" -eq 0 ] || { echo "Can chay bang root: sudo bash setup-autocheck.sh"; exit 1; }
APP=/opt/esxi-host-exporter
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$1" = off ]; then
  systemctl disable --now esxi-update-check.timer 2>/dev/null || true
  rm -f "$APP/.update-available"
  echo "Da TAT tu dong kiem tra ban moi."
  exit 0
fi

install -m 755 "$SRC/esxi-update-check.sh" "$APP/esxi-update-check.sh"
install -m 644 "$SRC/esxi-update-check.service" /etc/systemd/system/esxi-update-check.service
install -m 644 "$SRC/esxi-update-check.timer" /etc/systemd/system/esxi-update-check.timer
systemctl daemon-reload
systemctl enable --now esxi-update-check.timer
systemctl start esxi-update-check.service 2>/dev/null || true   # kiem tra ngay 1 lan
echo "Da BAT tu dong kiem tra ban moi (hang ngay)."
echo "  - Co ban moi -> menu hien banner va ghi log (journalctl -t esxi-update)."
echo "  - Khong tu cai; ban chu dong: esxi-menu -> 13."
echo "  - Tat lai: sudo bash setup-autocheck.sh off"
