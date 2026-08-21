#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网站首页截图模块（Playwright 异步 API + Chromium）

设计要点：
  - Python 3.14 的 sync_api 在多线程下事件循环会被关闭，
    因此用 单工作线程 + asyncio + async_playwright 的组合
  - 一个浏览器实例，多页面并发（信号量限 3），不占用端口扫描线程
  - 单站超时 20 秒；失败只记录错误，不影响扫描主流程
  - Playwright 未安装或 Chromium 缺失时自动降级为跳过截图
"""

import asyncio
import os
import queue
import sys
import threading
from pathlib import Path
from urllib.parse import urljoin

from scanner_app.core.platform_support import hidden_asyncio_subprocesses


if getattr(sys, "frozen", False):
    # scripts/build_windows.spec 将 Chromium 放到 Playwright 的内置浏览器目录。
    # 让冻结版优先从 _MEIPASS 中查找，而不是访问用户全局缓存。
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False

VIEWPORT = {"width": 1280, "height": 800}
PAGE_SETTLE_MS = 800   # domcontentloaded 后等待页面渲染的静态时延（提速截图，兼顾页面加载）
CONCURRENCY = 4        # 单浏览器内并发页面数


def _img_ext(b: bytes) -> str:
    """按魔数识别图片格式，选对 data URL 的 MIME"""
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if b[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if b[:4] == b"\x00\x00\x01\x00":
        return ".ico"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    head = b[:200].lstrip().lower()
    if head.startswith(b"<svg") or head.startswith(b"<?xml"):
        return ".svg"
    return ".png"


class ScreenshotPool:
    """异步截图池；submit() 入队，close() 等待全部完成后回收浏览器"""

    def __init__(self, on_done, timeout=20, out_dir="."):
        self.on_done = on_done           # 回调：{"ip","port","ok","path"/"error"}
        self.timeout = timeout
        self.out_dir = Path(out_dir)     # 截图保存目录（用绝对路径，避免 CWD 问题）
        self.tasks = queue.Queue()
        self.available = PLAYWRIGHT_OK
        self._launch_error = None
        self._thread = None

    def submit(self, ip: str, port: int, scheme: str):
        if not self.available:
            self.on_done({"ip": ip, "port": port, "ok": False,
                          "error": "Playwright/Chromium 不可用，已跳过截图"})
            return
        url = f"{scheme}://{ip}:{port}/"
        self.tasks.put((ip, port, url))

    def start(self):
        if not self.available:
            return
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self):
        # Playwright 会通过 asyncio 启动 Node 驱动和 Chromium。Windows
        # 的窗口版 EXE 没有控制台，但未设置 creationflags 的子进程仍可能
        # 短暂弹出 cmd，因此把隐藏策略限定在这个截图工作线程内。
        with hidden_asyncio_subprocesses():
            asyncio.run(self._run_all())

    async def _run_all(self):
        browser = None
        if PLAYWRIGHT_OK:
            try:
                self._pw = await async_playwright().start()
                browser = await self._pw.chromium.launch(headless=True)
            except Exception as e:  # Chromium 未安装等
                self.available = False
                self._launch_error = repr(e)
        else:
            self.available = False

        sem = asyncio.Semaphore(CONCURRENCY)
        pending = []

        async def handle(task):
            ip, port, url = task
            async with sem:
                if browser is None:
                    self.on_done({"ip": ip, "port": port, "ok": False,
                                  "error": f"浏览器启动失败：{self._launch_error}"})
                    return
                path = str(self.out_dir / f"{ip}_{port}.png")
                ok, err, fav = await self._shoot(browser, url, path)
                fav_name = None
                if fav is not None:
                    fbytes, fext = fav
                    fav_name = f"{ip}_{port}_icon{fext}"
                    try:
                        (self.out_dir / fav_name).write_bytes(fbytes)
                    except OSError:
                        fav_name = None
                self.on_done({"ip": ip, "port": port, "ok": ok,
                              "path": f"{ip}_{port}.png" if ok else None,
                              "favicon": fav_name, "error": err})

        while True:
            try:
                item = self.tasks.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue
            if item is None:  # close() 的哨兵
                break
            pending.append(asyncio.create_task(handle(item)))

        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if browser:
            await browser.close()
        if getattr(self, "_pw", None):
            await self._pw.stop()

    async def _shoot(self, browser, url: str, path: str):
        """截图 + 顺带抓 favicon；返回 (ok, err, favicon(bytes,ext) 或 None)"""
        page = await browser.new_page(viewport=VIEWPORT, ignore_https_errors=True)
        ok, err, fav = False, "", None
        try:
            await page.goto(url, timeout=self.timeout * 1000,
                            wait_until="domcontentloaded")
            await page.wait_for_timeout(PAGE_SETTLE_MS)
            await page.screenshot(path=path, timeout=self.timeout * 1000)
            ok = True
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        if ok:
            fav = await self._grab_favicon(page)
        await page.close()
        return ok, err, fav

    async def _grab_favicon(self, page):
        """按 link[rel*=icon] → /favicon.ico 顺序抓站点图标；返回 (bytes, ext) 或 None"""
        candidates = []
        try:
            el = await page.query_selector('link[rel*="icon"]')
            if el:
                href = await el.get_attribute("href")
                if href:
                    candidates.append(urljoin(page.url, href))
        except Exception:
            pass
        origin = "/".join(page.url.split("/")[:3])
        candidates.append(origin + "/favicon.ico")
        for u in candidates[:3]:
            try:
                resp = await page.request.get(u, fail_on_status_code=False, timeout=6000)
                if resp.ok:
                    body = await resp.body()
                    if body and len(body) < 256 * 1024:
                        return body, _img_ext(body)
            except Exception:
                continue
        return None

    def close(self):
        """等待队列中所有任务完成（含失败降级路径）"""
        if self._thread is None:
            self._drain_unstarted()
            return
        self.tasks.put(None)
        self._thread.join()
        if not self.available:
            self._drain_unstarted()

    def _drain_unstarted(self):
        while True:
            try:
                ip, port, _ = self.tasks.get_nowait()
            except queue.Empty:
                break
            self.on_done({"ip": ip, "port": port, "ok": False,
                          "error": "截图功能不可用，已跳过"})
