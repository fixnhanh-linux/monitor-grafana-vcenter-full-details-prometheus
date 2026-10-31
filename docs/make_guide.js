const d = require("docx");
const { Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, BorderStyle, ShadingType, AlignmentType, TableOfContents, PageBreak, LevelFormat } = d;
const fs = require("fs");

const MONO = "Consolas";
const ACC = "1F4E79", GREY = "F2F3F5", LINE = "C9D1D9";

function H1(t){return new Paragraph({heading:HeadingLevel.HEADING_1, spacing:{before:260,after:120}, children:[new TextRun({text:t,bold:true,color:ACC})]});}
function H2(t){return new Paragraph({heading:HeadingLevel.HEADING_2, spacing:{before:180,after:80}, children:[new TextRun({text:t,bold:true})]});}
function P(t,o){o=o||{};return new Paragraph({spacing:{after:o.after==null?90:o.after}, children:[new TextRun({text:t,bold:o.bold,italics:o.italics,color:o.color})]});}
function runs(arr){return new Paragraph({spacing:{after:90}, children:arr.map(x=>Array.isArray(x)?new TextRun({text:x[0],font:MONO,size:19,color:"103D63",shading:{type:ShadingType.CLEAR,fill:"EAF2FB"}}):new TextRun({text:x}))});}
function bullet(t){return new Paragraph({numbering:{reference:"bl",level:0}, spacing:{after:60}, children:[new TextRun(t)]});}
function num(t){return new Paragraph({numbering:{reference:"nm",level:0}, spacing:{after:60}, children:[new TextRun(t)]});}
function code(lines){
  return lines.map((ln,i)=>new Paragraph({
    spacing:{after: i===lines.length-1?150:0, before:i===0?60:0, line:252},
    shading:{type:ShadingType.CLEAR,fill:"EAF2FB"},
    border:{
      left:{style:BorderStyle.SINGLE,size:24,color:"2F6FB3",space:10},
      top:    i===0 ? {style:BorderStyle.SINGLE,size:6,color:"C9DDF2",space:3} : undefined,
      bottom: i===lines.length-1 ? {style:BorderStyle.SINGLE,size:6,color:"C9DDF2",space:3} : undefined,
      right:{style:BorderStyle.SINGLE,size:6,color:"C9DDF2",space:3}},
    children:[new TextRun({text:ln||" ",font:MONO,size:18,color:"103D63"})]}));
}
function cell(text,{w,bold,fill,mono,color}={}){
  return new TableCell({width:{size:w,type:WidthType.DXA}, shading:fill?{type:ShadingType.CLEAR,fill}:undefined,
    margins:{top:40,bottom:40,left:80,right:80},
    children:[new Paragraph({children:[new TextRun({text:text,bold,font:mono?MONO:undefined,size:mono?18:20,color})]})]});
}
function table(cols, rows){
  const total = cols.reduce((a,b)=>a+b.w,0);
  const head = new TableRow({tableHeader:true, children:cols.map(c=>cell(c.t,{w:c.w,bold:true,fill:ACC,color:"FFFFFF"}))});
  const body = rows.map(r=>new TableRow({children:r.map((txt,i)=>cell(txt,{w:cols[i].w,mono:cols[i].mono}))}));
  return new Table({columnWidths:cols.map(c=>c.w), width:{size:total,type:WidthType.DXA},
    borders:{top:{style:BorderStyle.SINGLE,size:4,color:LINE},bottom:{style:BorderStyle.SINGLE,size:4,color:LINE},
      left:{style:BorderStyle.SINGLE,size:4,color:LINE},right:{style:BorderStyle.SINGLE,size:4,color:LINE},
      insideHorizontal:{style:BorderStyle.SINGLE,size:4,color:LINE},insideVertical:{style:BorderStyle.SINGLE,size:4,color:LINE}},
    rows:[head,...body]});
}
const SP = ()=>new Paragraph({spacing:{after:80},children:[]});

const children = [];
// Bia
children.push(new Paragraph({alignment:AlignmentType.CENTER, spacing:{before:1600,after:60},
  children:[new TextRun({text:"HƯỚNG DẪN CÀI ĐẶT & VẬN HÀNH",bold:true,size:44,color:ACC})]}));
children.push(new Paragraph({alignment:AlignmentType.CENTER, spacing:{after:40},
  children:[new TextRun({text:"ESXi Host Exporter — Monitor Resource Host ESXi + vSAN",bold:true,size:30})]}));
children.push(new Paragraph({alignment:AlignmentType.CENTER, spacing:{after:40},
  children:[new TextRun({text:"Prometheus · Grafana · Cảnh báo",size:24,color:"666666"})]}));
children.push(new Paragraph({alignment:AlignmentType.CENTER, spacing:{before:400},
  children:[new TextRun({text:"Phiên bản 2026.10.31  ·  Cài tự động và thủ công",italics:true,size:22})]}));
children.push(new Paragraph({children:[new PageBreak()]}));

// Muc luc
children.push(new Paragraph({heading:HeadingLevel.HEADING_1,spacing:{after:120},children:[new TextRun({text:"Mục lục",bold:true,color:ACC})]}));
children.push(new TableOfContents("Mục lục",{hyperlink:true,headingStyleRange:"1-2"}));
children.push(new Paragraph({children:[new PageBreak()]}));

// 1. Gioi thieu
children.push(H1("1. Giới thiệu"));
children.push(P("Phần mềm là một exporter viết bằng Python: kết nối tới vCenter (chỉ đọc), lấy số liệu từng host ESXi và vSAN rồi xuất ra cho Prometheus, kèm một dashboard web có sẵn. Có thể cài nhiều instance trên một server, mỗi vCenter một instance và một cổng riêng."));
children.push(P("Luồng dữ liệu:", {bold:true, after:40}));
children.push(bullet("vCenter  →  esxi_host_exporter (systemd, cổng 9811…)  →  Prometheus  →  Grafana"));
children.push(bullet("Prometheus  →  Alertmanager (alert rule)  →  Element/Matrix"));
children.push(bullet("Dashboard web có sẵn tại http://<IP-server>:<port>/"));

children.push(H1("2. Yêu cầu"));
children.push(bullet("vCenter: tạo user (vd monitor@vsphere.local), cấp role Read-only ở cấp vCenter, tick Propagate to children. Bật vSAN Performance Service trên cluster để có số liệu latency."));
children.push(bullet("Server Linux: có systemd, Python ≥ 3.8, tới được vCenter cổng 443."));
children.push(bullet("Kiểm tra kết nối:"));
children.push(...code(['curl -k -s -o /dev/null -w "%{http_code}\\n" https://<IP-vCenter>/sdk/vsanServiceVersions.xml']));
children.push(P("Kết quả 200 là đạt. pyVmomi: Python ≥ 3.10 dùng pyVmomi 9.x; Python 3.8/3.9 dùng pyVmomi 8.0.3 (gói zip kèm sẵn cả hai, install.sh tự chọn)."));

// ============ A. TU DONG
children.push(H1("3. PHẦN A — CÀI ĐẶT TỰ ĐỘNG (khuyến nghị)"));
children.push(P("Dùng script install.sh. Chọn một trong hai cách lấy mã nguồn.", {italics:true}));

children.push(H2("A1. Cách 1 — gói zip (không cần internet, pyVmomi kèm sẵn)"));
children.push(num("Trên máy có Python + pyVmomi, tạo gói:"));
children.push(...code(["python deploy/build_zip.py        # -> esxi-host-exporter-linux.zip + .sha256"]));
children.push(num("Chép 2 file (.zip và .sha256) lên server, vào /home."));
children.push(num("Trên server, kiểm tra và cài:"));
children.push(...code([
  "cd /home && sha256sum -c esxi-host-exporter-linux.zip.sha256   # phai la OK",
  "unzip -o esxi-host-exporter-linux.zip",
  "cd esxi-host-exporter && sudo bash install.sh"]));

children.push(H2("A2. Cách 2 — git clone (server có internet, tự tải pyVmomi)"));
children.push(...code([
  "cd /root",
  "git clone https://github.com/fixnhanh-linux/monitor-grafana-vcenter-full-details-prometheus.git",
  "cd monitor-grafana-vcenter-full-details-prometheus",
  "sudo bash deploy/install.sh"]));
children.push(P("Thiếu pip: apt install python3-pip (Ubuntu/Debian) hoặc dnf install python3-pip (RHEL)."));

children.push(H2("A3. Các thông tin install.sh sẽ hỏi"));
children.push(table(
  [{t:"Mục",w:2600},{t:"Ý nghĩa",w:4200,}, {t:"Ví dụ",w:2000,mono:true}],
  [["Tên instance","Tên gợi nhớ (chữ/số/-), mỗi vCenter một tên","pool18"],
   ["IP/hostname vCenter","Địa chỉ vCenter","10.0.0.10"],
   ["User vCenter","Tài khoản Read-only","monitor@vsphere.local"],
   ["Cluster","- = tất cả cluster","-"],
   ["Port","Cổng dashboard/metrics","9811"],
   ["Chu kỳ (giây)","Bao lâu lấy dữ liệu một lần","60"],
   ["Mật khẩu vCenter","Gõ ẩn, lưu ở file .env quyền 600",""]]));
children.push(SP());
children.push(P("Sau khi cài: mật khẩu ở /etc/esxi-host-exporter/<instance>.env (quyền 600), chạy dưới user hệ thống esxi-exporter. Sai mật khẩu → service dừng hẳn (không thử lại, tránh khóa tài khoản). Dashboard web: http://<IP-server>:9811/."));

children.push(H2("A4. Quản lý bằng lệnh esxi-menu"));
children.push(P("Quên lệnh thì gõ (cần root):"));
children.push(...code(["sudo esxi-menu"]));
children.push(table(
  [{t:"Mục",w:900},{t:"Chức năng",w:7900}],
  [["1","Trạng thái chi tiết tất cả instance (host OK/WARN/ERROR, disk, resync, phiên bản)"],
   ["2","Xem log 1 instance (Ctrl+C để quay lại menu)"],
   ["3","Restart 1 instance"],
   ["4","Restart tất cả instance"],
   ["5","Kiểm tra phiên bản đang chạy"],
   ["6","Cập nhật bản mới từ file zip (kiểm tra sha256)"],
   ["7","Thêm vCenter / instance mới"],
   ["8","Đổi mật khẩu / cài lại 1 instance"],
   ["9","Sửa cấu hình .env 1 instance"],
   ["10","Xem cấu hình InfluxDB"],
   ["11","Gỡ 1 instance"],
   ["12","Các lệnh hay dùng"],
   ["13","Cập nhật bản mới từ GitHub (git pull)"],
   ["14","Sinh / cài cấu hình Prometheus từ các instance đã cài"],
   ["15","Phát hiện cluster — liệt kê cluster/vSAN/DRS, đánh dấu cluster chưa giám sát"]]));

// ============ B. THU CONG
children.push(new Paragraph({children:[new PageBreak()]}));
children.push(H1("4. PHẦN B — CÀI ĐẶT THỦ CÔNG (từng bước bằng tay)"));
children.push(P("Dùng khi không chạy install.sh, hoặc muốn hiểu script làm gì. Chạy bằng root.", {italics:true}));

children.push(H2("B1. Tạo user hệ thống"));
children.push(...code(["useradd --system --no-create-home --shell /usr/sbin/nologin esxi-exporter"]));

children.push(H2("B2. Chép mã nguồn và cài thư viện pyVmomi"));
children.push(...code([
  "mkdir -p /opt/esxi-host-exporter",
  "# chep 4 file tu thu muc exporter/ (hoac app/ trong goi zip):",
  "install -m 644 esxi_host_exporter.py vsan_disk_health.py \\",
  "        esxi_dashboard.html dashboard_template.html /opt/esxi-host-exporter/",
  "",
  "# pyVmomi: Python >= 3.10",
  "python3 -m pip install --target /opt/esxi-host-exporter/vendor \"pyvmomi>=8.0.2\"",
  "# Python 3.8/3.9 thi dung:  \"pyvmomi>=8.0.2,<9\"",
  "# (hoac chep san thu muc vendor/ tu goi zip neu khong co internet)",
  "",
  "chmod -R a+rX /opt/esxi-host-exporter"]));
children.push(P("Kiểm tra pyVmomi nạp được:"));
children.push(...code(["PYTHONPATH=/opt/esxi-host-exporter/vendor python3 -c \\",
  "  'import pyVmomi, pyVim.connect; from pyVmomi import vim; vim.cluster.VsanVcClusterHealthSystem'"]));

children.push(H2("B3. Tạo file cấu hình instance"));
children.push(P("Mỗi instance một file .env, quyền 600, thuộc root:"));
children.push(...code([
  "mkdir -p /etc/esxi-host-exporter",
  "cat > /etc/esxi-host-exporter/pool18.env <<'EOF'",
  "VC='10.0.0.10'",
  "VC_USER='monitor@vsphere.local'",
  "CLUSTER='-'",
  "PORT=9811",
  "INTERVAL=60",
  "VSAN_PASS='mat_khau_vcenter'",
  "# Tuy chon - bo dau # de doi nguong canh bao:",
  "#ESXI_WARN_CPU=60",
  "#ESXI_WARN_RAM=90",
  "#ESXI_WARN_LATENCY_MS=15",
  "#ESXI_NIC_MIN_MBPS=10000",
  "EOF",
  "chmod 600 /etc/esxi-host-exporter/pool18.env"]));

children.push(H2("B4. Tạo systemd unit (dạng template)"));
children.push(...code([
  "cat > /etc/systemd/system/esxi-host-exporter@.service <<'EOF'",
  "[Unit]",
  "Description=ESXi host + vSAN exporter (%i)",
  "After=network-online.target",
  "Wants=network-online.target",
  "",
  "[Service]",
  "EnvironmentFile=/etc/esxi-host-exporter/%i.env",
  "Environment=PYTHONPATH=/opt/esxi-host-exporter/vendor",
  "Environment=PYTHONDONTWRITEBYTECODE=1",
  "ExecStart=/usr/bin/env python3 /opt/esxi-host-exporter/esxi_host_exporter.py \\",
  "          ${VC} ${VC_USER} ${CLUSTER} ${PORT} ${INTERVAL}",
  "User=esxi-exporter",
  "Group=esxi-exporter",
  "Restart=always",
  "RestartSec=30",
  "RestartPreventExitStatus=3",
  "NoNewPrivileges=true",
  "ProtectSystem=strict",
  "ProtectHome=true",
  "PrivateTmp=true",
  "",
  "[Install]",
  "WantedBy=multi-user.target",
  "EOF"]));
children.push(P("Ghi chú: %i là tên instance. RestartPreventExitStatus=3 nghĩa là khi sai mật khẩu (mã thoát 3) thì systemd không thử lại, tránh khóa tài khoản vCenter."));

children.push(H2("B5. Khởi động và kiểm tra"));
children.push(...code([
  "systemctl daemon-reload",
  "systemctl enable --now esxi-host-exporter@pool18",
  "systemctl status esxi-host-exporter@pool18    # phai Active: active (running)",
  "journalctl -u esxi-host-exporter@pool18 -f    # xem log, cho dong 'OK: N host'",
  "curl -s localhost:9811/metrics | head         # co metric la chay"]));
children.push(P("Thêm instance thứ hai: lặp lại B3 với file .env khác (tên + PORT khác) rồi enable --now instance đó. Chạy thử không cần service:"));
children.push(...code(['VSAN_PASS=\'...\' python3 /opt/esxi-host-exporter/esxi_host_exporter.py 10.0.0.10 monitor@vsphere.local - 9811 60']));

// ============ Prometheus
children.push(new Paragraph({children:[new PageBreak()]}));
children.push(H1("5. Prometheus"));
children.push(H2("5.1. Tự động (khuyến nghị)"));
children.push(P("Trên server exporter, chạy esxi-menu → mục 14. Nó sinh cấu hình scrape từ các instance đã cài; nếu Prometheus cùng máy sẽ hỏi chép vào scrape_configs/ và rules/, chạy promtool check rồi reload."));
children.push(H2("5.2. Thủ công"));
children.push(num("Chép prometheus/scrape-esxi-host-resource.yml vào /etc/prometheus/scrape_configs/ (hoặc dán phần job vào scrape_configs của prometheus.yml). Sửa <IP-server>, port, nhãn pool."));
children.push(num("Chép prometheus/alert-rules-esxi.yml vào thư mục khai báo ở rule_files."));
children.push(num("Kiểm tra và reload:"));
children.push(...code(["promtool check config /etc/prometheus/prometheus.yml && systemctl reload prometheus"]));
children.push(P("Vào Status → Targets, job esxi_host_resource phải UP."));
children.push(SP());
children.push(P("Bảng cảnh báo (alert rule):", {bold:true, after:40}));
children.push(table(
  [{t:"Tình huống",w:4400},{t:"Rule",w:3000,mono:true},{t:"Severity",w:1400}],
  [["vmnic down","EsxiVmnicDown","critical"],
   ["Disk vSAN lỗi","VsanDiskError","error"],
   ["DiskGroup vSAN Unhealthy","VsanDiskGroupUnhealthy","unhealthy"],
   ["Host mất kết nối","EsxiHostDisconnected","critical"],
   ["vSAN resync > 0","VsanResyncInProgress","warning"],
   ["CPU > 60% / RAM > 90%","EsxiCpuHigh / EsxiRamHigh","warning"],
   ["vSAN write latency > 15ms","VsanWriteLatencyHigh","warning"],
   ["vSAN congestion > 60","VsanCongestion","warning"],
   ["Drop vmk vSAN > 0,1%","VsanVmkPacketDrop","warning"],
   ["Exporter mất dữ liệu / tắt","EsxiExporterStale / Down","warning"]]));

// ============ Grafana
children.push(H1("6. Grafana"));
children.push(P("Import dashboard: Dashboards → New → Import → Upload JSON → chọn file grafana/esxi_host_resource_grafana.json → chọn datasource Prometheus → Overwrite nếu đã có bản cũ. Chọn Cluster ở đầu trang."));
children.push(P("Ví dụ dashboard đang chạy:", {bold:true, after:40}));
children.push(...code(["https://42.117.4.233:3000/d/esxi-host-resource/"]));
children.push(bullet("Tổng quan (8 ô): Total Hosts · OK · Warning (WARN) · Error (ERROR) · Hosts In Maintenance · Network Latency Max · vSAN Resync · Data Freshness."));
children.push(bullet("Bảng host: CPU% · RAM% · NIC UP (xanh) / NIC DOWN (đỏ) · DiskGroup vSAN · congestion · write latency · VMs · Uptime · Status · Alerts. Bấm tên host để lọc phần chi tiết."));
children.push(bullet("Network: bandwidth vmnic TX/RX top 10, drop/discard vmk vSAN."));
children.push(bullet("Chi tiết host (top 10 host): CPU, RAM, vSAN write / read / network latency — mỗi loại một biểu đồ riêng."));
children.push(bullet("vSAN Disk Health: congestion, dung lượng, health từng disk."));

// ============ Zabbix
children.push(H1("7. Zabbix (tùy chọn — thay / cùng Prometheus)"));
children.push(P("Zabbix lấy thẳng /metrics của exporter bằng HTTP agent rồi tự phát hiện cluster/host/disk/nic/vmk (LLD) và tạo item + trigger + graph."));
children.push(num("Data collection → Templates → Import → chọn zabbix/esxi_vsan_command_center.yaml (Zabbix 6.2)."));
children.push(num("Tạo 1 host Zabbix cho mỗi instance exporter, gán template ESXi Host Exporter by HTTP."));
children.push(num("Sửa macro trên host:"));
children.push(table(
  [{t:"Macro",w:3400,mono:true},{t:"Giá trị",w:5400,mono:true}],
  [["{$ESXI.EXPORTER.URL}","http://<IP-server>:<port>/metrics"],
   ["{$ESXI.CLUSTER.MATCHES}",".*   (regex lọc cluster, vd ^POOL18-XD$)"],
   ["{$ESXI.HOST.MATCHES}",".*   (regex lọc host)"]]));
children.push(P("Có sẵn dashboard 3 trang (Hosts / vSAN / Network) trong template. Mức 2 = High, Mức 3 = Warning; ngưỡng đổi bằng macro {$ESXI.*} trên host/template, không cần sửa trigger."));

// ============ Van hanh
children.push(new Paragraph({children:[new PageBreak()]}));
children.push(H1("8. Vận hành & cập nhật"));
children.push(table(
  [{t:"Việc",w:3200},{t:"Lệnh / cách làm",w:5600,mono:true}],
  [["Trạng thái","systemctl status esxi-host-exporter@pool18"],
   ["Log trực tiếp","journalctl -u esxi-host-exporter@pool18 -f"],
   ["Restart","systemctl restart esxi-host-exporter@pool18"],
   ["Restart tất cả","systemctl restart 'esxi-host-exporter@*'"],
   ["Phiên bản đang chạy","curl -s localhost:9811/metrics | grep build_info"],
   ["Cập nhật từ zip","esxi-menu → 6"],
   ["Cập nhật từ GitHub","esxi-menu → 13   (hoặc: cd <repo> && git pull)"],
   ["Đổi mật khẩu","esxi-menu → 8"],
   ["Gỡ 1 instance","/opt/esxi-host-exporter/uninstall.sh pool18"]]));

// ============ Su co
children.push(H1("9. Xử lý sự cố"));
children.push(table(
  [{t:"Hiện tượng",w:3400},{t:"Nguyên nhân / cách xử lý",w:5400}],
  [["Service active nhưng không restart được, log 'Dang nhap that bai'","Sai user/mật khẩu vCenter. Sửa esxi-menu → 8 rồi restart."],
   ["Log 'Python 3.10 or newer is required'","Gói pyVmomi 9.x chạy trên Python 3.8. Dùng gói zip có vendor-py38, hoặc pip cài 'pyvmomi<9'."],
   ["install.sh báo 'chua co pip'","apt install python3-pip (hoặc dùng gói zip offline)."],
   ["/metrics không có dữ liệu host","Chờ 1–4 phút lần lấy đầu; kiểm tra kết nối 443 tới vCenter; xem journalctl."],
   ["Write latency luôn 0","Chưa bật vSAN Performance Service trên cluster."],
   ["Grafana bảng trống","Prometheus chưa scrape; kiểm tra Targets UP và chọn đúng Cluster."]]));

// ============ Bao mat
children.push(H1("10. Bảo mật"));
children.push(bullet("Tài khoản vCenter chỉ cần Read-only. Mật khẩu lưu ở .env quyền 600, chạy dưới user esxi-exporter."));
children.push(bullet("Không commit/chia sẻ file .env và .vsan_pass (đã chặn trong .gitignore)."));
children.push(bullet("Mật khẩu đã lộ thì đổi ngay rồi chạy lại install.sh (cùng tên instance)."));

const doc = new Document({
  creator:"FIX NHANH", title:"Huong dan ESXi Host Exporter",
  styles:{ default:{ document:{ run:{ font:"Calibri", size:21 } } } },
  numbering:{ config:[
    {reference:"bl", levels:[{level:0,format:LevelFormat.BULLET,text:"•",alignment:AlignmentType.LEFT,style:{paragraph:{indent:{left:420,hanging:220}}}}]},
    {reference:"nm", levels:[{level:0,format:LevelFormat.DECIMAL,text:"%1.",alignment:AlignmentType.LEFT,style:{paragraph:{indent:{left:420,hanging:220}}}}]}
  ]},
  sections:[{ properties:{ page:{ margin:{top:1000,bottom:1000,left:1100,right:1100} } }, children }]
});
Packer.toBuffer(doc).then(b=>{fs.writeFileSync(process.argv[2],b);console.log("wrote",process.argv[2],b.length,"bytes");});
