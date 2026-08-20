/* ===== 靶场扫描助手 · 前端逻辑 v3（双模式 + 数据看板） ===== */
"use strict";

let scanning = false;
let scanMode = "";          // "public" | "internal"
let pollTimer = null;
let currentResultsDir = "";
let shotsEnabled = true;

/* 公网模式计数 */
let openCount = 0;
let targetsCount = 1;
let targetsDone = 0;
let currentTargetIdx = 0;   // 当前扫描到第几个目标

/* 站点卡片：排序/筛选用 */
let siteCards = [];         // [{evt, el}]

/* 截图/图标 base64 缓存，避免重复读盘 */
const imgCache = new Map();

/* 扫描耗时统计 */
let scanStartTime = 0;

/* 内网模式计数 */
let intStats = null;

/* 图表数据采集 */
let pubPorts = [];           // 公网：每个 port_found 事件
let intHosts = [];           // 内网：每个 host_found 事件
let chartInstances = {};     // Chart.js 实例引用，更新前销毁

const $ = (id) => document.getElementById(id);
const AVATAR_COLORS = [
  ["#4aa3ff", "#0053c7"], ["#63d16e", "#1d8a3a"], ["#ff9f2e", "#c96a00"],
  ["#ff6482", "#c21540"], ["#af7bff", "#6d3ce0"], ["#3ecad6", "#0f8a9c"],
];

/* Apple 风格调色板 */
const PALETTE = {
  blue:   "#007aff", green:  "#34c759", orange: "#ff9500", red:    "#ff3b30",
  purple: "#af52de", teal:   "#5ac8fa", pink:   "#ff2d55", yellow: "#ffd60a",
  gray:   "#8e8e93", indigo: "#5856d6", mint:   "#00c7be", cyan:   "#32ade6",
};

/* ---------- 基础工具 ---------- */

function timestamp() {
  const d = new Date();
  return [d.getHours(), d.getMinutes(), d.getSeconds()]
    .map((n) => String(n).padStart(2, "0")).join(":");
}

function log(level, text) {
  const con = $("console");
  const stick = con.scrollTop + con.clientHeight >= con.scrollHeight - 24;  // 已在底部才自动滚动
  const line = document.createElement("div");
  line.className = "log-line " + level;
  const time = document.createElement("span");
  time.className = "log-time";
  time.textContent = timestamp();
  const msg = document.createElement("span");
  msg.className = "msg";
  msg.textContent = text;
  line.append(time, msg);
  con.appendChild(line);
  while (con.children.length > 500) con.removeChild(con.firstChild);
  if (stick) con.scrollTop = con.scrollHeight;
}

/* 顶部高亮横幅（扫描完成等醒目事件，插到日志区第一行） */
function logBanner(level, text) {
  const con = $("console");
  const line = document.createElement("div");
  line.className = "log-line banner " + level;
  const time = document.createElement("span");
  time.className = "log-time";
  time.textContent = timestamp();
  const msg = document.createElement("span");
  msg.className = "msg";
  msg.textContent = text;
  line.append(time, msg);
  con.insertBefore(line, con.firstChild);
}

function setStatus(text, active) {
  $("statusText").textContent = text;
  $("statusDot").classList.toggle("on", !!active);
}

function applyPlatformTheme() {
  const ua = navigator.userAgent || "";
  const isWindows = /Windows NT|Windows/i.test(ua);
  const isMac = !isWindows && /Macintosh|Mac OS X/i.test(ua);
  document.body.classList.toggle("platform-windows", isWindows);
  document.body.classList.toggle("platform-macos", isMac);
  document.documentElement.dataset.platform = isWindows ? "windows" : (isMac ? "macos" : "other");
}

/* 截图/图标读取（带缓存；跨扫描保留，容量超限自动清理最旧部分） */
async function shotData(resultsDir, filename) {
  const key = resultsDir + "/" + filename;
  if (imgCache.has(key)) return { data: imgCache.get(key) };
  if (imgCache.size > 600) imgCache.clear();   // 防止无限增长
  const res = await pywebview.api.screenshot_data(resultsDir, filename);
  if (res && res.data) imgCache.set(key, res.data);
  return res;
}

function setBar(area, pct, text) {
  const suffix = area === "" ? "" : "2";
  $("progressFill" + suffix).style.width = Math.min(pct, 100) + "%";
  if (text !== undefined) $("progressText" + suffix).textContent = text;
  $("progressPct" + suffix).textContent = Math.round(Math.min(pct, 100)) + "%";
}

/* ---------- 灯箱 ---------- */

async function openLightbox(title, filename) {
  const res = await shotData(currentResultsDir, filename);
  if (!res || res.error) { log("error", "读取截图失败：" + (res && res.error)); return; }
  $("lightboxTitle").textContent = title;
  $("lightboxImg").src = res.data;
  $("lightbox").hidden = false;
}

function closeLightbox() { $("lightbox").hidden = true; }

/* ---------- 公网：站点卡片 ---------- */

function addSiteCard(evt) {
  if ($("emptyHint")) $("emptyHint").remove();
  const card = document.createElement("div");
  card.className = "site-card";
  card.dataset.key = evt.ip + ":" + evt.port;
  card.dataset.ip = evt.ip;
  card.dataset.port = evt.port;
  card.dataset.status = evt.status || 0;

  if (shotsEnabled && evt.is_http) {
    const thumb = document.createElement("div");
    thumb.className = "site-thumb";
    const wait = document.createElement("div");
    wait.className = "thumb-wait";
    const sp = document.createElement("div");
    sp.className = "spinner";
    const tip = document.createElement("span");
    tip.textContent = "截图中…";
    wait.append(sp, tip);
    thumb.appendChild(wait);
    card.appendChild(thumb);
  }

  const info = document.createElement("div");
  info.className = "site-info";

  const avatar = document.createElement("div");
  avatar.className = "site-avatar";
  const hash = [...(evt.ip + evt.port)].reduce((a, c) => a + c.charCodeAt(0), 0);
  const [c1, c2] = AVATAR_COLORS[hash % AVATAR_COLORS.length];
  avatar.style.background = `linear-gradient(145deg, ${c1}, ${c2})`;
  const titleText = evt.title || evt.ip;
  const initialChar = (titleText.match(/[A-Za-z0-9一-龥]/) || ["?"])[0];
  avatar.textContent = initialChar.toUpperCase();

  const main = document.createElement("div");
  main.className = "site-main";
  const t = document.createElement("div");
  t.className = "site-title";
  t.textContent = evt.title || "(无标题)";
  t.title = evt.title || "";
  const url = document.createElement("div");
  url.className = "site-url";
  url.textContent = `${evt.scheme || "http"}://${evt.ip}:${evt.port}`;
  const meta = document.createElement("div");
  meta.className = "site-meta";
  const badge = document.createElement("span");
  if (evt.is_http) {
    badge.className = "badge " + (evt.status < 400 ? "ok" : "other");
    badge.textContent = evt.status;
  } else {
    badge.className = "badge other";
    badge.textContent = "非 HTTP";
  }
  meta.appendChild(badge);
  if (evt.server) {
    const sv = document.createElement("span");
    sv.className = "site-server";
    sv.textContent = evt.server;
    sv.title = evt.server;
    meta.appendChild(sv);
  }
  main.append(t, url, meta);

  const btn = document.createElement("button");
  btn.className = "btn-open";
  if (evt.is_http) {
    btn.textContent = "打开";
    btn.addEventListener("click", () => {
      pywebview.api.open_url(`${evt.scheme || "http"}://${evt.ip}:${evt.port}/`);
    });
  } else {
    /* 非 HTTP 服务无法在浏览器打开：禁用并提示 */
    btn.textContent = "非 HTTP";
    btn.classList.add("disabled");
    btn.title = "非 HTTP 服务，无法在浏览器中打开";
  }

  info.append(avatar, main, btn);
  card.appendChild(info);
  siteCards.push({ evt, el: card });
  $("resultsGrid").appendChild(card);
}

/* 站点卡片排序 / 筛选（前端即时执行，不动后端） */
function applySiteTools() {
  const q = ($("siteSearch").value || "").trim().toLowerCase();
  const sort = $("siteSort").value;
  let list = siteCards.filter(c => {
    if (!q) return true;
    const e = c.evt;
    const hay = `${e.ip} ${e.port} ${e.scheme || ""} ${e.title || ""} ${e.server || ""}`.toLowerCase();
    return hay.includes(q);
  });
  if (sort === "port") list.sort((a, b) => a.evt.port - b.evt.port);
  else if (sort === "status") list.sort((a, b) => (a.evt.status || 0) - (b.evt.status || 0));
  else if (sort === "ip") list.sort((a, b) => a.evt.ip.localeCompare(b.evt.ip, undefined, { numeric: true }));
  const grid = $("resultsGrid");
  grid.textContent = "";
  list.forEach(c => grid.appendChild(c.el));
}

/* 看板图表头部注入导出按钮 */
function decorateChartHeads() {
  document.querySelectorAll(".chart-card").forEach(card => {
    const head = card.querySelector(".chart-head");
    const canvas = card.querySelector("canvas");
    if (!head || !canvas || head.querySelector(".chart-export")) return;
    const btn = document.createElement("button");
    btn.className = "chart-export";
    btn.dataset.canvas = canvas.id;
    btn.textContent = "导出 PNG";
    btn.title = "导出为 PNG 图片";
    head.appendChild(btn);
  });
}

/* 摘要条尾部加"查看看板"锚点 */
function appendDashLink(sumEl, dashId) {
  if (!document.getElementById(dashId)) return;
  const go = document.createElement("button");
  go.className = "btn-open dash-link";
  go.textContent = "查看看板 →";
  go.addEventListener("click", () => {
    document.getElementById(dashId).scrollIntoView({ behavior: "smooth", block: "start" });
  });
  sumEl.appendChild(go);
}

async function attachThumbnail(evt) {
  const card = document.querySelector(`[data-key="${evt.ip}:${evt.port}"]`);
  if (!card) return;
  /* favicon → 卡片头像换成站点真实图标 */
  if (evt.favicon) {
    const fres = await shotData(currentResultsDir, evt.favicon);
    if (fres && fres.data) {
      const avatar = card.querySelector(".site-avatar");
      if (avatar) {
        avatar.style.background = "#f2f2f4";
        avatar.innerHTML = "";
        const img = document.createElement("img");
        img.src = fres.data;
        img.className = "fav-img";
        avatar.appendChild(img);
      }
    }
  }
  const thumb = card.querySelector(".site-thumb");
  if (!thumb) return;
  if (!evt.ok) {
    thumb.innerHTML = "";
    const wait = document.createElement("div");
    wait.className = "thumb-wait";
    wait.textContent = "截图失败";
    thumb.appendChild(wait);
    return;
  }
  const res = await shotData(currentResultsDir, evt.path);
  if (!res || res.error) return;
  thumb.innerHTML = "";
  const img = document.createElement("img");
  img.src = res.data;
  img.alt = "首页截图";
  img.addEventListener("click", () =>
    openLightbox(`${evt.ip}:${evt.port} 首页截图`, evt.path));
  thumb.appendChild(img);
}

function resetResults() {
  openCount = 0;
  targetsDone = 0;
  currentTargetIdx = 0;
  pubPorts = [];
  siteCards = [];
  /* 截图缓存跨扫描保留（容量上限由 shotData 控制），避免重扫同站点重复读盘 */
  $("targetPos").hidden = true;
  $("resultCount").hidden = true;
  $("resultCount").textContent = "0";
  $("stAlive").textContent = "0";
  $("stPorts").textContent = "0";
  $("stSites").textContent = "0";
  $("stShots").textContent = "0";
  $("btnReport").hidden = true;
  $("publicDash").hidden = true;
  $("scanSummary").hidden = true;
  const grid = $("resultsGrid");
  while (grid.firstChild) grid.removeChild(grid.firstChild);
}

/* ---------- 内网：主机表格 ---------- */

function resetHosts() {
  intStats = { alive: 0, Linux: 0, Windows: 0, "未知": 0 };
  intHosts = [];
  $("hostCount").hidden = true;
  ["stAlive2", "stLinux", "stWin", "stUnknown"].forEach((id) => $(id).textContent = "0");
  $("btnReport2").hidden = true;
  $("internalDash").hidden = true;
  $("scanSummary2").hidden = true;
  const tbody = $("hostRows");
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
}

function addHostRow(h) {
  intStats.alive++;
  intStats[h.os_guess]++;
  $("stAlive2").textContent = intStats.alive;
  $("stLinux").textContent = intStats.Linux;
  $("stWin").textContent = intStats.Windows;
  $("stUnknown").textContent = intStats["未知"];
  $("hostCount").hidden = false;
  $("hostCount").textContent = intStats.alive;

  const tr = document.createElement("tr");
  tr.dataset.ip = h.ip;
  tr.dataset.os = h.os_guess;
  tr.dataset.ttl = h.ttl != null ? h.ttl : "";
  tr.dataset.portsCount = h.open_ports.length;

  const tdIp = document.createElement("td");
  tdIp.className = "ip";
  tdIp.textContent = h.ip;
  tdIp.title = "点击复制 IP";
  tdIp.dataset.copy = h.ip;

  const tdVia = document.createElement("td");
  tdVia.textContent = h.via === "icmp" ? "ICMP" : "TCP";

  const tdTtl = document.createElement("td");
  tdTtl.textContent = h.ttl != null ? h.ttl : "-";

  const tdOs = document.createElement("td");
  const osBadge = document.createElement("span");
  osBadge.className = "os-badge " + h.os_guess;
  osBadge.textContent = h.os_guess;
  tdOs.appendChild(osBadge);

  const tdPorts = document.createElement("td");
  tdPorts.className = "ports";
  tdPorts.textContent = h.open_ports.length ? h.open_ports.join(", ") : "-";

  const tdMac = document.createElement("td");
  tdMac.className = "mac";
  tdMac.textContent = "-";

  const tdReason = document.createElement("td");
  tdReason.className = "reason";
  const reasonText = h.reasons.join("；") || "无信号";
  tdReason.textContent = reasonText;
  tdReason.title = reasonText;

  tr.append(tdIp, tdVia, tdTtl, tdOs, tdPorts, tdMac, tdReason);
  $("hostRows").appendChild(tr);
}

/* ---------- 内网表格排序 + 复制 IP ---------- */
let hostSortKey = "";
let hostSortAsc = true;

function sortHosts(key) {
  if (hostSortKey === key) hostSortAsc = !hostSortAsc;
  else { hostSortKey = key; hostSortAsc = true; }
  document.querySelectorAll(".host-table th.sortable").forEach(th => {
    th.classList.toggle("sorted", th.dataset.sort === key);
    th.classList.toggle("asc", th.dataset.sort === key && hostSortAsc);
  });
  const tbody = $("hostRows");
  const rows = Array.from(tbody.querySelectorAll("tr[data-ip]"));
  const cmp = {
    ip: (a, b) => a.dataset.ip.localeCompare(b.dataset.ip, undefined, { numeric: true }),
    os: (a, b) => String(a.dataset.os || "").localeCompare(String(b.dataset.os || ""), "zh"),
    ttl: (a, b) => (parseInt(a.dataset.ttl, 10) || 0) - (parseInt(b.dataset.ttl, 10) || 0),
    ports: (a, b) => (parseInt(a.dataset.portsCount, 10) || 0) - (parseInt(b.dataset.portsCount, 10) || 0),
  };
  const dir = hostSortAsc ? 1 : -1;
  rows.sort((a, b) => dir * (cmp[key] ? cmp[key](a, b) : 0));
  rows.forEach(r => tbody.appendChild(r));
}

function copyToClipboard(text) {
  const done = () => log("info", `已复制 IP：${text}`);
  const fallback = () => {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      done();
    } catch (e) { log("warn", "复制失败"); }
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(fallback);
  } else fallback();
}

function applyMacs(macs) {
  Object.entries(macs || {}).forEach(([ip, mac]) => {
    const cell = document.querySelector(`tr[data-ip="${ip}"] .mac`);
    if (cell) cell.textContent = mac;
  });
}

/* ---------- 扫描状态 ---------- */

function setScanning(on, mode) {
  scanning = on;
  scanMode = on ? mode : scanMode;
  const btn = mode === "internal" ? $("btnInternal") : $("btnScan");
  const otherBtn = mode === "internal" ? $("btnScan") : $("btnInternal");
  ["inpTargets", "inpPortStart", "inpPortEnd", "inpThreads", "inpTimeout",
   "inpPortsList", "inpShots", "inpCidrs", "inpPorts", "inpThreads2", "inpTimeout2"]
    .forEach((id) => { $(id).disabled = on; });
  document.querySelectorAll(".preset-btn").forEach((button) => { button.disabled = on; });
  document.querySelector(".switch").classList.toggle("disabled", on);

  if (on) {
    btn.textContent = mode === "internal" ? "停止扫描" : "停止扫描";
    btn.classList.add("stop", "scanning");
    otherBtn.disabled = true;
    (mode === "internal" ? $("progressArea2") : $("progressArea")).hidden = false;
    (mode === "internal" ? $("statsBar2") : $("statsBar")).hidden = false;
    setStatus("扫描中", true);
  } else {
    document.querySelectorAll(".btn-primary").forEach((b) => {
      b.disabled = false;
      b.classList.remove("stop", "scanning");
    });
    $("btnScan").textContent = "开始扫描";
    $("btnInternal").textContent = "开始内网扫描";
    setStatus("就绪", false);
  }
}

/* ---------- 参数校验 ---------- */

function setInvalid(el, bad) { el.classList.toggle("invalid", !!bad); }

function validNumber(v, min, max) {
  if (v === "" || v === null || v === undefined) return false;
  const n = Number(v);
  return Number.isFinite(n) && n >= min && n <= max;
}

/* 公网输入实时校验：非法红框 + 禁用开始按钮 */
function updatePublicValidity() {
  const portsList = $("inpPortsList").value.trim();
  const ps = $("inpPortStart").value, pe = $("inpPortEnd").value;
  let okPorts = true;
  if (portsList) {
    /* 端口列表模式：只校验列表合法性，范围输入框置空 */
    const items = portsList.split(/[,，\s]+/).filter(Boolean);
    okPorts = items.length > 0 &&
      items.every(x => /^\d+$/.test(x) && +x >= 1 && +x <= 65535);
    setInvalid($("inpPortsList"), !okPorts);
    setInvalid($("inpPortStart"), false);
    setInvalid($("inpPortEnd"), false);
  } else {
    const okPs = validNumber(ps, 1, 65535);
    const okPe = validNumber(pe, 1, 65535);
    const okRange = !okPs || !okPe || parseInt(pe, 10) >= parseInt(ps, 10);
    okPorts = okPs && okPe && okRange;
    setInvalid($("inpPortsList"), false);
    setInvalid($("inpPortStart"), !okPs);
    setInvalid($("inpPortEnd"), !okPe || !okRange);
  }
  const okThreads = validNumber($("inpThreads").value, 1, 1000);
  const okTimeout = validNumber($("inpTimeout").value, 0.5, 30);
  setInvalid($("inpThreads"), !okThreads);
  setInvalid($("inpTimeout"), !okTimeout);
  if (!scanning) $("btnScan").disabled = !(okPorts && okThreads && okTimeout);
}

/* 内网输入实时校验 */
function updateInternalValidity() {
  const okThreads = validNumber($("inpThreads2").value, 1, 1000);
  const okTimeout = validNumber($("inpTimeout2").value, 0.5, 10);
  setInvalid($("inpThreads2"), !okThreads);
  setInvalid($("inpTimeout2"), !okTimeout);
  if (!scanning) $("btnInternal").disabled = !(okThreads && okTimeout);
}

function collectPublicParams() {
  const targets = $("inpTargets").value.trim();
  const ps = parseInt($("inpPortStart").value, 10);
  const pe = parseInt($("inpPortEnd").value, 10);
  const th = parseInt($("inpThreads").value, 10);
  const to = parseFloat($("inpTimeout").value);
  if (!targets) { log("error", "目标 IP 不能为空"); return null; }
  let portsStr = null;
  const portsList = $("inpPortsList").value.trim();
  if (portsList) {
    /* 端口列表模式：显式端口集合，优先于范围 */
    const items = portsList.split(/[,，\s]+/).filter(Boolean);
    const bad = items.filter(x => !/^\d+$/.test(x) || +x < 1 || +x > 65535);
    if (bad.length) { log("error", `端口列表含非法项：${bad.join("、")}`); return null; }
    if (items.length > 5000) log("warn", `端口数量较多（${items.length} 个），预计耗时较长`);
    portsStr = items.join(",");
  } else {
    if (!(ps >= 1 && ps <= 65535 && pe >= 1 && pe <= 65535)) {
      log("error", "端口范围不合法（1-65535）"); return null;
    }
    if (pe < ps) { log("error", "结束端口不能小于起始端口"); return null; }
    if (pe - ps + 1 > 5000) log("warn", `端口范围较大（${pe - ps + 1} 个），预计耗时较长`);
  }
  if (!(th >= 1 && th <= 1000)) { log("error", "并发线程需在 1-1000 之间"); return null; }
  if (!(to >= 0.5 && to <= 30)) { log("error", "超时需在 0.5-30 秒之间"); return null; }
  return { targets, ps, pe, th, to, portsStr };
}

function collectInternalParams() {
  const cidrs = $("inpCidrs").value.trim();
  const ports = $("inpPorts").value.trim();
  const th = parseInt($("inpThreads2").value, 10);
  const to = parseFloat($("inpTimeout2").value);
  if (!cidrs) { log("error", "网段不能为空"); return null; }
  if (!ports) { log("error", "探测端口不能为空"); return null; }
  if (!(th >= 1 && th <= 1000)) { log("error", "并发线程需在 1-1000 之间"); return null; }
  if (!(to >= 0.5 && to <= 10)) { log("error", "超时需在 0.5-10 秒之间"); return null; }
  return { cidrs, ports, th, to };
}

/* ---------- 事件分发 ---------- */

function handleEvent(evt) {
  if (evt.type === "error") {
    log("error", evt.message);
    if (evt.fatal) {
      clearInterval(pollTimer);
      pollTimer = null;
      const suffix = scanMode === "internal" ? "2" : "";
      setScanning(false, scanMode);
      setBar(suffix, 100, "扫描失败");
      logBanner("error", "扫描未完成，请检查参数和运行环境");
    }
    return;
  }

  /* ---- 公共结束 ---- */
  if (evt.type === "scan_done") {
    clearInterval(pollTimer);
    pollTimer = null;
    const suffix = scanMode === "internal" ? "2" : "";
    setScanning(false, scanMode);
    setBar(suffix, 100, evt.cancelled ? "扫描已停止" : "扫描完成");
    let summaryText;
    if (scanMode === "internal") {
      const c = evt.counts || {};
      summaryText = `存活 ${c["存活主机"] || 0} 台 · Linux ${c["Linux"] || 0} · Windows ${c["Windows"] || 0}`;
      logBanner(evt.cancelled ? "warn" : "success",
          (evt.cancelled ? "⚠ 扫描已停止" : "✅ 扫描完成") + `：${summaryText} · 未知 ${c["未知"] || 0}`);
      renderInternalCharts();
      const dur = ((Date.now() - scanStartTime) / 1000).toFixed(1);
      const sum2 = $("scanSummary2");
      sum2.hidden = false;
      sum2.innerHTML =
        `<span class="sum-item">耗时 <b>${dur} s</b></span>` +
        `<span class="sum-item">存活 <b>${c["存活主机"] || 0}</b> 台</span>` +
        `<span class="sum-item">Linux <b>${c["Linux"] || 0}</b></span>` +
        `<span class="sum-item">Windows <b>${c["Windows"] || 0}</b></span>` +
        `<span class="sum-item">未知 <b>${c["未知"] || 0}</b></span>`;
      appendDashLink(sum2, "internalDash");
    } else {
      summaryText = `发现 ${evt.open_total} 个开放端口、${evt.screenshot_total || 0} 张截图`;
      logBanner(evt.cancelled ? "warn" : "success",
          (evt.cancelled ? "⚠ 扫描已停止" : "✅ 扫描完成") + `：${summaryText}`);
      renderPublicCharts();
      const dur = ((Date.now() - scanStartTime) / 1000).toFixed(1);
      const sumEl = $("scanSummary");
      sumEl.hidden = false;
      sumEl.innerHTML =
        `<span class="sum-item">耗时 <b>${dur} s</b></span>` +
        `<span class="sum-item">目标 <b>${$("stTargets").textContent}</b> 个</span>` +
        `<span class="sum-item">ping 存活 <b>${$("stAlive").textContent}</b></span>` +
        `<span class="sum-item">开放端口 <b>${evt.open_total}</b></span>` +
        `<span class="sum-item">截图 <b>${evt.screenshot_total || 0}</b></span>`;
      appendDashLink(sumEl, "publicDash");
    }
    /* 完成提示音（失败静默） */
    try { if (pywebview.api.play_sound) pywebview.api.play_sound(); } catch (e) { /* 忽略 */ }
    log("info", `分类报告已保存：${evt.results_dir}（report.html / report.md / report.csv）`);
    const btnReport = $("btnReport" + suffix);
    if (currentResultsDir) {
      btnReport.hidden = false;
      btnReport.onclick = () => pywebview.api.open_report(currentResultsDir + "/report.html");
    }
    if (!document.hasFocus()) {
      pywebview.api.notify("靶场扫描助手",
          (evt.cancelled ? "扫描已停止：" : "扫描完成：") + summaryText);
    }
    return;
  }

  if (scanMode === "internal") {
    /* ---- 内网模式事件 ---- */
    switch (evt.type) {
      case "scan_start":
        currentResultsDir = evt.results_dir;
        scanStartTime = Date.now();
        log("info", `开始内网扫描：网段 ${evt.cidrs.join("、")}（共 ${evt.total_hosts} 个 IP），探测端口 ${evt.ports.join(",")}`);
        setBar("2", 0, "准备中…");
        break;
      case "progress": {
        const label = evt.phase === "ping" ? "主机存活探测（ICMP）" : "端口与系统探测";
        setBar("2", (evt.done / evt.total) * 100, `${label} … ${evt.done}/${evt.total}`);
        break;
      }
      case "host_found": {
        intHosts.push(evt);
        addHostRow(evt);
        log("success", `${evt.ip} 存活（${evt.via === "icmp" ? "ICMP" : "TCP"}）· 判断：${evt.os_guess}` +
            (evt.ttl != null ? ` · TTL=${evt.ttl}` : "") +
            (evt.open_ports.length ? ` · 端口 ${evt.open_ports.join(",")}` : ""));
        break;
      }
      case "mac_resolved":
        applyMacs(evt.macs);
        if (Object.keys(evt.macs || {}).length) {
          log("info", `ARP 已解析 ${Object.keys(evt.macs).length} 台主机的 MAC 地址`);
        }
        break;
    }
    return;
  }

  /* ---- 公网模式事件 ---- */
  switch (evt.type) {
    case "scan_start":
      currentResultsDir = evt.results_dir;
      scanStartTime = Date.now();
      targetsCount = evt.targets.length;
      $("stTargets").textContent = targetsCount;
      const pdesc = evt.ports ? `端口列表（${evt.ports.length} 个）` : `端口 ${evt.port_start}-${evt.port_end}`;
      const tlist = evt.targets || [];
      const tdesc = tlist.length > 5
        ? `${tlist.slice(0, 3).join("、")}… 等 ${tlist.length} 个`
        : tlist.join("、");
      if (tlist.length > 256) log("warn", `目标较多（${tlist.length} 个，可能来自 CIDR 网段），预计耗时较长`);
      log("info", `开始扫描：目标 ${tdesc}，${pdesc}`);
      setBar("", 0, "准备中…");
      break;
    case "target_start":
      currentTargetIdx++;
      const posEl = $("targetPos");
      posEl.hidden = false;
      posEl.textContent = `目标 ${currentTargetIdx}/${targetsCount}`;
      log("info", `── 目标 ${evt.ip} ──`);
      break;
    case "ping":
      if (evt.alive) {
        $("stAlive").textContent = (parseInt($("stAlive").textContent, 10) || 0) + 1;
        log("success", `ping ${evt.ip} 通${evt.latency_ms != null ? `（${evt.latency_ms.toFixed(1)} ms）` : ""}`);
      } else {
        log("warn", `ping ${evt.ip} 不通（云服务器可能禁 ICMP，继续端口扫描）`);
      }
      break;
    case "progress": {
      const overall = ((targetsDone + evt.done / evt.total) / targetsCount) * 100;
      setBar("", overall, `正在扫描 ${evt.ip} … ${evt.done}/${evt.total}`);
      break;
    }
    case "port_found":
      openCount++;
      pubPorts.push(evt);
      $("resultCount").hidden = false;
      $("resultCount").textContent = openCount;
      $("stPorts").textContent = openCount;
      if (evt.is_http) {
        $("stSites").textContent = (parseInt($("stSites").textContent, 10) || 0) + 1;
      }
      addSiteCard(evt);
      if (evt.is_http) {
        log("success", `${evt.ip}:${evt.port} 开放  ${evt.scheme} 状态 ${evt.status}  title: ${evt.title || "(无)"}`);
      } else {
        log("warn", `${evt.ip}:${evt.port} 开放（非 HTTP）`);
      }
      break;
    case "phase":
      if (evt.phase === "screenshots") {
        setBar("", 100, "端口扫描完成，正在截取网站首页…");
      }
      break;
    case "screenshot_done":
      if (evt.ok) {
        $("stShots").textContent = (parseInt($("stShots").textContent, 10) || 0) + 1;
        log("info", `[截图] ${evt.ip}:${evt.port} 完成`);
      } else {
        log("warn", `[截图] ${evt.ip}:${evt.port} 失败：${evt.error || ""}`);
      }
      attachThumbnail(evt);
      break;
    case "target_done":
      targetsDone++;
      log("info", `目标 ${evt.ip} 完成${evt.cancelled ? "（已取消）" : ""}：开放端口 ${evt.open_count}/${evt.total}`);
      break;
  }
}

async function poll() {
  try {
    const events = await pywebview.api.poll_events(60);  // 分批，避免一次渲染过多事件卡主线程
    (events || []).forEach(handleEvent);
  } catch (e) { /* 窗口关闭等场景忽略 */ }
}

/* ---------- 页面 ---------- */

function switchPage(name) {
  document.querySelectorAll(".nav-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.page === name);
  });
  document.querySelectorAll(".page").forEach((el) => {
    el.classList.toggle("active", el.id === "page-" + name);
  });
  if (name === "history") loadHistory();
}

let historyItems = [];

async function loadHistory() {
  historyItems = (await pywebview.api.get_history()) || [];
  renderHistory();
}

function renderHistory() {
  const list = $("historyList");
  list.textContent = "";
  const q = ($("historySearch").value || "").trim().toLowerCase();
  const items = historyItems.filter(it =>
    !q || `${it.time} ${(it.targets || []).join(" ")} ${it.summary}`.toLowerCase().includes(q));
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty-hint";
    empty.textContent = q ? "没有匹配的历史记录" : "暂无历史记录";
    list.appendChild(empty);
    return;
  }
  for (const it of items) {
    const row = document.createElement("div");
    row.className = "history-item";

    const folder = document.createElement("div");
    folder.className = "history-folder " + (it.kind === "internal" ? "internal" : "public");
    folder.innerHTML = it.kind === "internal"
      ? `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><rect x="3" y="5" width="18" height="6" rx="1.5"/><rect x="3" y="13" width="18" height="6" rx="1.5"/></svg>`
      : `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M3.5 7.5a1.5 1.5 0 0 1 1.5-1.5h4l2 2.5h8a1.5 1.5 0 0 1 1.5 1.5v8A1.5 1.5 0 0 1 19 19.5H5a1.5 1.5 0 0 1-1.5-1.5z"/></svg>`;

    const info = document.createElement("div");
    info.className = "history-info";
    const time = document.createElement("div");
    time.className = "history-time";
    time.textContent = `${it.time} · ${it.kind === "internal" ? "内网穿透" : "公网 Web"}`;
    const desc = document.createElement("div");
    desc.className = "history-desc";
    desc.textContent = `${(it.targets || []).join("、")} · ${it.summary}`;
    info.append(time, desc);

    const actions = document.createElement("div");
    actions.className = "history-actions";
    const bDash = document.createElement("button");
    bDash.className = "btn-open btn-dash";
    bDash.textContent = "看板";
    bDash.addEventListener("click", () => openDashModal(it));
    actions.appendChild(bDash);
    if (it.report_html) {
      const b1 = document.createElement("button");
      b1.className = "btn-open";
      b1.textContent = "查看报告";
      b1.addEventListener("click", () =>
        pywebview.api.open_report(it.path + "/report.html"));
      actions.appendChild(b1);
    }
    const b2 = document.createElement("button");
    b2.className = "btn-open";
    b2.textContent = "打开目录";
    b2.addEventListener("click", () => pywebview.api.open_path(it.path));
    actions.appendChild(b2);

    const del = document.createElement("button");
    del.className = "btn-open btn-delete";
    del.textContent = "删除";
    del.addEventListener("click", async () => {
      if (del.classList.contains("armed")) {
        const r = await pywebview.api.delete_history(it.path);
        if (r && r.ok) {
          historyItems = historyItems.filter(x => x.path !== it.path);
          row.style.opacity = "0";
          setTimeout(() => row.remove(), 180);
          log("info", `已删除历史记录：${it.name}`);
        } else {
          log("error", `删除失败：${(r && r.error) || "未知错误"}`);
          del.classList.remove("armed");
          del.textContent = "删除";
        }
      } else {
        del.classList.add("armed");
        del.textContent = "确认删除？";
        setTimeout(() => {
          del.classList.remove("armed");
          del.textContent = "删除";
        }, 2600);
      }
    });
    actions.appendChild(del);

    row.append(folder, info, actions);
    list.appendChild(row);
  }
}

/* ==========================================================
   数据看板 · Chart.js 图表渲染
   ========================================================== */

/* Chart.js 全局默认风格（Apple 设计语言）；CDN 加载失败时静默降级，不影响主功能 */
const CHART_OK = typeof Chart !== "undefined";
if (CHART_OK) {
  const darkMode = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif';
  Chart.defaults.font.size = 11.5;
  Chart.defaults.color = darkMode ? "#98989f" : '#8e8e93';
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.pointStyleWidth = 8;
  Chart.defaults.plugins.legend.labels.padding = 14;
  Chart.defaults.plugins.legend.labels.boxHeight = 7;
  Chart.defaults.animation.duration = 650;
  Chart.defaults.animation.easing = "easeOutQuart";
}

const BASE_OPTS = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: "rgba(30,30,30,0.88)",
      titleFont: { weight: "600", size: 12 },
      bodyFont: { size: 11.5 },
      cornerRadius: 8,
      padding: 10,
      displayColors: true,
      boxPadding: 4,
    },
  },
};

/* 销毁旧实例后创建新图 */
function makeChart(canvasId, config) {
  if (!CHART_OK) return null;
  if (chartInstances[canvasId]) { chartInstances[canvasId].destroy(); }
  const ctx = $(canvasId);
  if (!ctx) return null;
  chartInstances[canvasId] = new Chart(ctx, config);
  return chartInstances[canvasId];
}

/* ---------- 公网模式图表 ---------- */

function renderPublicCharts() {
  if (!pubPorts.length || !CHART_OK) return;
  $("publicDash").hidden = false;

  /* 1) 端口分布 —— 按端口区间分组的环形图 */
  renderPortDistChart();

  /* 2) HTTP 状态码 —— 柱状图 */
  renderHttpStatusChart();

  /* 3) 各目标开放端口数 —— 水平条形图 */
  renderTargetBarChart();

  /* 4) 服务类型占比 —— 环形图 */
  renderServiceTypeChart();

  decorateChartHeads();
}

function renderPortDistChart(data = pubPorts, canvas = "chartPortDist") {
  /* 将端口按区间聚合：0-999 / 1000-4999 / 5000-7999 / 8000-9999 / 10000-19999 / 20000-65535 */
  const ranges = [
    { label: "0–999",     min: 0,     max: 999 },
    { label: "1k–4999",   min: 1000,  max: 4999 },
    { label: "5k–7999",   min: 5000,  max: 7999 },
    { label: "8k–9999",   min: 8000,  max: 9999 },
    { label: "10k–19999", min: 10000, max: 19999 },
    { label: "20k–65535", min: 20000, max: 65535 },
  ];
  const counts = ranges.map(() => 0);
  data.forEach(p => {
    for (let i = 0; i < ranges.length; i++) {
      if (p.port >= ranges[i].min && p.port <= ranges[i].max) { counts[i]++; break; }
    }
  });
  const colors = [PALETTE.blue, PALETTE.teal, PALETTE.green, PALETTE.orange, PALETTE.purple, PALETTE.pink];
  const total = counts.reduce((a, b) => a + b, 0);

  makeChart(canvas, {
    type: "doughnut",
    data: {
      labels: ranges.map(r => r.label),
      datasets: [{
        data: counts,
        backgroundColor: colors,
        borderWidth: 2,
        borderColor: "#fff",
        hoverOffset: 6,
      }],
    },
    options: {
      ...BASE_OPTS,
      cutout: "62%",
      plugins: {
        ...BASE_OPTS.plugins,
        legend: { position: "right", labels: { font: { size: 10.5 }, padding: 8 } },
        tooltip: { ...BASE_OPTS.plugins.tooltip, callbacks: {
          label: ctx => ` ${ctx.label}：${ctx.parsed} 个端口（${total ? ((ctx.parsed / total) * 100).toFixed(1) : 0}%）`,
        }},
      },
    },
    plugins: [{
      id: "centerText",
      afterDraw(chart) {
        const { ctx: c, chartArea: { top, bottom, left, right } } = chart;
        const cx = (left + right) / 2, cy = (top + bottom) / 2;
        c.save();
        c.font = "800 22px -apple-system, sans-serif";
        c.fillStyle = getComputedStyle(document.body).color;
        c.textAlign = "center";
        c.textBaseline = "middle";
        c.fillText(String(total), cx, cy - 8);
        c.font = "500 10.5px -apple-system, sans-serif";
        c.fillStyle = Chart.defaults.color;
        c.fillText("总端口", cx, cy + 12);
        c.restore();
      }
    }],
  });
}

function renderHttpStatusChart(data = pubPorts, canvas = "chartHttpStatus") {
  const httpPorts = data.filter(p => p.is_http);
  const buckets = {};
  httpPorts.forEach(p => {
    const code = p.status;
    let label;
    if (code >= 200 && code < 300) label = "2xx 成功";
    else if (code >= 300 && code < 400) label = "3xx 重定向";
    else if (code >= 400 && code < 500) label = "4xx 客户端错误";
    else if (code >= 500) label = "5xx 服务端错误";
    else label = String(code);
    buckets[label] = (buckets[label] || 0) + 1;
  });
  const labels = Object.keys(buckets);
  const vals = Object.values(buckets);
  const colorMap = {
    "2xx 成功": PALETTE.green, "3xx 重定向": PALETTE.blue,
    "4xx 客户端错误": PALETTE.orange, "5xx 服务端错误": PALETTE.red,
  };
  const colors = labels.map(l => colorMap[l] || PALETTE.gray);

  makeChart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: vals,
        backgroundColor: colors.map(c => c + "33"),
        borderColor: colors,
        borderWidth: 1.5,
        borderRadius: 6,
        maxBarThickness: 48,
      }],
    },
    options: {
      ...BASE_OPTS,
      plugins: { ...BASE_OPTS.plugins, legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 10 } } },
        y: { beginAtZero: true, grid: { color: "rgba(0,0,0,0.04)" },
             ticks: { stepSize: 1, font: { size: 10 } } },
      },
    },
  });
}

function renderTargetBarChart(data = pubPorts, canvas = "chartTargetBar") {
  const ipMap = {};
  data.forEach(p => { ipMap[p.ip] = (ipMap[p.ip] || 0) + 1; });
  const sorted = Object.entries(ipMap).sort((a, b) => b[1] - a[1]);
  const labels = sorted.map(e => e[0]);
  const vals = sorted.map(e => e[1]);
  const barColors = labels.map((_, i) =>
    PALETTE.blue + (i === 0 ? "cc" : i === 1 ? "88" : "55"));

  makeChart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: vals,
        backgroundColor: barColors,
        borderWidth: 0,
        borderRadius: 6,
        maxBarThickness: 36,
      }],
    },
    options: {
      ...BASE_OPTS,
      indexAxis: "y",
      plugins: { ...BASE_OPTS.plugins, legend: { display: false } },
      scales: {
        x: { beginAtZero: true, grid: { color: "rgba(0,0,0,0.04)" },
             ticks: { stepSize: 1, font: { size: 10 } } },
        y: { grid: { display: false },
             ticks: { font: { size: 10.5, family: '"SF Mono", Menlo, monospace' } } },
      },
    },
  });
}

function renderServiceTypeChart(data = pubPorts, canvas = "chartServiceType") {
  const httpCount = data.filter(p => p.is_http).length;
  const httpsCount = data.filter(p => p.is_http && p.scheme === "https").length;
  const nonHttpCount = data.length - httpCount;
  const httpOnlyCount = httpCount - httpsCount;
  const vals = [];
  const labels = [];
  const colors = [];

  if (httpOnlyCount) { vals.push(httpOnlyCount); labels.push("HTTP"); colors.push(PALETTE.teal); }
  if (httpsCount)   { vals.push(httpsCount);   labels.push("HTTPS"); colors.push(PALETTE.blue); }
  if (nonHttpCount) { vals.push(nonHttpCount);  labels.push("非 HTTP"); colors.push(PALETTE.gray); }

  const total = vals.reduce((a, b) => a + b, 0);

  makeChart(canvas, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data: vals,
        backgroundColor: colors,
        borderWidth: 2,
        borderColor: "#fff",
        hoverOffset: 6,
      }],
    },
    options: {
      ...BASE_OPTS,
      cutout: "62%",
      plugins: {
        ...BASE_OPTS.plugins,
        legend: { position: "right", labels: { font: { size: 10.5 }, padding: 8 } },
        tooltip: { ...BASE_OPTS.plugins.tooltip, callbacks: {
          label: ctx => ` ${ctx.label}：${ctx.parsed} 个（${total ? ((ctx.parsed / total) * 100).toFixed(1) : 0}%）`,
        }},
      },
    },
    plugins: [{
      id: "centerText",
      afterDraw(chart) {
        const { ctx: c, chartArea: { top, bottom, left, right } } = chart;
        const cx = (left + right) / 2, cy = (top + bottom) / 2;
        c.save();
        c.font = "800 22px -apple-system, sans-serif";
        c.fillStyle = getComputedStyle(document.body).color;
        c.textAlign = "center";
        c.textBaseline = "middle";
        c.fillText(String(total), cx, cy - 8);
        c.font = "500 10.5px -apple-system, sans-serif";
        c.fillStyle = Chart.defaults.color;
        c.fillText("总服务", cx, cy + 12);
        c.restore();
      }
    }],
  });
}

/* ---------- 内网模式图表 ---------- */

function renderInternalCharts() {
  if (!intHosts.length) return;
  $("internalDash").hidden = false;

  renderOSDistChart();
  renderPortHeatChart();
  renderDiscoverChart();
  renderTTLDistChart();
  decorateChartHeads();
}

function renderOSDistChart(data = intHosts, canvas = "chartOSDist") {
  const buckets = {};
  data.forEach(h => { buckets[h.os_guess] = (buckets[h.os_guess] || 0) + 1; });
  const labels = Object.keys(buckets);
  const vals = Object.values(buckets);
  const colorMap = { "Linux": PALETTE.green, "Windows": PALETTE.blue, "未知": PALETTE.gray };
  const colors = labels.map(l => colorMap[l] || PALETTE.gray);
  const total = vals.reduce((a, b) => a + b, 0);

  makeChart(canvas, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data: vals,
        backgroundColor: colors,
        borderWidth: 2,
        borderColor: "#fff",
        hoverOffset: 6,
      }],
    },
    options: {
      ...BASE_OPTS,
      cutout: "62%",
      plugins: {
        ...BASE_OPTS.plugins,
        legend: { position: "right", labels: { font: { size: 11 }, padding: 10 } },
        tooltip: { ...BASE_OPTS.plugins.tooltip, callbacks: {
          label: ctx => ` ${ctx.label}：${ctx.parsed} 台（${total ? ((ctx.parsed / total) * 100).toFixed(1) : 0}%）`,
        }},
      },
    },
    plugins: [{
      id: "centerText",
      afterDraw(chart) {
        const { ctx: c, chartArea: { top, bottom, left, right } } = chart;
        const cx = (left + right) / 2, cy = (top + bottom) / 2;
        c.save();
        c.font = "800 22px -apple-system, sans-serif";
        c.fillStyle = getComputedStyle(document.body).color;
        c.textAlign = "center";
        c.textBaseline = "middle";
        c.fillText(String(total), cx, cy - 8);
        c.font = "500 10.5px -apple-system, sans-serif";
        c.fillStyle = Chart.defaults.color;
        c.fillText("总主机", cx, cy + 12);
        c.restore();
      }
    }],
  });
}

function renderPortHeatChart(data = intHosts, canvas = "chartPortHeat") {
  const portMap = {};
  data.forEach(h => {
    (h.open_ports || []).forEach(p => { portMap[p] = (portMap[p] || 0) + 1; });
  });
  const sorted = Object.entries(portMap).sort((a, b) => b[1] - a[1]).slice(0, 12);
  const labels = sorted.map(e => String(e[0]));
  const vals = sorted.map(e => e[1]);
  const colors = vals.map(v => {
    if (v >= data.length * 0.7) return PALETTE.red;
    if (v >= data.length * 0.4) return PALETTE.orange;
    return PALETTE.blue;
  });

  makeChart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "开放数",
        data: vals,
        backgroundColor: colors.map(c => c + "44"),
        borderColor: colors,
        borderWidth: 1.5,
        borderRadius: 5,
        maxBarThickness: 40,
      }],
    },
    options: {
      ...BASE_OPTS,
      plugins: { ...BASE_OPTS.plugins, legend: { display: false } },
      scales: {
        x: { grid: { display: false },
             ticks: { font: { size: 9.5, family: '"SF Mono", Menlo, monospace' } } },
        y: { beginAtZero: true, grid: { color: "rgba(0,0,0,0.04)" },
             ticks: { stepSize: 1, font: { size: 10 } } },
      },
    },
  });
}

function renderDiscoverChart(data = intHosts, canvas = "chartDiscover") {
  const icmp = data.filter(h => h.via === "icmp").length;
  const tcp = data.filter(h => h.via === "tcp").length;
  const total = icmp + tcp;

  makeChart(canvas, {
    type: "doughnut",
    data: {
      labels: ["ICMP", "TCP 兜底"],
      datasets: [{
        data: [icmp, tcp],
        backgroundColor: [PALETTE.green, PALETTE.orange],
        borderWidth: 2,
        borderColor: "#fff",
        hoverOffset: 6,
      }],
    },
    options: {
      ...BASE_OPTS,
      cutout: "62%",
      plugins: {
        ...BASE_OPTS.plugins,
        legend: { position: "right", labels: { font: { size: 10.5 }, padding: 8 } },
        tooltip: { ...BASE_OPTS.plugins.tooltip, callbacks: {
          label: ctx => ` ${ctx.label}：${ctx.parsed} 台（${total ? ((ctx.parsed / total) * 100).toFixed(1) : 0}%）`,
        }},
      },
    },
    plugins: [{
      id: "centerText",
      afterDraw(chart) {
        const { ctx: c, chartArea: { top, bottom, left, right } } = chart;
        const cx = (left + right) / 2, cy = (top + bottom) / 2;
        c.save();
        c.font = "800 22px -apple-system, sans-serif";
        c.fillStyle = getComputedStyle(document.body).color;
        c.textAlign = "center";
        c.textBaseline = "middle";
        c.fillText(String(total), cx, cy - 8);
        c.font = "500 10.5px -apple-system, sans-serif";
        c.fillStyle = Chart.defaults.color;
        c.fillText("总发现", cx, cy + 12);
        c.restore();
      }
    }],
  });
}

function renderTTLDistChart(data = intHosts, canvas = "chartTTLDist") {
  /* TTL 分桶：32–64 / 65–100 / 101–128 / 129–200 / 201–255 / null */
  const buckets = { "≤64": 0, "65–100": 0, "101–128": 0, ">128": 0, "无 TTL": 0 };
  data.forEach(h => {
    const t = h.ttl;
    if (t == null) { buckets["无 TTL"]++; }
    else if (t <= 64) { buckets["≤64"]++; }
    else if (t <= 100) { buckets["65–100"]++; }
    else if (t <= 128) { buckets["101–128"]++; }
    else { buckets[">128"]++; }
  });
  /* 去掉值为 0 的桶 */
  const labels = [], vals = [], colors = [];
  const colorMap = {
    "≤64": PALETTE.green, "65–100": PALETTE.teal, "101–128": PALETTE.blue,
    ">128": PALETTE.orange, "无 TTL": PALETTE.gray,
  };
  Object.entries(buckets).forEach(([k, v]) => {
    if (v > 0) { labels.push(k); vals.push(v); colors.push(colorMap[k]); }
  });
  const total = vals.reduce((a, b) => a + b, 0);

  makeChart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: vals,
        backgroundColor: colors.map(c => c + "44"),
        borderColor: colors,
        borderWidth: 1.5,
        borderRadius: 6,
        maxBarThickness: 44,
      }],
    },
    options: {
      ...BASE_OPTS,
      plugins: { ...BASE_OPTS.plugins, legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 10 } } },
        y: { beginAtZero: true, grid: { color: "rgba(0,0,0,0.04)" },
             ticks: { stepSize: 1, font: { size: 10 } } },
      },
    },
  });
}

/* ---------- 历史看板弹窗 ---------- */

/* 弹窗内图表用的 canvas ID 前缀（避免与主页 canvas 冲突） */
const MODAL_PREFIX = "modal_";

async function openDashModal(item) {
  $("dashModalTitle").textContent = item.time + " · 数据看板";
  const kindEl = $("dashModalKind");
  kindEl.textContent = item.kind === "internal" ? "内网穿透" : "公网 Web";
  kindEl.className = "modal-kind " + (item.kind === "internal" ? "internal" : "public");

  /* 清空旧图表 */
  const grid = $("dashModalGrid");
  grid.textContent = "";
  $("dashModalEmpty").hidden = true;
  $("dashModal").hidden = false;

  try {
    const res = await pywebview.api.get_report_data(item.path);
    if (!res || !res.ok) {
      $("dashModalEmpty").hidden = false;
      return;
    }

    if (res.kind === "public") {
      buildPublicDashCharts(res.ports || [], grid);
    } else {
      /* get_report_data 服务端已过滤只返回存活主机 */
      buildInternalDashCharts(res.hosts || [], grid);
    }
  } catch (e) {
    log("error", "加载看板数据失败：" + e);
    $("dashModalEmpty").hidden = false;
  }
}

function closeDashModal() { $("dashModal").hidden = true; }

function buildPublicDashCharts(data, container) {
  if (!data.length || !CHART_OK) { $("dashModalEmpty").hidden = false; return; }
  const ids = ["chartPortDist", "chartHttpStatus", "chartTargetBar", "chartServiceType"];
  const titles = ["端口分布", "HTTP 状态码", "各目标端口数", "服务类型占比"];
  ids.forEach((id, i) => {
    const modalId = MODAL_PREFIX + id;
    container.appendChild(makeChartCard(modalId, titles[i]));
  });
  /* 渲染到 modal canvas */
  renderPortDistChart(data, MODAL_PREFIX + "chartPortDist");
  renderHttpStatusChart(data, MODAL_PREFIX + "chartHttpStatus");
  renderTargetBarChart(data, MODAL_PREFIX + "chartTargetBar");
  renderServiceTypeChart(data, MODAL_PREFIX + "chartServiceType");
  decorateChartHeads();
}

function buildInternalDashCharts(data, container) {
  if (!data.length || !CHART_OK) { $("dashModalEmpty").hidden = false; return; }
  const ids = ["chartOSDist", "chartPortHeat", "chartDiscover", "chartTTLDist"];
  const titles = ["操作系统分布", "端口开放热度", "发现方式", "TTL 分布"];
  ids.forEach((id, i) => {
    const modalId = MODAL_PREFIX + id;
    container.appendChild(makeChartCard(modalId, titles[i]));
  });
  renderOSDistChart(data, MODAL_PREFIX + "chartOSDist");
  renderPortHeatChart(data, MODAL_PREFIX + "chartPortHeat");
  renderDiscoverChart(data, MODAL_PREFIX + "chartDiscover");
  renderTTLDistChart(data, MODAL_PREFIX + "chartTTLDist");
  decorateChartHeads();
}

function makeChartCard(canvasId, title) {
  const card = document.createElement("div");
  card.className = "chart-card";
  const head = document.createElement("div");
  head.className = "chart-head";
  head.textContent = title;
  const wrap = document.createElement("div");
  wrap.className = "chart-wrap";
  const canvas = document.createElement("canvas");
  canvas.id = canvasId;
  wrap.appendChild(canvas);
  card.append(head, wrap);
  return card;
}

/* ---------- 初始化 ---------- */

async function init() {
  try {
    const cfg = await pywebview.api.get_config();
    $("inpTargets").value = cfg.targets;
    $("inpPortStart").value = cfg.port_start;
    $("inpPortEnd").value = cfg.port_end;
    $("inpThreads").value = cfg.threads;
    $("inpTimeout").value = cfg.timeout;
    const icfg = await pywebview.api.get_internal_config();
    $("inpCidrs").value = icfg.cidrs;
    $("inpPorts").value = icfg.ports;
    $("inpThreads2").value = icfg.threads;
    $("inpTimeout2").value = icfg.timeout;
  } catch (e) {
    log("error", "读取配置失败：" + e);
  }
  /* 初始化后执行一次实时校验，让按钮可用性即时生效 */
  updatePublicValidity();
  updateInternalValidity();
  log("info", "环境就绪 · 公网模式扫描 Web 靶场，内网模式请先连接向日葵 VPN");
}

function bindUI() {
  applyPlatformTheme();
  document.querySelectorAll(".nav-item").forEach((el) => {
    el.addEventListener("click", () => switchPage(el.dataset.page));
  });

  /* 公网扫描 */
  $("btnScan").addEventListener("click", async () => {
    if (scanning) {
      if ($("btnScan").textContent === "确认停止？") {
        $("btnScan").disabled = true;
        await pywebview.api.stop_scan();
        log("warn", "已请求停止扫描…");
      } else {
        $("btnScan").textContent = "确认停止？";
        setTimeout(() => {
          if (scanning && $("btnScan").textContent === "确认停止？") {
            $("btnScan").textContent = "停止扫描";
          }
        }, 3000);
      }
      return;
    }
    const p = collectPublicParams();
    if (!p) return;
    /* 前端先做一次目标去重并提示（后端也会去重，这里让用户感知） */
    const raw = p.targets.split(",").map(t => t.trim()).filter(Boolean);
    const uniq = [...new Set(raw)];
    if (uniq.length < raw.length) {
      log("warn", `目标包含 ${raw.length - uniq.length} 个重复项，已自动去重`);
      p.targets = uniq.join(",");
    }
    shotsEnabled = $("inpShots").checked;
    const res = await pywebview.api.start_scan(p.targets, p.ps, p.pe, p.th, p.to, shotsEnabled, p.portsStr);
    if (!res || !res.ok) { log("error", (res && res.error) || "启动扫描失败"); return; }
    scanMode = "public";
    resetResults();
    $("statsBar").hidden = false;
    setScanning(true, "public");
    setBar("", 0, "准备中…");
    pollTimer = setInterval(poll, 250);
  });

  /* 内网扫描 */
  $("btnInternal").addEventListener("click", async () => {
    if (scanning) {
      if ($("btnInternal").textContent === "确认停止？") {
        $("btnInternal").disabled = true;
        await pywebview.api.stop_scan();
        log("warn", "已请求停止扫描…");
      } else {
        $("btnInternal").textContent = "确认停止？";
        setTimeout(() => {
          if (scanning && $("btnInternal").textContent === "确认停止？") {
            $("btnInternal").textContent = "停止扫描";
          }
        }, 3000);
      }
      return;
    }
    const p = collectInternalParams();
    if (!p) return;
    const res = await pywebview.api.start_internal_scan(p.cidrs, p.ports, p.th, p.to);
    if (!res || !res.ok) { log("error", (res && res.error) || "启动扫描失败"); return; }
    scanMode = "internal";
    resetHosts();
    $("statsBar2").hidden = false;
    setScanning(true, "internal");
    setBar("2", 0, "准备中…");
    pollTimer = setInterval(poll, 250);
  });

  /* 控制台折叠 / 清空 */
  $("consoleToggle").addEventListener("click", (e) => {
    if (e.target.closest("#btnClearLog")) return;
    $("consoleCard").classList.toggle("collapsed");
  });
  $("btnClearLog").addEventListener("click", () => { $("console").textContent = ""; });

  /* 站点排序 / 筛选 */
  $("siteSearch").addEventListener("input", applySiteTools);
  $("siteSort").addEventListener("change", applySiteTools);

  /* 端口快捷预设 */
  document.querySelectorAll(".preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.ports) {
        /* 端口列表预设（全量端口：常用 + 偏冷门） */
        $("inpPortsList").value = btn.dataset.ports;
        $("inpPortStart").value = "";
        $("inpPortEnd").value = "";
        log("info", `已载入「全量端口」预设（${btn.dataset.ports.split(",").length} 个常用/冷门端口）`);
      } else {
        $("inpPortsList").value = "";
        $("inpPortStart").value = btn.dataset.ps;
        $("inpPortEnd").value = btn.dataset.pe;
      }
      updatePublicValidity();
    });
  });

  /* 历史记录搜索 */
  $("historySearch").addEventListener("input", renderHistory);

  /* 内网表格：表头排序 + IP 点击复制 */
  document.querySelectorAll(".host-table th.sortable").forEach((th) => {
    th.addEventListener("click", () => sortHosts(th.dataset.sort));
  });
  $("hostRows").addEventListener("click", (e) => {
    const ipCell = e.target.closest("td.ip[data-copy]");
    if (ipCell) copyToClipboard(ipCell.dataset.copy);
  });

  /* 输入实时校验 */
  ["inpPortStart", "inpPortEnd", "inpPortsList", "inpThreads", "inpTimeout"].forEach((id) =>
    $(id).addEventListener("input", updatePublicValidity));
  ["inpThreads2", "inpTimeout2"].forEach((id) =>
    $(id).addEventListener("input", updateInternalValidity));

  /* 看板图表导出 PNG */
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".chart-export");
    if (!btn) return;
    const canvas = $(btn.dataset.canvas);
    if (!canvas) return;
    try {
      const a = document.createElement("a");
      a.href = canvas.toDataURL("image/png");
      a.download = btn.dataset.canvas + ".png";
      a.click();
      log("info", `已导出图表：${btn.dataset.canvas}.png`);
    } catch (err) {
      log("error", "导出图表失败：" + err);
    }
  });

  /* 回车快捷启动扫描 */
  ["inpTargets", "inpPortStart", "inpPortEnd", "inpPortsList", "inpThreads", "inpTimeout"].forEach((id) =>
    $(id).addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !scanning) $("btnScan").click();
    }));
  ["inpCidrs", "inpPorts", "inpThreads2", "inpTimeout2"].forEach((id) =>
    $(id).addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !scanning) $("btnInternal").click();
    }));

  /* 灯箱 */
  $("lightboxClose").addEventListener("click", closeLightbox);
  $("lightboxMask").addEventListener("click", closeLightbox);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeLightbox(); closeDashModal(); return; }
    /* 快捷键：⌘1/2/3 切页、⌘K 聚焦日志 */
    if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey) {
      const k = e.key;
      if (k === "1") { e.preventDefault(); switchPage("scan"); }
      else if (k === "2") { e.preventDefault(); switchPage("internal"); }
      else if (k === "3") { e.preventDefault(); switchPage("history"); }
      else if (k.toLowerCase() === "k") {
        e.preventDefault();
        $("consoleCard").classList.remove("collapsed");
        const c = $("console");
        c.scrollTop = c.scrollHeight;
      }
    }
  });

  /* 看板弹窗 */
  $("dashModalClose").addEventListener("click", closeDashModal);
  $("dashModalMask").addEventListener("click", closeDashModal);
  $("dashModalMax").addEventListener("click", () => {
    const body = document.querySelector(".modal-body");
    body.classList.toggle("fullscreen");
    $("dashModalMax").textContent = body.classList.contains("fullscreen") ? "还原" : "全屏";
  });

  window.addEventListener("pywebviewready", init);
}

bindUI();
