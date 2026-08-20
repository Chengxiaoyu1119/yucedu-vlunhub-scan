#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""靶场扫描 GUI 入口（pywebview，支持 macOS / Windows）双模式版

启动：python3 range_gui.py
模式：公网 Web 靶场（端口递增扫描 + 首页截图）/ 内网穿透靶场（存活 + 无凭据 OS 判断）
通信：JS 侧定时轮询 poll_events() 拉取事件，避免跨线程调用问题
"""

import base64
import ipaddress
import json
import queue
import re
import sys
import threading
import webbrowser
from pathlib import Path

try:
    import webview
except ImportError:  # 允许 CLI/静态测试在未安装 GUI 依赖时继续导入模块
    webview = None

import internal_scanner
from platform_support import (
    GUI_DIR,
    RESULTS_ROOT,
    configure_console,
    delete_path,
    notify as platform_notify,
    open_path as platform_open_path,
    play_sound as platform_play_sound,
    show_error,
)
import scanner_core

IMG_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".ico": "image/x-icon",
            ".svg": "image/svg+xml", ".gif": "image/gif"}


class Api:
    """暴露给 JS 的接口（JS 侧通过 pywebview.api.xxx() 调用）"""

    def __init__(self):
        self.evt_queue = queue.Queue()
        self.scan_thread = None   # 公网/内网共用一个"当前扫描"槽位
        self.cancel = threading.Event()

    # ---------- 配置 ----------

    def get_config(self):
        return {
            "targets": ", ".join(scanner_core.DEFAULT_TARGETS),
            "port_start": 8000,
            "port_end": 8099,
            "threads": 100,
            "timeout": 2.0,
        }

    def get_internal_config(self):
        return {
            "cidrs": ", ".join(internal_scanner.DEFAULT_CIDRS),
            "ports": ", ".join(map(str, internal_scanner.DEFAULT_PORTS)),
            "threads": 64,   # 内网扫描并发下调：508 IP × 8 端口场景下降低 CPU/网络压力
            "timeout": 1.0,
        }

    # ---------- 扫描控制 ----------

    def _busy(self):
        return self.scan_thread is not None and self.scan_thread.is_alive()

    def start_scan(self, targets, port_start, port_end, threads, timeout, screenshots=True, ports=None):
        if self._busy():
            return {"ok": False, "error": "扫描正在进行中，请先停止"}
        # 目标解析：支持 IP / hostname / CIDR 网段混合输入（CIDR 展开为 IP 列表）
        ip_list = []
        bad = []
        for t in str(targets).split(","):
            t = t.strip()
            if not t:
                continue
            if "/" in t:
                try:
                    net = ipaddress.ip_network(t, strict=False)
                    ip_list.extend(str(h) for h in net.hosts())
                except ValueError:
                    bad.append(t)
            else:
                ip_list.append(t)
        if bad:
            return {"ok": False, "error": f"网段格式不合法：{', '.join(bad)}"}
        # 去重并保持顺序
        seen = set()
        uniq = []
        for t in ip_list:
            if t not in seen:
                seen.add(t)
                uniq.append(t)
        ip_list = uniq
        if not ip_list:
            return {"ok": False, "error": "目标 IP 不能为空"}
        bad = [t for t in ip_list if not re.fullmatch(r"[\w.-]+", t)]
        if bad:
            return {"ok": False, "error": f"目标格式不合法：{', '.join(bad)}"}
        # 端口列表（可选）：显式端口集合，优先级高于范围
        port_list = None
        if ports:
            try:
                port_list = sorted({int(p) for p in re.split(r"[,，\s]+", str(ports)) if p.strip()})
            except ValueError:
                return {"ok": False, "error": "端口列表格式不合法（应为逗号分隔数字）"}

        self.evt_queue = queue.Queue()
        self.cancel = threading.Event()

        def worker():
            try:
                scanner_core.run_scan(
                    targets=ip_list,
                    port_start=int(port_start),
                    port_end=int(port_end),
                    timeout=float(timeout),
                    threads=int(threads),
                    on_event=lambda evt: self.evt_queue.put(evt),
                    cancel=self.cancel,
                    screenshots=bool(screenshots),
                    ports=port_list,
                )
            except Exception as e:
                self.evt_queue.put({"type": "error", "message": repr(e), "fatal": True})

        self.scan_thread = threading.Thread(target=worker, daemon=True)
        self.scan_thread.start()
        return {"ok": True}

    def start_internal_scan(self, cidrs, ports, threads, timeout):
        if self._busy():
            return {"ok": False, "error": "扫描正在进行中，请先停止"}
        seen = set()
        cidr_list = []
        bad_cidrs = []
        for c in str(cidrs).split(","):
            c = c.strip()
            if not c or c in seen:
                continue
            try:
                ipaddress.ip_network(c, strict=False)
            except ValueError:
                bad_cidrs.append(c)
                continue
            seen.add(c)
            cidr_list.append(c)
        if bad_cidrs:
            return {"ok": False, "error": f"网段格式不合法：{', '.join(bad_cidrs)}"}
        if not cidr_list:
            return {"ok": False, "error": "网段不能为空"}
        try:
            port_list = sorted({int(p) for p in re.split(r"[,，\s]+", str(ports)) if p.strip()})
        except ValueError:
            return {"ok": False, "error": "端口列表格式不合法（应为逗号分隔数字）"}

        self.evt_queue = queue.Queue()
        self.cancel = threading.Event()

        def worker():
            try:
                internal_scanner.run_internal_scan(
                    cidrs=cidr_list,
                    ports=port_list,
                    timeout=float(timeout),
                    threads=int(threads),
                    on_event=lambda evt: self.evt_queue.put(evt),
                    cancel=self.cancel,
                )
            except Exception as e:
                self.evt_queue.put({"type": "error", "message": repr(e), "fatal": True})

        self.scan_thread = threading.Thread(target=worker, daemon=True)
        self.scan_thread.start()
        return {"ok": True}

    def stop_scan(self):
        self.cancel.set()
        return {"ok": True}

    def poll_events(self, limit=60):
        """分批返回事件队列，避免一次回传大量事件导致前端批量渲染卡顿"""
        events = []
        try:
            for _ in range(int(limit)):
                events.append(self.evt_queue.get_nowait())
        except queue.Empty:
            pass
        return events

    def is_scanning(self):
        return {"scanning": self._busy()}

    # ---------- 截图与报告 ----------

    def screenshot_data(self, results_dir, filename):
        """返回 base64 data URL 供界面显示（截图/图标；仅限 scan_results 内的图片）"""
        try:
            d = Path(results_dir).resolve()
            d.relative_to(RESULTS_ROOT.resolve())
            f = (d / Path(str(filename)).name).resolve()
            f.relative_to(RESULTS_ROOT.resolve())
            mime = IMG_MIME.get(f.suffix.lower())
            if not mime or not f.is_file():
                return {"error": "文件不存在"}
        except (ValueError, OSError):
            return {"error": "路径不合法"}
        b64 = base64.b64encode(f.read_bytes()).decode("ascii")
        return {"data": f"data:{mime};base64,{b64}"}

    def _safe_under_results(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(RESULTS_ROOT.resolve())
            return True
        except (ValueError, OSError):
            return False

    def open_report(self, path):
        """用默认浏览器打开 report.html"""
        f = Path(path)
        if not self._safe_under_results(f) or f.name != "report.html" or not f.is_file():
            return {"ok": False, "error": "报告文件不存在"}
        webbrowser.open(f.resolve().as_uri())
        return {"ok": True}

    # ---------- 系统联动 ----------

    def notify(self, title, message):
        """桌面提醒（macOS 使用通知中心，Windows 使用系统消息）。"""
        platform_notify(title, message)
        return {"ok": True}

    def play_sound(self):
        """扫描完成提示音（静默失败，不阻塞扫描线程）。"""
        platform_play_sound()
        return {"ok": True}

    def open_url(self, url):
        if str(url).startswith(("http://", "https://")):
            webbrowser.open(str(url))
            return {"ok": True}
        return {"ok": False, "error": "仅支持 http/https 链接"}

    def open_path(self, path):
        """在系统文件管理器中打开目录；只允许 scan_results 之内。"""
        if not self._safe_under_results(Path(path)):
            return {"ok": False, "error": "路径不在 scan_results 目录内"}
        return {"ok": platform_open_path(Path(path))}

    def delete_history(self, path):
        """删除一条历史记录（仅限 scan_results 直接子目录）"""
        try:
            p = Path(path).resolve()
            root = RESULTS_ROOT.resolve()
            p.relative_to(root)
            if p.parent != root:
                return {"ok": False, "error": "只能删除 scan_results 下的记录目录"}
            if not p.is_dir():
                return {"ok": False, "error": "目录不存在或已被删除"}
        except (ValueError, OSError):
            return {"ok": False, "error": "路径不合法"}
        ok, error = delete_path(p)
        if not ok:
            return {"ok": False, "error": f"删除失败：{error}"}
        return {"ok": True}

    # ---------- 历史记录 ----------

    def get_report_data(self, path):
        """读取历史记录的 report.json，归一化为前端图表可直接消费的数据"""
        if not self._safe_under_results(Path(path)):
            return {"ok": False, "error": "路径不在 scan_results 目录内"}
        f = Path(path) / "report.json"
        if not f.is_file():
            return {"ok": False, "error": "report.json 不存在"}
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            return {"ok": False, "error": f"读取失败：{e}"}

        if isinstance(data, dict) and data.get("mode") == "internal":
            hosts = [{"ip": h.get("ip"), "via": h.get("via"),
                      "ttl": h.get("ttl"), "os_guess": h.get("os_guess", "未知"),
                      "open_ports": h.get("open_ports", [])}
                     for h in data.get("hosts", []) if h.get("alive")]
            return {"ok": True, "kind": "internal", "hosts": hosts}

        if isinstance(data, list):
            ports = []
            for t in data:
                for r in (t.get("ports") or {}).values():
                    if r.get("state") == "open":
                        ports.append({"ip": t.get("ip"), "port": r.get("port"),
                                      "is_http": bool(r.get("is_http")),
                                      "scheme": r.get("scheme", ""),
                                      "status": r.get("status", 0),
                                      "title": r.get("title", ""),
                                      "server": r.get("server", "")})
            return {"ok": True, "kind": "public", "ports": ports}

        return {"ok": False, "error": "无法识别的 report.json 格式"}

    def get_history(self):
        items = []
        if RESULTS_ROOT.exists():
            for d in sorted(RESULTS_ROOT.iterdir(), reverse=True):
                if len(items) >= 30:
                    break
                rpt = d / "report.json"
                if not (d.is_dir() and rpt.exists()):
                    continue
                try:
                    data = json.loads(rpt.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                m = re.fullmatch(r"(?:internal_)?(\d{8})_(\d{6})", d.name)
                if m:
                    time_str = (f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]} "
                                f"{m.group(2)[:2]}:{m.group(2)[2:4]}:{m.group(2)[4:]}")
                else:
                    time_str = d.name
                if isinstance(data, dict) and data.get("mode") == "internal":
                    items.append({
                        "name": d.name, "path": str(d), "time": time_str, "kind": "internal",
                        "targets": data.get("cidrs", []),
                        "summary": (f"存活 {data.get('counts', {}).get('存活主机', 0)} 台 · "
                                    f"Linux {data.get('counts', {}).get('Linux', 0)} · "
                                    f"Windows {data.get('counts', {}).get('Windows', 0)}"),
                        "report_html": (d / "report.html").is_file(),
                    })
                elif isinstance(data, list):
                    open_total = sum(t.get("open_count", 0) for t in data)
                    items.append({
                        "name": d.name, "path": str(d), "time": time_str, "kind": "public",
                        "targets": [t.get("ip", "?") for t in data],
                        "summary": f"开放端口 {open_total} 个",
                        "report_html": (d / "report.html").is_file(),
                    })
        return items


def set_dock_icon():
    """用 pyobjc 设置 macOS Dock 图标（GUI 启动后调用）"""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication, NSImage
        img = NSImage.alloc().initWithContentsOfFile_(str(GUI_DIR / "app_icon.png"))
        if img is not None:
            NSApplication.sharedApplication().setApplicationIconImage_(img)
    except Exception:
        pass  # 图标设置失败不影响主功能


def main():
    configure_console()
    if webview is None:
        message = "缺少 pywebview，请重新构建 Windows EXE 或安装项目依赖。"
        if getattr(sys, "frozen", False):
            show_error("靶场扫描助手", message)
        raise SystemExit(message)
    api = Api()
    try:
        webview.create_window(
            title="靶场扫描助手",
            url=str(GUI_DIR / "index.html"),
            js_api=api,
            width=1160,
            height=780,
            min_size=(1000, 660),
            background_color="#f5f5f7",
        )
        webview.start(set_dock_icon)
    except Exception as exc:
        message = f"桌面窗口启动失败：{exc!r}"
        if getattr(sys, "frozen", False):
            show_error("靶场扫描助手", message)
        raise


if __name__ == "__main__":
    main()
