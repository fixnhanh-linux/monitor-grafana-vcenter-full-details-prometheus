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

installed_ver() { grep -m1 '^VERSION' "$APP/esxi_host_exporter.py" 2>/dev/null | cut -d'"' -f2; }
my_ip() { hostname -I 2>/dev/null | awk '{print $1}'; }

# Bao cao trang thai: bash gom service/.env/log, python doc /metrics tung instance -> bang tong hop + chi tiet
read -r -d '' STATUS_PY <<'PY'
import re, shutil, sys, time, urllib.request
ip, inst_ver, hostname = sys.argv[1:4]
cols = shutil.get_terminal_size((110, 30)).columns
TTY = sys.stdout.isatty()
def c(code, s): return "\033[%sm%s\033[0m" % (code, s) if TTY and code else s
RED, GRN, YEL, CYN, DIM, BLD = "1;31", "32", "33", "36", "2", "1"
W = 108
PAD = " " * max(0, (cols - W) // 2)
def say(s=""): print(PAD + s)
def cell(s, w, code=None, right=False):
    s = str(s)[:w]; s = s.rjust(w) if right else s.ljust(w)
    return c(code, s)
LBL = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')
def parse(text):
    out = {}
    for ln in text.splitlines():
        if not ln or ln[0] == "#": continue
        try:
            head, val = ln.rsplit(" ", 1); val = float(val)
        except ValueError: continue
        if "{" in head:
            name, rest = head.split("{", 1)
            lab = {k: v.replace('\\"', '"').replace("\\n", " ").replace("\\\\", "\\") for k, v in LBL.findall(rest)}
        else: name, lab = head, {}
        out.setdefault(name, []).append((lab, val))
    return out
def fetch(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%s/metrics" % port, timeout=8) as r:
            return parse(r.read().decode("utf-8", "replace")), ""
    except Exception as e:
        return None, str(e)[:60]
def ago(sec):
    sec = int(sec)
    if sec < 60: return "%ds truoc" % sec
    if sec < 3600: return "%dm%02ds truoc" % (sec // 60, sec % 60)
    return "%dh%02dm truoc" % (sec // 3600, sec % 3600 // 60)
def dur(sec):
    sec = int(sec); d, h, m = sec // 86400, sec % 86400 // 3600, sec % 3600 // 60
    return ("%dd %dh" % (d, h)) if d else ("%dh %dm" % (h, m)) if h else "%dm" % m
def gb(b):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or u == "TB": return "%.1f %s" % (b, u)
        b /= 1024.0

now = time.time()
rows = [l.rstrip("\n").split("\t") for l in sys.stdin if l.strip()]
say(c(BLD, "TRANG THAI ESXi HOST EXPORTER".center(W)))
say(c(DIM, ("%s (%s)  |  %s  |  ban cai trong /opt: %s" % (hostname, ip, time.strftime("%d/%m/%Y %H:%M:%S"), inst_ver or "?")).center(W)))
if not rows:
    say(); say(c(YEL, "Chua co instance nao. Chon muc 7 de cai.")); sys.exit()

infos = []
for r in rows:
    r += [""] * (10 - len(r))
    name, port, svc, since, vc, user, cluster, interval, influx, lastlog = r[:10]
    m, err = fetch(port) if svc == "active" else (None, "service " + svc)
    i = dict(name=name, port=port, svc=svc, since=int(since or 0), vc=vc, user=user, cluster=cluster,
             interval=int(interval or 60), influx=influx, lastlog=lastlog, m=m, err=err)
    if m is not None:
        g = lambda k: m.get(k, [])
        i["ver"] = next((l.get("version") for l, _ in g("esxi_exporter_build_info")), "")
        info = {l.get("host"): l for l, _ in g("esxi_host_info")}
        i["hosts"] = [(l.get("cluster", ""), l.get("host", ""), int(v), info.get(l.get("host"), {})) for l, v in g("esxi_host_status")]
        i["discon"] = sum(1 for _, v in g("esxi_host_connected") if v == 0)
        i["maint"] = sum(1 for _, v in g("esxi_host_maintenance") if v == 1)
        disks = g("vsan_disk_health")
        i["disks"], i["dbad"] = len(disks), [l for l, v in disks if v != 0]
        i["nicdown"] = [(l.get("host"), l.get("nic")) for l, v in g("esxi_host_nic_up") if v == 0]
        objs = {l.get("cluster"): v for l, v in g("esxi_vsan_resync_objects")}
        i["resync"] = [(l.get("cluster"), objs.get(l.get("cluster"), 0), v) for l, v in g("esxi_vsan_resync_bytes") if v > 0]
        i["last"] = next((v for _, v in g("vsan_disk_exporter_last_success_timestamp_seconds")), 0)
        i["up"] = next((v for _, v in g("vsan_disk_exporter_up")), 0)
    infos.append(i)

# ---- bang tong hop
say()
say(c(CYN, cell("INSTANCE", 11) + cell("PORT", 6) + cell("SERVICE", 10) + cell("PHIEN BAN", 15) + cell("HOST", 6, right=True)
           + cell("OK", 5, right=True) + cell("WARN", 6, right=True) + cell("ERROR", 7, right=True) + cell("DISK", 6, right=True)
           + cell("DISK LOI", 10, right=True) + cell("NIC DOWN", 10, right=True) + "  DU LIEU MOI NHAT"))
say(c(DIM, "-" * W))
tot = [0] * 7
for i in infos:
    line = cell(i["name"], 11) + cell(i["port"], 6) + cell(i["svc"], 10, GRN if i["svc"] == "active" else RED)
    if i["m"] is None:
        say(line + c(RED, "khong doc duoc /metrics: " + i["err"])); continue
    st = [h[2] for h in i["hosts"]]
    ok, wa, er = st.count(0), st.count(1), st.count(2)
    age = now - i["last"] if i["last"] else None
    stale = age is None or age > i["interval"] * 3 + 300
    vals = [len(st), ok, wa, er, i["disks"], len(i["dbad"]), len(i["nicdown"])]
    tot = [a + b for a, b in zip(tot, vals)]
    say(line + cell(i["ver"] or "CU-can cap nhat", 15, None if i["ver"] else RED)
        + cell(len(st), 6, right=True) + cell(ok, 5, GRN, True) + cell(wa, 6, YEL if wa else None, True)
        + cell(er, 7, RED if er else None, True) + cell(i["disks"], 6, right=True)
        + cell(len(i["dbad"]), 10, RED if i["dbad"] else None, True) + cell(len(i["nicdown"]), 10, RED if i["nicdown"] else None, True)
        + "  " + c(RED if stale else GRN, ago(age) if age is not None else "chua co du lieu"))
say(c(DIM, "-" * W))
say(cell("TONG", 42) + cell(tot[0], 6, right=True) + cell(tot[1], 5, GRN, True) + cell(tot[2], 6, YEL if tot[2] else None, True)
    + cell(tot[3], 7, RED if tot[3] else None, True) + cell(tot[4], 6, right=True)
    + cell(tot[5], 10, RED if tot[5] else None, True) + cell(tot[6], 10, RED if tot[6] else None, True))

# ---- chi tiet tung instance
K = lambda k: c(CYN, k.ljust(13) + ": ")
for i in infos:
    say(); say(c(BLD, ("== %s " % i["name"]).ljust(W, "=")))
    run = "chay tu %s (%s)" % (time.strftime("%d/%m %H:%M", time.localtime(i["since"])), dur(now - i["since"])) if i["since"] and i["svc"] == "active" else ""
    say(K("Service") + c(GRN if i["svc"] == "active" else RED, i["svc"]) + "  esxi-host-exporter@%s  port %s  %s" % (i["name"], i["port"], run))
    say(K("vCenter") + "%s  |  user %s  |  cluster: %s  |  chu ky %ss" % (i["vc"] or "?", i["user"] or "?", i["cluster"] if i["cluster"] not in ("", "-") else "tat ca", i["interval"]))
    if i["m"] is None:
        say(K("Loi") + c(RED, i["err"] or "khong doc duoc /metrics"))
        say(K("Log cuoi") + (i["lastlog"] or "-"))
        say(K("Xu ly") + "menu 2 (xem log), menu 3 (restart); sai mat khau -> menu 8"); continue
    say(K("Phien ban") + (i["ver"] if i["ver"] else c(RED, "CU - khong co build_info -> cap nhat: menu 6 (zip) hoac 13 (GitHub)"))
        + ("" if not i["ver"] or not inst_ver or i["ver"] == inst_ver else c(YEL, "  (khac ban trong /opt %s -> restart: menu 4)" % inst_ver)))
    if i["last"]:
        age = now - i["last"]; stale = age > i["interval"] * 3 + 300
        say(K("Du lieu") + "lan cuoi %s  " % time.strftime("%H:%M:%S", time.localtime(i["last"]))
            + c(RED if stale else GRN, "(%s)" % ago(age)) + ("  exporter UP" if i["up"] else c(RED, "  lan lay gan nhat LOI")))
    else:
        say(K("Du lieu") + c(YEL, "chua co (dang lay lan dau, cho 1-4 phut)"))
    cl = {}
    for h in i["hosts"]: cl[h[0]] = cl.get(h[0], 0) + 1
    say(K("Cluster") + (", ".join("%s (%d host)" % kv for kv in sorted(cl.items())) or "-"))
    st = [h[2] for h in i["hosts"]]
    say(K("Host") + "%d tong  |  " % len(st) + c(GRN, "%d OK" % st.count(0)) + "  |  " + c(YEL if st.count(1) else None, "%d WARN" % st.count(1))
        + "  |  " + c(RED if st.count(2) else None, "%d ERROR" % st.count(2))
        + "  |  " + c(RED if i["discon"] else None, "%d mat ket noi" % i["discon"]) + "  |  %d maintenance" % i["maint"])
    say(K("Disk vSAN") + "%d tong  |  " % i["disks"] + c(RED if i["dbad"] else GRN, "%d khong green" % len(i["dbad"]))
        + ("  (%s)" % ", ".join("%s %s" % (l.get("host", "?"), l.get("disk", "")[:24]) for l in i["dbad"][:3]) if i["dbad"] else ""))
    say(K("vmnic DOWN") + (c(RED, ", ".join("%s %s" % x for x in i["nicdown"][:6]) + (" ..." if len(i["nicdown"]) > 6 else "")) if i["nicdown"] else c(GRN, "khong co")))
    say(K("vSAN resync") + (c(YEL, ", ".join("%s: %d object, %s" % (cn, o, gb(b)) for cn, o, b in i["resync"])) if i["resync"] else c(GRN, "khong co")))
    say(K("InfluxDB") + (i["influx"] if i["influx"] else c(DIM, "tat")))
    say(K("Web") + "http://%s:%s/" % (ip, i["port"]))
    say(K("Log cuoi") + (i["lastlog"] or "-"))
    bad = sorted((h for h in i["hosts"] if h[2]), key=lambda h: (-h[2], h[1]))
    if bad:
        say(c(CYN, "Host can xem".ljust(13) + ":"))
        for cl_, host, s, inf in bad[:20]:
            say("   " + cell("ERROR" if s == 2 else "WARN", 6, RED if s == 2 else YEL) + " " + cell(cl_, 14) + cell(host, 18)
                + (inf.get("reason") or c(DIM, "(ban cu: khong co ly do)"))[:W - 44])
        if len(bad) > 20: say("   ... va %d host khac (xem Grafana / dashboard web)" % (len(bad) - 20))
say()
say(c(DIM, "DU LIEU mau do = qua 3 chu ky chua co du lieu moi.  PHIEN BAN CU = server chua cap nhat (menu 6 / 13)."))
PY

status_all() {
  local n st since last
  for n in $(instances); do
    st=$(systemctl is-active "$SVC@$n" 2>/dev/null)
    since=$(date -d "$(systemctl show -p ActiveEnterTimestamp --value "$SVC@$n" 2>/dev/null)" +%s 2>/dev/null)
    last=$(journalctl -u "$SVC@$n" -n 50 --no-pager -o cat 2>/dev/null | grep -E 'OK:|LOI|that bai' | tail -1)
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$n" "$(port_of "$n")" "${st:-unknown}" "${since:-0}" \
      "$(val_of "$n" VC)" "$(val_of "$n" VC_USER)" "$(val_of "$n" CLUSTER)" "$(val_of "$n" INTERVAL)" \
      "$(val_of "$n" INFLUX_URL)" "${last//$'\t'/ }"
  done | python3 -c "$STATUS_PY" "$(my_ip)" "$(installed_ver)" "$(hostname)"
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
    # pyVmomi theo Python cua server: >= 3.10 -> vendor/, 3.8-3.9 -> vendor-py38/; kiem tra import truoc khi thay
    local VS="$T/esxi-host-exporter/vendor"
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || VS="$T/esxi-host-exporter/vendor-py38"
    if [ -d "$VS" ] && PYTHONPATH="$VS" python3 -c 'import pyVmomi, pyVim.connect; from pyVmomi import vim; vim.cluster.VsanVcClusterHealthSystem'; then
      rm -rf "$APP/vendor.old"; mv "$APP/vendor" "$APP/vendor.old" 2>/dev/null; cp -r "$VS" "$APP/vendor"
      chmod -R a+rX "$APP/vendor"; rm -rf "$APP/vendor.old"; echo "pyVmomi: $(basename "$VS") ($(python3 -V 2>&1))"
    else
      echo "${R}Goi zip khong co pyVmomi chay duoc voi $(python3 -V 2>&1) - dung lai, chua thay doi gi.${N}"; rm -rf "$T"; return
    fi
    install -m 644 "$T"/esxi-host-exporter/app/* "$APP/"
    install -m 755 "$T/esxi-host-exporter/menu.sh" "$APP/menu.sh" 2>/dev/null
    install -m 755 "$T/esxi-host-exporter/uninstall.sh" "$APP/uninstall.sh" 2>/dev/null
    for n in $(instances); do systemctl restart "$SVC@$n"; done
    sleep 3; for n in $(instances); do p=$(port_of "$n"); echo "  $n ($p): ${G}$(version_of_port "$p")${N}"; done
  fi
  rm -rf "$T"
}

REPO_NAME=monitor-grafana-vcenter-full-details-prometheus
find_src() {  # thu muc chua install.sh: goi zip da giai nen hoac repo git clone
  for c in /home/esxi-host-exporter /root/$REPO_NAME/deploy /home/*/$REPO_NAME/deploy /opt/$REPO_NAME/deploy; do
    [ -f "$c/install.sh" ] && { echo "$c"; return; }
  done
}

update_from_git() {
  local RP; RP=$(find_src); RP=${RP%/deploy}
  if [ -z "$RP" ] || [ ! -d "$RP/.git" ]; then
    read -r -p "Thu muc repo da git clone [/root/$REPO_NAME]: " RP; RP=${RP:-/root/$REPO_NAME}
  fi
  [ -d "$RP/.git" ] || { echo "${R}Chua clone: git clone https://github.com/fixnhanh-linux/$REPO_NAME.git${N}"; return; }
  echo "Ban dang cai : $(grep -m1 '^VERSION' "$APP/esxi_host_exporter.py" | cut -d'"' -f2)"
  git -C "$RP" pull --ff-only || { echo "${R}git pull loi${N}"; return; }
  local E="$RP/exporter"
  echo "Ban tren git : ${B}$(grep -m1 '^VERSION' "$E/esxi_host_exporter.py" | cut -d'"' -f2)${N}"
  read -r -p "Cai ban nay va restart tat ca instance? (y/N): " a
  [ "$a" = y ] || return
  install -m 644 "$E/esxi_host_exporter.py" "$E/vsan_disk_health.py" "$E/esxi_dashboard.html" "$E/dashboard_template.html" "$APP/"
  install -m 755 "$RP/deploy/menu.sh" "$APP/menu.sh"; install -m 755 "$RP/deploy/uninstall.sh" "$APP/uninstall.sh"
  for n in $(instances); do systemctl restart "$SVC@$n"; done
  sleep 3; for n in $(instances); do p=$(port_of "$n"); echo "  $n ($p): ${G}$(version_of_port "$p")${N}"; done
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
  Tu GitHub       : git clone https://github.com/fixnhanh-linux/$REPO_NAME.git && sudo bash $REPO_NAME/deploy/install.sh
  Cap nhat GitHub : cd $REPO_NAME && git pull  (hoac menu muc 13)
  Go 1 instance   : $APP/uninstall.sh pool18
EOF
}

[ "$(id -u)" -eq 0 ] || { echo "Can chay bang root: sudo esxi-menu"; exit 1; }

# ---- ve menu trong khung, can giua man hinh
BW=64                                   # be rong ben trong khung
W=$'\e[1m'; [ -t 1 ] || W=
rep() { local s; printf -v s '%*s' "$2" ''; printf '%s' "${s// /$1}"; }
setpad() { local w; w=$(stty size </dev/tty 2>/dev/null | cut -d" " -f2); [[ $w =~ ^[0-9]+$ ]] || w=${COLUMNS:-80}; w=$(( (w - BW - 2) / 2 )); [ $w -lt 0 ] && w=0; printf -v PADS '%*s' $w ''; }
bline() { printf '%s%s%s%s%s%s\n' "$PADS" "$B" "$1" "$(rep "$2" $BW)" "$3" "$N"; }
bcenter() {  # bcenter "chu khong dau" [mau]
  local t="${1:0:BW}" l r; l=$(( (BW - ${#t}) / 2 )); r=$(( BW - ${#t} - l ))
  printf '%s%s║%s%*s%s%s%s%*s%s║%s\n' "$PADS" "$B" "$N" $l '' "${2:-}" "$t" "$N" $r '' "$B" "$N"
}
brow() {     # brow "cot trai" "cot phai"; bat dau bang # = tieu de nhom
  local l="$1" r="$2" lc="" rc="" h=$(( BW / 2 - 1 ))
  [[ $l == '#'* ]] && { l=${l#\#}; lc=$Y; }; [[ $r == '#'* ]] && { r=${r#\#}; rc=$Y; }
  printf '%s%s║%s  %s%-*s%s%s%-*s%s%s║%s\n' "$PADS" "$B" "$N" "$lc" $h "$l" "$N" "$rc" $((BW - h - 2)) "$r" "$N" "$B" "$N"
}
draw_menu() {
  setpad
  local tot=0 act=0 n ac
  for n in $(instances); do tot=$((tot+1)); [ "$(systemctl is-active "$SVC@$n" 2>/dev/null)" = active ] && act=$((act+1)); done
  ac=$G; [ $act -lt $tot ] && ac=$R
  echo
  bline "╔" "═" "╗"
  bcenter "ESXi HOST EXPORTER  -  MENU QUAN LY" "$W"
  bcenter "$(hostname) ($(my_ip))   |   $(date '+%d/%m/%Y %H:%M')"
  bcenter "Ban cai: $(installed_ver)   |   Instance: $act/$tot dang chay" "$ac"
  bline "╠" "═" "╣"
  brow "#XEM TRANG THAI"           "#CAP NHAT PHIEN BAN"
  brow " 1) Trang thai chi tiet"   " 6) Tu file zip (+ sha256)"
  brow " 2) Xem log 1 instance"    "13) Tu GitHub (git pull)"
  brow " 5) Kiem tra phien ban"    ""
  brow "10) Cau hinh InfluxDB"     "#CAI DAT / CAU HINH"
  brow "12) Cac lenh hay dung"     " 7) Them vCenter / instance"
  brow ""                          " 8) Doi mat khau / cai lai"
  brow "#DIEU KHIEN"               " 9) Sua cau hinh .env"
  brow " 3) Restart 1 instance"    "11) Go 1 instance"
  brow " 4) Restart tat ca"        ""
  bline "╠" "═" "╣"
  bcenter "0) Thoat         (Ctrl+C khi xem log = quay lai menu)"
  bline "╚" "═" "╝"
}

while true; do
  clear 2>/dev/null
  draw_menu
  printf '%s' "$PADS"; read -r -p "Chon so: " c
  echo
  case "$c" in
    1) status_all; pause ;;
    2) if pick; then trap ':' INT; journalctl -u "$SVC@$PICK" -n 50 -f; trap - INT; fi ;;  # Ctrl+C chi thoat log
    3) pick && systemctl restart "$SVC@$PICK" && echo "${G}Da restart $PICK${N}"; pause ;;
    4) for n in $(instances); do systemctl restart "$SVC@$n" && echo "${G}Da restart $n${N}"; done; pause ;;
    5) printf "%-12s %-6s %s\n" INSTANCE PORT "PHIEN BAN DANG CHAY"
       for n in $(instances); do p=$(port_of "$n"); v=$(version_of_port "$p")
         printf "%-12s %-6s %s\n" "$n" "$p" "${v:-${R}CU / khong co build_info (chua cap nhat hoac chua chay)${N}}"; done
       echo; echo "Ban trong $APP: ${B}$(installed_ver)${N}  (khac ban dang chay -> restart: muc 4)"; pause ;;
    6) update_from_zip; pause ;;
    7|8) D=$(find_src)
       [ -n "$D" ] || read -r -p "Thu muc co install.sh (goi zip da giai nen hoac <repo>/deploy): " D
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
    13) update_from_git; pause ;;
    0|q|Q) exit 0 ;;
    *) ;;
  esac
done
