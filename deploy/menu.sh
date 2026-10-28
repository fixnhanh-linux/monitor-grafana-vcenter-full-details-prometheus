#!/usr/bin/env bash
# Menu quan ly ESXi host exporter - go "esxi-menu" (can root) neu quen lenh.
APP=/opt/esxi-host-exporter
CONF=/etc/esxi-host-exporter
SVC=esxi-host-exporter

R=$'\e[31m'; G=$'\e[32m'; Y=$'\e[33m'; B=$'\e[36m'; N=$'\e[0m'
[ -t 1 ] || { R=; G=; Y=; B=; N=; }

pause() { echo; read -r -p "Nhan Enter de quay lai menu..." _; }
instances() { for f in "$CONF"/*.env; do [ -e "$f" ] && basename "$f" .env; done; }
port_of() { grep -m1 '^PORT=' "$CONF/$1.env" 2>/dev/null | cut -d= -f2 | tr -d "'\""; }
val_of() { grep -m1 "^$2=" "$CONF/$1.env" 2>/dev/null | cut -d= -f2- | tr -d "'\""; }

pick() {  # chon 1 instance -> bien PICK
  mapfile -t LIST < <(instances)
  if [ ${#LIST[@]} -eq 0 ]; then echo "${Y}Chua co instance nao. Chon muc 7 de cai.${N}"; return 1; fi
  echo "Chon instance:"
  local i=1; for n in "${LIST[@]}"; do printf "  %d) %s (port %s)\n" "$i" "$n" "$(port_of "$n")"; i=$((i+1)); done
  read -r -p "So thu tu: " k
  [[ "$k" =~ ^[0-9]+$ ]] && [ "$k" -ge 1 ] && [ "$k" -le ${#LIST[@]} ] || { echo "${R}Lua chon khong hop le${N}"; return 1; }
  PICK=${LIST[$((k-1))]}
}

version_of_port() {
  curl -s -m 5 "localhost:$1/metrics" | grep -o 'esxi_exporter_build_info{version="[^"]*"' | cut -d'"' -f2
}

status_all() {
  printf "%-12s %-6s %-10s %-16s %-6s %-6s %s\n" INSTANCE PORT SERVICE VERSION HOST LOI "LAN LAY DU LIEU GAN NHAT"
  for n in $(instances); do
    p=$(port_of "$n"); st=$(systemctl is-active "$SVC@$n" 2>/dev/null)
    m=$(curl -s -m 5 "localhost:$p/metrics")
    ver=$(grep -o 'esxi_exporter_build_info{version="[^"]*"' <<<"$m" | cut -d'"' -f2)
    hosts=$(grep -c '^esxi_host_status{' <<<"$m"); bad=$(grep '^esxi_host_status{' <<<"$m" | grep -vc ' 0$')
    last=$(journalctl -u "$SVC@$n" -n 30 --no-pager -o cat 2>/dev/null | grep -E 'OK:|LOI|that bai' | tail -1)
    [ "$st" = active ] && c=$G || c=$R
    printf "%-12s %-6s ${c}%-10s${N} %-16s %-6s %-6s %s\n" "$n" "$p" "$st" "${ver:-${R}cu/khong ro${N}}" "$hosts" "$bad" "$last"
  done
}

update_from_zip() {
  read -r -p "Duong dan file zip [/home/esxi-host-exporter-linux.zip]: " Z
  Z=${Z:-/home/esxi-host-exporter-linux.zip}
  [ -f "$Z" ] || { echo "${R}Khong thay $Z${N}"; return; }
  if [ -f "$Z.sha256" ]; then
    (cd "$(dirname "$Z")" && sha256sum -c "$(basename "$Z").sha256") || { echo "${R}SHA256 SAI - dung lai, chep lai ca 2 file.${N}"; return; }
  else
    echo "${Y}Khong co file $Z.sha256 - khong kiem tra duoc file co dung khong.${N}"
    read -r -p "Van tiep tuc? (y/N): " a; [ "$a" = y ] || return
  fi
  T=$(mktemp -d); python3 -m zipfile -e "$Z" "$T" || { rm -rf "$T"; return; }
  echo "Phien ban trong goi: ${B}$(cat "$T/esxi-host-exporter/VERSION" 2>/dev/null)${N}"
  read -r -p "Cai ban nay va restart tat ca instance? (y/N): " a
  if [ "$a" = y ]; then
    install -m 644 "$T"/esxi-host-exporter/app/* "$APP/"
    install -m 755 "$T/esxi-host-exporter/menu.sh" "$APP/menu.sh" 2>/dev/null
    install -m 755 "$T/esxi-host-exporter/uninstall.sh" "$APP/uninstall.sh" 2>/dev/null
    for n in $(instances); do systemctl restart "$SVC@$n"; done
    sleep 3; for n in $(instances); do p=$(port_of "$n"); echo "  $n ($p): ${G}$(version_of_port "$p")${N}"; done
  fi
  rm -rf "$T"
}

influx_show() {
  pick || return
  echo "Cau hinh InfluxDB cua $PICK (token/password da an):"
  grep -E '^#?INFLUX_' "$CONF/$PICK.env" | sed -E "s/^(#?INFLUX_(TOKEN|PASSWORD)=).*/\1*****/"
  echo; journalctl -u "$SVC@$PICK" -n 200 --no-pager -o cat | grep InfluxDB | tail -3
  echo; echo "Bat/sua: chon muc 9 (sua file .env), bo dau # o cac dong INFLUX_, luu, menu se restart."
}

cheatsheet() {
cat <<EOF
${B}Lenh hay dung (thay pool18 bang ten instance)${N}
  Trang thai      : systemctl status $SVC@pool18
  Log truc tiep   : journalctl -u $SVC@pool18 -f
  Restart         : systemctl restart $SVC@pool18
  Restart tat ca  : systemctl restart '$SVC@*'
  Danh sach       : systemctl list-units '$SVC@*' --no-legend
  Phien ban       : curl -s localhost:9811/metrics | grep build_info
  Dashboard web   : http://$(hostname -I 2>/dev/null | awk '{print $1}'):9811/
  Cau hinh        : $CONF/<instance>.env   (quyen 600, co mat khau)
  Kiem tra zip    : sha256sum -c esxi-host-exporter-linux.zip.sha256
  Them / doi pass : cd /home/esxi-host-exporter && bash install.sh
  Go 1 instance   : $APP/uninstall.sh pool18
EOF
}

[ "$(id -u)" -eq 0 ] || { echo "Can chay bang root: sudo esxi-menu"; exit 1; }

while true; do
  clear 2>/dev/null
  cat <<EOF
${B}========= ESXi HOST EXPORTER - MENU =========${N}
  1) Trang thai tat ca instance
  2) Xem log 1 instance (Ctrl+C de thoat log)
  3) Restart 1 instance
  4) Restart tat ca instance
  5) Kiem tra phien ban dang chay
  6) Cap nhat ban moi tu file zip
  7) Them vCenter / instance moi
  8) Doi mat khau / cai lai 1 instance
  9) Sua cau hinh (.env) 1 instance
 10) Xem cau hinh InfluxDB
 11) Go 1 instance
 12) Cac lenh hay dung
  0) Thoat
EOF
  read -r -p "Chon: " c
  case "$c" in
    1) status_all; pause ;;
    2) if pick; then trap ':' INT; journalctl -u "$SVC@$PICK" -n 50 -f; trap - INT; fi ;;  # Ctrl+C chi thoat log
    3) pick && systemctl restart "$SVC@$PICK" && echo "${G}Da restart $PICK${N}"; pause ;;
    4) for n in $(instances); do systemctl restart "$SVC@$n" && echo "${G}Da restart $n${N}"; done; pause ;;
    5) for n in $(instances); do p=$(port_of "$n"); v=$(version_of_port "$p"); echo "  $n ($p): ${v:-${R}khong co build_info (ban cu hoac chua chay)${N}}"; done
       echo "  Ban trong $APP: $(grep -m1 '^VERSION' "$APP/esxi_host_exporter.py" | cut -d'"' -f2)"; pause ;;
    6) update_from_zip; pause ;;
    7|8) D=/home/esxi-host-exporter
       [ -f "$D/install.sh" ] || read -r -p "Thu muc da giai nen goi (co install.sh): " D
       if [ -f "$D/install.sh" ]; then
         if [ "$c" = 8 ]; then pick && (cd "$D" && NAME="$PICK" VC="$(val_of "$PICK" VC)" VC_USER="$(val_of "$PICK" VC_USER)" \
              CLUSTER="$(val_of "$PICK" CLUSTER)" PORT="$(port_of "$PICK")" INTERVAL="$(val_of "$PICK" INTERVAL)" bash install.sh)
         else (cd "$D" && bash install.sh); fi
       else echo "${R}Khong thay install.sh - giai nen goi zip truoc.${N}"; fi
       pause ;;
    9) pick && { ${EDITOR:-nano} "$CONF/$PICK.env"; read -r -p "Restart $PICK de ap dung? (Y/n): " a
                 [ "$a" = n ] || { systemctl restart "$SVC@$PICK" && echo "${G}Da restart${N}"; }; }; pause ;;
    10) influx_show; pause ;;
    11) pick && { read -r -p "Go instance $PICK? (y/N): " a; [ "$a" = y ] && "$APP/uninstall.sh" "$PICK"; }; pause ;;
    12) cheatsheet; pause ;;
    0|q|Q) exit 0 ;;
    *) ;;
  esac
done
