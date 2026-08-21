#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""靶场扫描核心逻辑（CLI 与 GUI 共用）

约定：
  - 过程信息一律通过 on_event(dict) 回调发出，本模块自身不做任何 print
  - cancel（threading.Event）置位后尽快停止，未执行的任务被丢弃，
    已在执行的任务最迟约 timeout 秒内自然结束
  - 返回结构化结果列表，并落盘 report.md / report.json / 各站 HTML 快照

事件类型：
  scan_start      {targets, port_start, port_end, total_ports, results_dir}
  target_start    {ip}
  ping            {ip, alive, latency_ms}
  progress        {ip, done, total}
  port_found      {ip, port, state, is_http, scheme, status, title, server, snapshot, ...}
  phase           {phase}                     # screenshots = 端口扫完等待截图
  screenshot_done {ip, port, ok, path, favicon, error}
  target_done     {ip, open_count, total, cancelled}
  scan_done       {results_dir, cancelled, open_total, screenshot_total}
  error           {message}
"""

import concurrent.futures
import html
import re
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from scanner_app.core.platform_support import (
    hidden_subprocess_kwargs,
    parse_ping_output,
    ping_command,
    resolve_output_dir,
    user_agent,
)

UA = user_agent()
MAX_BODY = 512 * 1024  # 首页最多抓取 512KB
DEFAULT_TARGETS = ["43.139.231.237", "43.139.149.11"]
# 复用 SSL 上下文（跳过证书校验，适用于靶场常见自签证书）
_SSL_CTX = ssl._create_unverified_context()
# 直连 opener（禁用系统代理，靶场扫描必须连目标本身；HTTPS 用跳过校验的 context）
_NO_PROXY_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=_SSL_CTX),
)


def ping_host(ip: str, timeout: float) -> dict:
    """ICMP 存活探测；命令参数和输出解析由平台适配层处理。"""
    cmd = ping_command(ip, timeout)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 3,
            **hidden_subprocess_kwargs(),
        )
    except subprocess.TimeoutExpired:
        return {"alive": False, "latency_ms": None}
    out = proc.stdout + proc.stderr
    if proc.returncode == 0:
        parsed = parse_ping_output(out)
        return {"alive": True, "latency_ms": parsed["latency_ms"]}
    return {"alive": False, "latency_ms": None}


def decode_body(body: bytes, content_type: str) -> str:
    """按 响应头 charset → meta charset → utf-8 → gbk 的顺序解码"""
    candidates = []
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    if m:
        candidates.append(m.group(1))
    meta = re.search(rb"""<meta[^>]+charset=["']?([\w-]+)""", body[:2048], re.I)
    if meta:
        candidates.append(meta.group(1).decode("ascii", "replace"))
    candidates += ["utf-8", "gbk"]
    for enc in candidates:
        try:
            return body.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


def extract_title(text: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()[:120]


def _http_result(scheme, status, headers, body, req_url, final_url):
    content_type = (headers.get("Content-Type") or "") if headers else ""
    text = decode_body(body, content_type)
    return {
        "is_http": True,
        "scheme": scheme,
        "status": status,
        "server": (headers.get("Server") or "") if headers else "",
        "content_type": content_type,
        "title": extract_title(text),
        "body_length": len(body),
        "redirected": final_url != req_url,
        "body": body,
    }


def fetch_http(ip: str, port: int, timeout: float) -> dict:
    """对开放端口先试 http 再试 https；非 HTTP 服务返回 is_http=False
    https 二次尝试用递减超时，避免非 HTTP 端口白等满一个完整 timeout；
    必须直连目标（禁用系统代理，否则代理会接管 127.0.0.1 等请求导致误判）"""
    last_err = ""
    for scheme in ("http", "https"):
        url = f"{scheme}://{ip}:{port}/"
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
        eff_timeout = timeout if scheme == "http" else max(0.3, timeout * 0.7)
        try:
            # 靶场常用自签证书已通过 HTTPSHandler(context) 跳过校验
            with _NO_PROXY_OPENER.open(req, timeout=eff_timeout) as resp:
                return _http_result(scheme, resp.status, resp.headers,
                                    resp.read(MAX_BODY), url, resp.url)
        except urllib.error.HTTPError as e:  # 4xx/5xx 也说明是 HTTP 服务
            try:
                body = e.read(MAX_BODY)
            except Exception:
                body = b""
            return _http_result(scheme, e.code, e.headers, body, url, url)
        except Exception as e:  # 连不上 / 超时 / 非 HTTP 协议
            last_err = f"{type(e).__name__}: {e}"
    return {"is_http": False, "error": last_err}


def scan_port(ip: str, port: int, timeout: float, outdir: Path, cancel: threading.Event) -> dict:
    """单个端口：TCP 连接探测 → 开放则抓首页并保存 HTML 快照"""
    if cancel.is_set():
        return {"state": "cancelled", "port": port}
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            pass
    except OSError as e:
        return {"state": "closed", "port": port, "detail": type(e).__name__}

    info = fetch_http(ip, port, timeout)
    result = {"state": "open", "port": port, **info}
    if info.get("is_http"):
        snap = outdir / f"{ip}_{port}.html"
        snap.write_bytes(info["body"])
        result["snapshot"] = snap.name
    result.pop("body", None)
    return result


def scan_target(ip: str, ports: range, timeout: float, threads: int,
                outdir: Path, on_event, cancel: threading.Event) -> dict:
    on_event({"type": "target_start", "ip": ip})
    ping = ping_host(ip, timeout)
    on_event({"type": "ping", "ip": ip, **ping})

    results = {"ip": ip, "ping": ping, "ports": {}}
    total = len(ports)
    cancelled = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as ex:
        futmap = {ex.submit(scan_port, ip, p, timeout, outdir, cancel): p for p in ports}
        try:
            for i, fut in enumerate(concurrent.futures.as_completed(futmap), 1):
                if cancel.is_set():
                    cancelled = True
                    break
                port = futmap[fut]
                try:
                    r = fut.result()
                except Exception as e:
                    r = {"state": "error", "port": port, "error": repr(e)}
                results["ports"][str(port)] = r
                if r["state"] == "open":
                    on_event({"type": "port_found", "ip": ip, **r})
                on_event({"type": "progress", "ip": ip, "done": i, "total": total})
        finally:
            if cancelled:
                ex.shutdown(wait=False, cancel_futures=True)

    open_count = sum(1 for r in results["ports"].values() if r["state"] == "open")
    results["open_count"] = open_count
    on_event({"type": "target_done", "ip": ip, "open_count": open_count,
              "total": total, "cancelled": cancelled})
    return results


def write_reports(results: list, outdir: Path, port_start: int, port_end: int,
                  threads: int, timeout: float, ports=None, duration=None) -> None:
    """兼容保留：转发到 reports.write_public_report"""
    from scanner_app.core import reports
    reports.write_public_report(results, outdir, port_start, port_end, threads, timeout,
                                ports, duration)


def run_scan(targets, port_start=8000, port_end=8099, timeout=2.0, threads=100,
             output="", on_event=None, cancel=None, screenshots=True, ports=None) -> list:
    """执行一次完整扫描；targets 为 IP 字符串列表。
    支持两种端口模式：ports 列表（显式端口集合）或 port_start/port_end 范围。"""
    base_on_event = on_event or (lambda evt: None)
    cancel = cancel if cancel is not None else threading.Event()
    scan_t0 = time.time()
    # 去重并保持顺序（先取原参数，再重建，避免生成器迭代到空列表）
    seen = set()
    raw_targets = [t.strip() for t in targets if t.strip()]
    targets = []
    for t in raw_targets:
        if t not in seen:
            seen.add(t)
            targets.append(t)

    outdir = resolve_output_dir(output, "public")
    outdir.mkdir(parents=True, exist_ok=True)
    if ports:
        ports = sorted(set(int(p) for p in ports if str(p).strip().isdigit()))
    else:
        ports = range(port_start, port_end + 1)

    # 截图池：发现 HTTP 站点后异步截图（顺带抓 favicon），完成经 screenshot_done 事件上报
    shot_map = {}
    fav_map = {}
    pool = None
    if screenshots:
        from scanner_app.core import screenshot as shot_mod
        if shot_mod.PLAYWRIGHT_OK:
            def on_shot_done(info):
                if info["ok"]:
                    shot_map[(info["ip"], info["port"])] = info["path"]
                if info.get("favicon"):
                    fav_map[(info["ip"], info["port"])] = info["favicon"]
                base_on_event({"type": "screenshot_done", **info})

            pool = shot_mod.ScreenshotPool(on_done=on_shot_done, out_dir=outdir)
            pool.start()
        else:
            base_on_event({"type": "error", "message": "Playwright 未安装，本次扫描跳过截图"})

    def wrapped_on_event(evt):
        if evt["type"] == "port_found" and evt.get("is_http") and pool is not None:
            pool.submit(evt["ip"], evt["port"], evt["scheme"])
        base_on_event(evt)

    base_on_event({"type": "scan_start", "targets": targets, "port_start": port_start,
                   "port_end": port_end, "total_ports": len(ports),
                   "ports": list(ports) if isinstance(ports, list) else None,
                   "results_dir": str(outdir)})

    all_results = []
    for ip in targets:
        if cancel.is_set():
            break
        try:
            all_results.append(scan_target(ip, ports, timeout, threads,
                                           outdir, wrapped_on_event, cancel))
        except Exception as e:
            base_on_event({"type": "error", "message": f"扫描 {ip} 时出错：{e!r}"})

    if pool is not None:
        base_on_event({"type": "phase", "phase": "screenshots"})
        pool.close()  # 等待全部截图任务结束

    # 截图结果并入端口数据（截图在端口扫描之后完成，需在此回填）
    for t in all_results:
        for pr in t["ports"].values():
            fn = shot_map.get((t["ip"], pr.get("port")))
            if fn:
                pr["screenshot"] = fn
            fv = fav_map.get((t["ip"], pr.get("port")))
            if fv:
                pr["favicon"] = fv

    if all_results:  # 即使中途取消，也把已拿到的结果落盘
        write_reports(all_results, outdir, port_start, port_end, threads, timeout,
                      ports if isinstance(ports, list) else None,
                      round(time.time() - scan_t0, 1))

    open_total = sum(t["open_count"] for t in all_results)
    base_on_event({"type": "scan_done", "results_dir": str(outdir),
                   "cancelled": cancel.is_set(), "open_total": open_total,
                   "screenshot_total": len(shot_map),
                   "duration": round(time.time() - scan_t0, 1)})
    return all_results
