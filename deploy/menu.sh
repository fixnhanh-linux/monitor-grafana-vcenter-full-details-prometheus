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

# ---- muc 14: sinh cau hinh Prometheus tu cac instance dang cai, (tuy chon) cai vao Prometheus tren may nay
yaml_list() {  # yaml_list <file> <key>: cac dong "- xxx" ngay duoi key cap 1 (rule_files, scrape_config_files)
  awk -v k="$2:" '$1==k{f=1;next} f&&/^[^ \t#]/{f=0} f&&/^[ \t]*-/{sub(/^[ \t]*-[ \t]*/,""); gsub(/["\047]/,""); print}' "$1"
}
ask_yn() { local a; read -r -p "$1 (y/N): " a; [ "$a" = y ] || [ "$a" = Y ]; }

prom_config() {
  local ip out pc src rules n p vc dir f dst cfg_ok
  mapfile -t LIST < <(instances)
  [ ${#LIST[@]} -gt 0 ] || { echo "${Y}Chua co instance nao. Chon muc 7 de cai truoc.${N}"; return; }
  ip=$(my_ip); out="$CONF/prometheus-scrape-esxi.yml"
  {
    echo "# Sinh boi esxi-menu $(date '+%d/%m/%Y %H:%M') - exporter tren $(hostname) ($ip)"
    echo "# Dung cho scrape_config_files, hoac dan phan '- job_name ...' vao scrape_configs cua prometheus.yml"
    echo "scrape_configs:"
    echo "  - job_name: 'esxi_host_resource'"
    echo "    scrape_interval: 30s"
    echo "    scrape_timeout: 25s"
    echo "    static_configs:"
    for n in "${LIST[@]}"; do
      p=$(port_of "$n"); vc=$(val_of "$n" VC)
      echo "      - targets: ['$ip:$p']"
      echo "        labels: { pool: '$n', vcenter: '$vc' }"
    done
  } > "$out"
  chmod 644 "$out"
  echo "${B}== Cau hinh scrape (da luu: $out) ==${N}"; cat "$out"

  # alert rule: lay tu bo cai (goi zip hoac repo git clone)
  src=$(find_src); rules=""
  for f in "$src/alert-rules-esxi.yml" "$src/../prometheus/alert-rules-esxi.yml"; do [ -f "$f" ] && { rules=$(readlink -f "$f"); break; }; done
  echo; echo "${B}== Alert rule ==${N}"; echo "  ${rules:-khong thay alert-rules-esxi.yml (giai nen goi zip / git clone truoc)}"

  # Prometheus tren may nay?
  pc=$(systemctl cat prometheus 2>/dev/null | grep -o -- '--config.file[= ][^ ]*' | head -1 | sed 's/--config.file[= ]//')
  pc=${pc:-/etc/prometheus/prometheus.yml}
  echo
  if [ ! -f "$pc" ]; then
    echo "${Y}May nay khong co Prometheus ($pc). Chep file tren sang may Prometheus:${N}"
    echo "  scp $out <may-prometheus>:/etc/prometheus/scrape_configs/esxi-host-resource.yml"
    [ -n "$rules" ] && echo "  scp $rules <may-prometheus>:/etc/prometheus/rules/"
    echo "  roi tren may do: promtool check config /etc/prometheus/prometheus.yml && systemctl reload prometheus"
    return
  fi
  echo "${B}== Prometheus tren may nay: $pc ==${N}"
  cfg_ok=1
  if grep -rqs "esxi_host_resource" "$pc"; then
    echo "${Y}prometheus.yml da co job esxi_host_resource -> sua truc tiep trong $pc (khong tao them de tranh trung job).${N}"; cfg_ok=0
  fi
  local sdirs rdirs; sdirs=$(yaml_list "$pc" scrape_config_files); rdirs=$(yaml_list "$pc" rule_files)
  echo "  scrape_config_files: ${sdirs:-(khong dung)}"
  echo "  rule_files         : ${rdirs:-(chua khai bao)}"
  local copied=()
  if [ $cfg_ok = 1 ]; then
    if [ -n "$sdirs" ]; then
      dir=$(dirname "$(head -1 <<<"$sdirs")"); dst="$dir/esxi-host-resource.yml"
      for f in "$dir"/*; do [ -f "$f" ] && [ "$f" != "$dst" ] && grep -qs "esxi_host_resource" "$f" && { echo "${Y}  $f da co job esxi_host_resource -> bo qua, sua file do.${N}"; cfg_ok=0; }; done
      if [ $cfg_ok = 1 ] && ask_yn "Chep cau hinh scrape vao $dst ?"; then
        mkdir -p "$dir"; [ -f "$dst" ] && cp "$dst" "$dst.bak"; install -m 644 "$out" "$dst"; copied+=("$dst"); echo "${G}  Da chep $dst${N}"
      fi
    else
      echo "${Y}  prometheus.yml khong dung scrape_config_files: dan phan tu dong '- job_name' o tren vao muc scrape_configs cua $pc${N}"
      echo "  (hoac them vao $pc:  scrape_config_files: [ '$(dirname "$pc")/scrape_configs/*.yml' ]  roi chay lai muc 14)"
    fi
  fi
  if [ -n "$rules" ]; then
    local rd; rd=$(head -1 <<<"$rdirs")
    if [[ "$rd" == *'*'* ]]; then
      dst="$(dirname "$rd")/alert-rules-esxi.yml"
      if ask_yn "Chep alert rule vao $dst ?"; then
        mkdir -p "$(dirname "$dst")"; [ -f "$dst" ] && cp "$dst" "$dst.bak"; install -m 644 "$rules" "$dst"; copied+=("$dst"); echo "${G}  Da chep $dst${N}"
      fi
    else
      echo "${Y}  Them vao $pc:  rule_files: [ '$(dirname "$pc")/rules/*.yml' ]  roi chep $rules vao $(dirname "$pc")/rules/${N}"
    fi
  fi
  [ ${#copied[@]} -gt 0 ] || return
  echo
  if command -v promtool >/dev/null; then
    if ! promtool check config "$pc"; then
      echo "${R}promtool bao loi -> hoan tac file vua chep.${N}"
      for f in "${copied[@]}"; do if [ -f "$f.bak" ]; then mv "$f.bak" "$f"; else rm -f "$f"; fi; done
      return
    fi
  else echo "${Y}Khong co promtool - bo qua buoc kiem tra cu phap.${N}"; fi
  for f in "${copied[@]}"; do rm -f "$f.bak"; done
  if ask_yn "Reload Prometheus de ap dung?"; then
    systemctl reload prometheus 2>/dev/null || curl -s -X POST localhost:9090/-/reload || systemctl restart prometheus
    sleep 5
    echo "Target job esxi_host_resource:"
    curl -s -m 5 localhost:9090/api/v1/targets | python3 -c '
import json, sys
try: t = json.load(sys.stdin)["data"]["activeTargets"]
except Exception: print("  khong doc duoc API Prometheus localhost:9090"); sys.exit()
rows = [x for x in t if x.get("labels", {}).get("job") == "esxi_host_resource"]
for x in rows: print("  %-22s %-8s %s" % (x["scrapeUrl"].split("/")[2], x["health"], x.get("lastError", "")))
if not rows: print("  chua thay (doi 30s roi xem lai: Status -> Targets)")'
  fi
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
M=$'\e[35m'; BL=$'\e[94m'; D=$'\e[2m'; RV=$'\e[7m'; [ -t 1 ] || { M=; BL=; D=; RV=; }
bcenter() {  # bcenter "chu khong dau" [mau]
  local t="${1:0:BW}" l r; l=$(( (BW - ${#t}) / 2 )); r=$(( BW - ${#t} - l ))
  printf '%s%s║%s%*s%s%s%s%*s%s║%s\n' "$PADS" "$B" "$N" $l '' "${2:-}" "$t" "$N" $r '' "$B" "$N"
}
bfree() {    # bfree "chu co mau" [do dai hien thi]: 1 dong trong khung, can trai
  set -- "$1" "${2:-$(sed 's/\x1b\[[0-9;]*m//g' <<<"$1" | wc -m | awk '{print $1-1}')}"
  printf '%s%s║%s  %s%*s%s║%s\n' "$PADS" "$B" "$N" "$1" $(( BW - 2 - $2 )) '' "$B" "$N"
}
cell() {     # cell <spec> <rong> -> CELL; spec: "H|mau|TIEU DE" | "I|mau|so|chu" | ""
  local IFS='|' k col a t plain; read -r k col a t <<<"$1"
  case "$k" in
    H) plain=" $a "; CELL="${!col}${RV}${W}${plain}${N}" ;;
    I) printf -v plain '%3s) %s' "$a" "$t"; CELL="${!col}${W}$(printf '%3s)' "$a")${N} $t" ;;
    *) plain=""; CELL="" ;;
  esac
  CELL+=$(printf '%*s' $(( $2 - ${#plain} )) '')
}
brow() {     # brow <spec trai> <spec phai>
  local h=$(( BW / 2 - 1 )) L
  cell "$1" $h; L=$CELL; cell "$2" $(( BW - h - 2 ))
  printf '%s%s║%s  %s%s%s║%s\n' "$PADS" "$B" "$N" "$L" "$CELL" "$B" "$N"
}
draw_menu() {
  setpad
  local tot=0 act=0 n p st ac line plain item
  local -a ok_list
  for n in $(instances); do
    tot=$((tot+1)); st=$(systemctl is-active "$SVC@$n" 2>/dev/null)
    [ "$st" = active ] && act=$((act+1))
    ok_list+=("$n|$(port_of "$n")|$st")
  done
  ac=$G; [ $act -lt $tot ] && ac=$R; [ $tot -eq 0 ] && ac=$Y
  echo
  bline "╔" "═" "╗"
  bcenter "E S X i   H O S T   E X P O R T E R" "$W$Y"
  bcenter "Menu quan ly  -  vCenter / vSAN monitoring" "$D"
  bline "╟" "─" "╢"
  bcenter "May: $(hostname) ($(my_ip))   |   $(date '+%d/%m/%Y %H:%M')" "$BL"
  bcenter "Ban cai: $(installed_ver)   |   Instance dang chay: $act/$tot" "$ac"
  # dai trang thai tung instance: ten:port UP (xanh) / DOWN (do), tu xuong dong
  if [ $tot -gt 0 ]; then
    line=""; plain=""
    for item in "${ok_list[@]}"; do
      IFS='|' read -r n p st <<<"$item"
      local tag="UP" col=$G; [ "$st" = active ] || { tag="DOWN"; col=$R; }
      local seg="$n:$p $tag"
      if [ $(( ${#plain} + ${#seg} + 3 )) -gt $(( BW - 4 )) ]; then bfree "$line" ${#plain}; line=""; plain=""; fi
      line+="${col}●${N} ${W}$n${N}${D}:$p${N} ${col}$tag${N}   "; plain+="* $seg   "
    done
    bfree "$line" ${#plain}
  else
    bcenter "Chua co instance nao -> chon 7 de them vCenter" "$Y"
  fi
  bline "╠" "═" "╣"
  brow "H|G|XEM TRANG THAI"            "H|BL|CAI DAT / CAU HINH"
  brow "I|G|1|Trang thai chi tiet"     "I|BL|7|Them vCenter / instance"
  brow "I|G|2|Xem log 1 instance"      "I|BL|8|Doi mat khau / cai lai"
  brow "I|G|5|Kiem tra phien ban"      "I|BL|9|Sua cau hinh .env"
  brow ""                              "I|BL|11|Go 1 instance"
  brow "H|Y|DIEU KHIEN"                ""
  brow "I|Y|3|Restart 1 instance"      "H|M|CAP NHAT PHIEN BAN"
  brow "I|Y|4|Restart tat ca"          "I|M|6|Tu file zip (+ sha256)"
  brow ""                              "I|M|13|Tu GitHub (git pull)"
  brow "H|B|TICH HOP"                  ""
  brow "I|B|14|Cau hinh Prometheus"    "H|D|TRO GIUP"
  brow "I|B|10|Cau hinh InfluxDB"      "I|D|12|Cac lenh hay dung"
  bline "╠" "═" "╣"
  bfree "${R}${W}  0)${N} Thoat        ${D}Ctrl+C khi xem log = quay lai menu${N}"
  bline "╚" "═" "╝"
}

while true; do
  clear 2>/dev/null
  draw_menu
  printf '%s' "$PADS"; read -r -p "${W}${Y}Chon so (0-14):${N} " c
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
         echo "Bo cai dung: ${B}$D${N}  (phien ban $(cat "$D/VERSION" 2>/dev/null || grep -m1 '^VERSION' "$D/../exporter/esxi_host_exporter.py" 2>/dev/null | cut -d'"' -f2))"
         if [ -d "$D/vendor" ] && [ ! -d "$D/vendor-py38" ] && ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
           echo "${R}Goi zip cu: chi co pyVmomi cho Python >= 3.10, server dang $(python3 -V 2>&1).${N}"
           echo "${Y}Chep goi zip moi (co vendor-py38/) vao /home roi: cd /home && unzip -o esxi-host-exporter-linux.zip${N}"
           pause; continue
         fi
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
    14) prom_config; pause ;;
    0|q|Q) exit 0 ;;
    *) ;;
  esac
done
