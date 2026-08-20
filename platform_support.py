#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨平台支持：项目路径、Ping/ARP 解析和桌面系统联动。

扫描核心只依赖这里暴露的稳定接口，避免把 macOS 命令散落在业务代码中。
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
GUI_DIR = PROJECT_ROOT / "gui"
RESULTS_ROOT = PROJECT_ROOT / "scan_results"


def default_results_dir(kind: str = "public") -> Path:
    """返回项目内的默认结果目录，避免依赖启动时的当前工作目录。"""
    prefix = "internal_" if kind == "internal" else ""
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return RESULTS_ROOT / f"{prefix}{stamp}"


def resolve_output_dir(output: str = "", kind: str = "public") -> Path:
    """解析 CLI/GUI 的输出目录；显式相对路径仍相对当前终端目录。"""
    if output:
        path = Path(output).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()
    return default_results_dir(kind)


def user_agent() -> str:
    """返回扫描请求使用的浏览器标识。"""
    if sys.platform == "darwin":
        return ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) RangeScanner/1.0")
    if os.name == "nt":
        return ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) RangeScanner/1.0")
    return "Mozilla/5.0 (X11; Linux x86_64) RangeScanner/1.0"


def configure_console() -> None:
    """让 Windows CLI 使用 UTF-8，避免报告依据中的特殊字符导致输出异常。"""
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def ping_command(ip: str, timeout: float) -> list[str]:
    """生成当前系统的单包 Ping 命令。"""
    timeout_ms = max(1, int(timeout * 1000))
    if os.name == "nt":
        # Windows: -n 为次数，-w 为单次等待毫秒数。
        return ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    # macOS: -c 为次数，-W 单位为毫秒；Linux 的 -W 单位为秒。
    binary = shutil.which("ping") or ("/sbin/ping" if sys.platform == "darwin" else "ping")
    wait = timeout_ms if sys.platform == "darwin" else max(1, int(timeout))
    return [binary, "-c", "1", "-W", str(wait), ip]


def parse_ping_output(output: str) -> dict:
    """解析 macOS/Linux/Windows Ping 输出中的 TTL 和时延。"""
    ttl_match = re.search(r"\bttl[=:\s]+(\d+)", output or "", re.I)
    # Windows 常见 time<1ms，macOS/Linux 常见 time=0.123 ms。
    latency_match = re.search(r"\btime\s*[=<]\s*([\d.]+)\s*ms", output or "", re.I)
    return {
        "ttl": int(ttl_match.group(1)) if ttl_match else None,
        "latency_ms": float(latency_match.group(1)) if latency_match else None,
    }


def parse_arp_output(output: str) -> dict[str, str]:
    """解析 macOS 与 Windows 的 arp -a 输出并统一为小写冒号 MAC。"""
    result: dict[str, str] = {}

    # macOS: ? (192.168.3.10) at aa:bb:cc:dd:ee:ff on en0
    for ip, mac in re.findall(
        r"\((\d{1,3}(?:\.\d{1,3}){3})\)\s+at\s+"
        r"((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})",
        output or "",
    ):
        result[ip] = mac.lower()

    # Windows: 192.168.3.10    aa-bb-cc-dd-ee-ff    dynamic
    for ip, mac in re.findall(
        r"\b(\d{1,3}(?:\.\d{1,3}){3})\s+"
        r"([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})\b",
        output or "",
    ):
        result[ip] = mac.replace("-", ":").lower()
    return result


def open_path(path: Path) -> bool:
    """用系统文件管理器打开目录或文件。"""
    try:
        resolved = str(path.resolve())
        if os.name == "nt":
            os.startfile(resolved)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", resolved], check=False)
        else:
            subprocess.run(["xdg-open", resolved], check=False)
        return True
    except (OSError, ValueError):
        return False


def notify(title: str, message: str) -> bool:
    """发送非阻塞桌面提醒；系统不支持时静默返回 False。"""
    title = str(title).replace('"', "'")[:60]
    message = str(message).replace('"', "'")[:200]
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
                check=False,
                timeout=5,
            )
            return True
        if os.name == "nt":
            # msg.exe 是 Windows 自带的当前会话提醒，失败时不影响扫描。
            user = os.environ.get("USERNAME") or "*"
            subprocess.Popen(
                ["msg", user, "/TIME:5", f"{title}: {message}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        binary = shutil.which("notify-send")
        if binary:
            subprocess.Popen([binary, title, message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    return False


def play_sound() -> bool:
    """播放完成提示音；失败时不阻塞主流程。"""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(
                ["afplay", "/System/Library/Sounds/Glass.aiff"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        if os.name == "nt":
            import winsound

            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return True
    except (ImportError, OSError, ValueError):
        pass
    return False


def delete_path(path: Path) -> tuple[bool, str]:
    """删除历史目录；macOS 优先移入废纸篓，其它平台直接删除。"""
    path = path.resolve()
    try:
        if sys.platform == "darwin":
            escaped = str(path).replace('"', '\\"')
            osa = f'tell application "Finder" to delete (POSIX file "{escaped}" as alias)'
            result = subprocess.run(
                ["osascript", "-e", osa],
                capture_output=True,
                timeout=20,
            )
            if result.returncode == 0 and not path.exists():
                return True, ""

        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        else:
            return False, "目录不存在或已被删除"
        return True, ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
