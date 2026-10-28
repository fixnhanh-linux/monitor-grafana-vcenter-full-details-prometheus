#!/usr/bin/env bash
# Cai dat ESXi host + vSAN exporter (dashboard web + Prometheus) len Linux co systemd.
#
#   sudo ./install.sh                 # hoi tung thong tin
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

echo "-> Chep chuong trinh vao $APP"
install -d -m 755 "$APP" "$APP/vendor"
install -m 644 "$SRC/app/esxi_host_exporter.py" "$SRC/app/vsan_disk_health.py" \
               "$SRC/app/esxi_dashboard.html" "$SRC/app/dashboard_template.html" "$APP/"
install -m 755 "$SRC/uninstall.sh" "$APP/uninstall.sh"
install -m 755 "$SRC/menu.sh" "$APP/menu.sh"
ln -sf "$APP/menu.sh" /usr/local/bin/esxi-menu   # go "esxi-menu" neu quen lenh
rm -rf "$APP/vendor"/*
cp -r "$SRC/vendor/." "$APP/vendor/"
chmod -R a+rX "$APP"

echo "-> Kiem tra thu vien pyVmomi"
PYTHONPATH="$APP/vendor" python3 -c 'import pyVmomi, pyVim.connect; from pyVmomi import vim; vim.cluster.VsanVcClusterHealthSystem' \
  || die "khong import duoc pyVmomi tu $APP/vendor"

if ! id "$SVC_USER" >/dev/null 2>&1; then
  echo "-> Tao user he thong $SVC_USER"
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SVC_USER" 2>/dev/null \
    || useradd -r -M -s /sbin/nologin "$SVC_USER"
fi

echo "-> Ghi cau hinh $ENV_FILE (chi root doc duoc)"
install -d -m 700 "$CONF"
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
