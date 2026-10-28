#!/usr/bin/env bash
# Copyright (c) 2026 FIX NHANH. All rights reserved. Proprietary - xem file LICENSE.
# Cai dat ESXi host + vSAN exporter (dashboard web + Prometheus) len Linux co systemd.
#
#   sudo ./install.sh                 # hoi tung thong tin (tu goi zip)
#   sudo bash deploy/install.sh       # tu repo git clone (tu tai pyVmomi bang pip)
#   sudo NAME=pool18 VC=<IP-vCenter> VC_USER=monitor@vsphere.local CLUSTER=POOL18-XD PORT=9811 ./install.sh
#
# Chay lai voi NAME khac de them vCenter/cluster khac (moi instance 1 port).
# Chay lai voi cung NAME de cap nhat code / doi mat khau.
set -euo pipefail

APP=/opt/esxi-host-exporter
CONF=/etc/esxi-host-exporter
UNIT=esxi-host-exporter@.service
SVC_USER=esxi-exporter
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

die() { echo "LOI: $*" >&2; exit 1; }
ask() {  # ask BIEN "Cau hoi" "mac dinh"
  local var=$1 q=$2 def=${3:-} val=${!1:-}
  if [ -z "$val" ]; then
    read -r -p "$q${def:+ [$def]}: " val
    val=${val:-$def}
  fi
  [ -n "$val" ] || die "$q khong duoc de trong"
  printf -v "$var" '%s' "$val"
}

[ "$(id -u)" -eq 0 ] || die "can chay bang root: sudo ./install.sh"
command -v systemctl >/dev/null || die "may nay khong co systemd"
command -v python3 >/dev/null || die "chua co python3 (Ubuntu/Debian: apt install python3 | RHEL: dnf install python3)"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' \
  || die "can Python >= 3.8 (dang co $(python3 -V 2>&1))"

echo "== Cai dat ESXi host exporter =="
ask NAME     "Ten instance (vd: pool18, chi chu/so/-)" "pool18"
[[ "$NAME" =~ ^[A-Za-z0-9_-]+$ ]] || die "ten instance chi gom chu, so, - va _"
ask VC       "IP/hostname vCenter"
ask VC_USER  "User vCenter (chi can quyen Read-only)" "monitor@vsphere.local"
ask CLUSTER  "Cluster (- = tat ca cluster)" "-"
ask PORT     "Port dashboard/metrics" "9811"
ask INTERVAL "Chu ky lay du lieu (giay)" "60"
[[ "$PORT" =~ ^[0-9]+$ && "$INTERVAL" =~ ^[0-9]+$ ]] || die "PORT va INTERVAL phai la so"

ENV_FILE="$CONF/$NAME.env"
if [ -z "${VSAN_PASS:-}" ]; then
  if [ -f "$ENV_FILE" ] && grep -q '^VSAN_PASS=' "$ENV_FILE"; then
    read -r -s -p "Mat khau vCenter (Enter = giu mat khau cu): " VSAN_PASS; echo
  else
    read -r -s -p "Mat khau vCenter: " VSAN_PASS; echo
    [ -n "$VSAN_PASS" ] || die "mat khau khong duoc de trong"
  fi
fi

# Chay duoc tu 2 noi: goi zip (install.sh + app/ + vendor/) hoac repo git clone (deploy/install.sh, code o exporter/)
if [ -f "$SRC/app/esxi_host_exporter.py" ]; then FILES="$SRC/app"; else FILES="$(cd "$SRC/../exporter" 2>/dev/null && pwd)"; fi
[ -f "$FILES/esxi_host_exporter.py" ] || die "khong thay esxi_host_exporter.py (chay tu goi zip hoac repo git clone)"

# pyVmomi 9.x can Python >= 3.10; Python 3.8/3.9 dung pyVmomi 8.0.3 (goi zip kem ca 2: vendor/ va vendor-py38/)
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then VSRC="$SRC/vendor"; PIPSPEC="pyvmomi>=8.0.2"
else VSRC="$SRC/vendor-py38"; PIPSPEC="pyvmomi>=8.0.2,<9"; fi

# Cai pyVmomi vao thu muc tam, kiem tra import duoc roi moi thay -> loi thi instance dang chay khong bi anh huong
install -d -m 755 "$APP"
NEWV="$APP/vendor.new"; rm -rf "$NEWV"; install -d -m 755 "$NEWV"
if [ -d "$VSRC" ]; then
  echo "-> pyVmomi kem trong goi ($(basename "$VSRC"), Python $PYV)"
  cp -r "$VSRC/." "$NEWV/"                       # goi zip: khong can internet
elif [ -d "$SRC/vendor" ] && [ "$VSRC" != "$SRC/vendor" ]; then
  rm -rf "$NEWV"; die "goi zip nay chi co pyVmomi cho Python >= 3.10 (server dang Python $PYV) - lay goi zip moi (co vendor-py38/)"
else
  echo "-> Tai $PIPSPEC bang pip (repo git clone, Python $PYV, can internet)"
  python3 -m pip --version >/dev/null 2>&1 \
    || { rm -rf "$NEWV"; die "chua co pip: apt install python3-pip | dnf install python3-pip (hoac dung goi zip offline)"; }
  python3 -m pip install -q --no-cache-dir --target "$NEWV" "$PIPSPEC" 2>/dev/null \
    || python3 -m pip install -q --no-cache-dir --break-system-packages --target "$NEWV" "$PIPSPEC" \
    || { rm -rf "$NEWV"; die "pip khong cai duoc pyvmomi (kiem tra internet / proxy)"; }
fi
chmod -R a+rX "$NEWV"

echo "-> Kiem tra thu vien pyVmomi"
PYTHONPATH="$NEWV" python3 -c 'import pyVmomi, pyVim.connect; from pyVmomi import vim; vim.cluster.VsanVcClusterHealthSystem' \
  || { rm -rf "$NEWV"; die "khong import duoc pyVmomi voi Python $PYV - chua thay doi gi tren server"; }

echo "-> Chep chuong trinh vao $APP"
rm -rf "$APP/vendor.old"; [ -d "$APP/vendor" ] && mv "$APP/vendor" "$APP/vendor.old"
mv "$NEWV" "$APP/vendor"; rm -rf "$APP/vendor.old"
rm -f "$APP/esxi_host_exporter.py" "$APP/vsan_disk_health.py" "$APP/esxi_dashboard.html" "$APP/dashboard_template.html" "$APP/app.bundle"
for f in "$FILES"/*.py "$FILES"/*.html "$FILES"/*.bundle; do
  [ -f "$f" ] && [ "$(basename "$f")" != esxi_launcher.py ] && install -m 644 "$f" "$APP/"
done
[ -f "$APP/app.bundle" ] && echo "   (goi bao ve: ma nguon duoc ma hoa trong app.bundle)"
install -m 755 "$SRC/uninstall.sh" "$APP/uninstall.sh"
install -m 755 "$SRC/menu.sh" "$APP/menu.sh"
ln -sf "$APP/menu.sh" /usr/local/bin/esxi-menu   # go "esxi-menu" neu quen lenh
chmod -R a+rX "$APP"

if ! id "$SVC_USER" >/dev/null 2>&1; then
  echo "-> Tao user he thong $SVC_USER"
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SVC_USER" 2>/dev/null \
    || useradd -r -M -s /sbin/nologin "$SVC_USER"
fi

echo "-> Ghi cau hinh $ENV_FILE (chi root doc duoc)"
install -d -m 750 -o root -g "$SVC_USER" "$CONF"   # service doc duoc license.key; file .env van 600 root
OLD_PASS_LINE=""
if [ -z "$VSAN_PASS" ] && [ -f "$ENV_FILE" ]; then
  OLD_PASS_LINE=$(grep '^VSAN_PASS=' "$ENV_FILE")
fi
quote() {  # dua gia tri vao EnvironmentFile cua systemd an toan voi moi ky tu dac biet
  local s=$1
  if [[ "$s" != *"'"* ]]; then
    printf "'%s'" "$s"            # nhay don: systemd giu nguyen moi ky tu
  else
    s=${s//\\/\\\\}; s=${s//\"/\\\"}; s=${s//\$/\\\$}
    printf '"%s"' "$s"
  fi
}
umask 077
{
  echo "# Tao boi install.sh luc $(date '+%F %T') - KHONG chia se file nay"
  echo "VC=$(quote "$VC")"
  echo "VC_USER=$(quote "$VC_USER")"
  echo "CLUSTER=$(quote "$CLUSTER")"
  echo "PORT=$PORT"
  echo "INTERVAL=$INTERVAL"
  if [ -n "$OLD_PASS_LINE" ]; then echo "$OLD_PASS_LINE"; else echo "VSAN_PASS=$(quote "$VSAN_PASS")"; fi
  echo "# Nguong canh bao (bo comment de doi):"
  echo "#ESXI_WARN_CPU=60"
  echo "#ESXI_WARN_RAM=90"
  echo "#ESXI_WARN_LATENCY_MS=15"
  echo "#ESXI_WARN_CONGESTION=60"
  echo "#ESXI_WARN_VMK_DROP_PCT=0.1"
  echo "#ESXI_SLOW_INTERVAL=300"
  echo "# Chi theo doi vmnic >= 10GB (0 = tat ca vmnic uplink):"
  echo "#ESXI_NIC_MIN_MBPS=10000"
  echo "# Day metric len InfluxDB (bo dau # de bat). InfluxDB 2.x:"
  echo "#INFLUX_URL='http://10.16.16.x:8086'"
  echo "#INFLUX_ORG='fpt'"
  echo "#INFLUX_BUCKET='vmware'"
  echo "#INFLUX_TOKEN='...'"
  echo "# InfluxDB 1.x: INFLUX_URL + INFLUX_DB (+ INFLUX_USER, INFLUX_PASSWORD):"
  echo "#INFLUX_DB='vmware'"
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"; chown root:root "$ENV_FILE"
umask 022

# Ban quyen: file license do FIX NHANH cap (gan machine-id). Dat canh install.sh (license.key) hoac LICENSE_FILE=/duong/dan
LIC_DST=/etc/esxi-host-exporter/license.key
LIC_SRC="${LICENSE_FILE:-}"; [ -n "$LIC_SRC" ] || for f in "$SRC/license.key" "$SRC"/*.license.key /home/*.license.key; do [ -f "$f" ] && { LIC_SRC="$f"; break; }; done
if [ -n "$LIC_SRC" ] && [ -f "$LIC_SRC" ]; then
  install -m 640 -o root -g "$SVC_USER" "$LIC_SRC" "$LIC_DST" && echo "-> Da cai license: $LIC_SRC"
fi
echo "-> Kiem tra ban quyen"
python3 "$APP/license_check.py" status "$LIC_DST" || {
  echo "!! Chua co license hop le. Gui machine-id tren cho FIX NHANH de xin license, luu vao $LIC_DST"
  echo "   roi: sudo systemctl restart esxi-host-exporter@$NAME   (hoac chay lai install.sh voi LICENSE_FILE=...)"
}
echo "-> Cai systemd unit"
install -m 644 "$SRC/$UNIT" "/etc/systemd/system/$UNIT"
systemctl daemon-reload
systemctl enable "esxi-host-exporter@$NAME" >/dev/null 2>&1
systemctl restart "esxi-host-exporter@$NAME"

echo "-> Cho exporter lay du lieu lan dau (46 host co the mat 1-4 phut, cho toi da 8 phut)..."
ok=""
for _ in $(seq 1 96); do
  sleep 5
  if ! systemctl is-active --quiet "esxi-host-exporter@$NAME"; then
    break
  fi
  if python3 - "$PORT" <<'EOF' 2>/dev/null; then ok=1; break; fi
import json, sys, urllib.request
s = json.load(urllib.request.urlopen("http://127.0.0.1:%s/api/state" % sys.argv[1], timeout=5))
sys.exit(0 if s.get("last_success") else 1)
EOF
done

echo
journalctl -u "esxi-host-exporter@$NAME" -n 5 --no-pager || true
echo
if [ -n "$ok" ]; then
  IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  echo "OK - exporter dang chay."
  echo "   Dashboard web : http://${IP:-<ip-may-nay>}:$PORT/"
  echo "   Prometheus    : http://${IP:-<ip-may-nay>}:$PORT/metrics"
  echo "   Log           : journalctl -u esxi-host-exporter@$NAME -f"
  echo "   Go cai dat    : sudo $APP/uninstall.sh $NAME   (bo ten = go tat ca)"
  echo "   Quen lenh?    : sudo esxi-menu"
  echo "   Mo firewall neu can: ufw allow $PORT/tcp   |   firewall-cmd --add-port=$PORT/tcp --permanent && firewall-cmd --reload"
elif systemctl is-active --quiet "esxi-host-exporter@$NAME"; then
  echo "Service dang chay nhung chua lay xong du lieu (vCenter cham?). Theo doi: journalctl -u esxi-host-exporter@$NAME -f"
else
  code=$(systemctl show -p ExecMainStatus --value "esxi-host-exporter@$NAME")
  [ "$code" = "3" ] && die "dang nhap vCenter that bai (sai user/mat khau). Chay lai: sudo ./install.sh voi NAME=$NAME"
  die "service khong chay duoc - xem: journalctl -u esxi-host-exporter@$NAME -n 50"
fi
