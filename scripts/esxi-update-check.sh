#!/usr/bin/env bash
# (C) 2026 FIX NHANH. Kiem tra GitHub co ban moi khong - CHI BAO, khong tu cai.
# Timer esxi-update-check.timer chay dinh ky. Co ban moi -> ghi file co de menu hien banner.
REPO_NAME=monitor-grafana-vcenter-full-details-prometheus
APP=/opt/esxi-host-exporter
FLAG="$APP/.update-available"

RP=""
for c in /root/$REPO_NAME /home/*/$REPO_NAME /opt/$REPO_NAME; do
  [ -d "$c/.git" ] && { RP="$c"; break; }
done
[ -n "$RP" ] || exit 0                       # khong co git clone -> bo qua (ban cai bang zip)

git -C "$RP" fetch -q origin main 2>/dev/null || exit 0
L=$(git -C "$RP" rev-parse HEAD 2>/dev/null)
R=$(git -C "$RP" rev-parse origin/main 2>/dev/null)
if [ -n "$R" ] && [ "$L" != "$R" ]; then
  short=$(git -C "$RP" rev-parse --short origin/main 2>/dev/null)
  when=$(git -C "$RP" log -1 --format=%cd --date=format:'%d/%m %H:%M' origin/main 2>/dev/null)
  printf '%s | %s' "$short" "$when" > "$FLAG"
  logger -t esxi-update "Co ban moi tren GitHub: $short ($when) - chon esxi-menu 13 de cap nhat" 2>/dev/null
else
  rm -f "$FLAG"                              # da moi nhat
fi
