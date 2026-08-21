#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""截图运行时回归测试：确认完整 Chromium 能访问 HTTP 页面并产出 PNG。"""

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from scanner_app.core import screenshot


class _FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = (
            b"<html><head><title>Screenshot fixture</title></head>"
            b"<body><h1>VLUN</h1></body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


@unittest.skipUnless(
    screenshot.SCREENSHOT_AVAILABLE,
    f"截图运行时不可用：{screenshot.SCREENSHOT_UNAVAILABLE_REASON}",
)
class ScreenshotRuntimeTests(unittest.TestCase):
    def test_pool_captures_http_fixture(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            test_root = Path(".artifacts/test-shots")
            test_root.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix="screenshot-", dir=test_root) as temp:
                events = []
                pool = screenshot.ScreenshotPool(events.append, timeout=15, out_dir=Path(temp))
                pool.start()
                pool.submit("127.0.0.1", server.server_port, "http")
                pool.close()

                self.assertEqual(len(events), 1)
                self.assertTrue(events[0]["ok"], events[0])
                output = Path(temp) / f"127.0.0.1_{server.server_port}.png"
                self.assertGreater(output.stat().st_size, 1000)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
