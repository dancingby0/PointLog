"""AW 客户端测试：本地假 HTTP 服务验证请求形态与错误处理（不依赖真实 ActivityWatch）。"""

import datetime as dt
import json
import socket
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import aw_client


class _Handler(BaseHTTPRequestHandler):
    routes = {}            # path -> (status, payload)
    seen = []              # ["/api/0/...?query"]
    auth = []              # Authorization 头

    def do_GET(self):
        _Handler.seen.append(self.path)
        _Handler.auth.append(self.headers.get("Authorization"))
        path, _, _query = self.path.partition("?")
        status, payload = _Handler.routes.get(path, (404, {"error": "not found"}))
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):          # 静音
        pass


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class AwClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        _Handler.routes = {}
        _Handler.seen = []
        _Handler.auth = []
        self.base = f"http://127.0.0.1:{self.port}"
        self.client = aw_client.AwClient(self.base, timeout=2)

    # ---------- 正常路径 ----------

    def test_bucket_summaries_and_ping(self):
        _Handler.routes["/api/0/buckets/"] = (200, {
            "aw-watcher-window_pc": {"id": "aw-watcher-window_pc", "type": "currentwindow",
                                     "client": "aw-watcher-window", "hostname": "pc"},
            "aw-watcher-web-chrome": {"id": "aw-watcher-web-chrome", "type": "web.tab.current",
                                      "client": "aw-watcher-web", "hostname": "pc"},
        })
        summaries = self.client.bucket_summaries()
        self.assertEqual([b["type"] for b in summaries], ["currentwindow", "web.tab.current"])
        self.assertEqual(summaries[0]["hostname"], "pc")

        ping = self.client.ping()
        self.assertTrue(ping["connected"])
        self.assertEqual(ping["buckets"], 2)
        self.assertIsNone(ping["error"])

    def test_events_passes_utc_rfc3339_window(self):
        _Handler.routes["/api/0/buckets/b1/events"] = (200, [
            {"timestamp": "2026-10-11T01:00:00Z", "duration": 60, "data": {"app": "Code"}},
        ])
        start = dt.datetime(2026, 10, 11, 4, 0).astimezone()
        end = start + dt.timedelta(days=1)
        events = self.client.events("b1", start, end)
        self.assertEqual(len(events), 1)

        query = urllib.parse.parse_qs(_Handler.seen[-1].partition("?")[2])
        self.assertEqual(query["start"][0], aw_client.rfc3339(start))
        self.assertEqual(query["end"][0], aw_client.rfc3339(end))
        self.assertEqual(query["limit"][0], "-1")
        self.assertTrue(query["start"][0].endswith("Z"))

    def test_bucket_id_appears_in_path(self):
        _Handler.routes["/api/0/buckets/aw-watcher-web-chrome/events"] = (200, [])
        events = self.client.events("aw-watcher-web-chrome",
                                    dt.datetime.now(), dt.datetime.now())
        self.assertEqual(events, [])
        self.assertTrue(_Handler.seen[-1].startswith(
            "/api/0/buckets/aw-watcher-web-chrome/events"))

    def test_api_token_is_sent_when_configured(self):
        _Handler.routes["/api/0/buckets/"] = (200, {})
        aw_client.AwClient(self.base, api_token="secret", timeout=2).buckets()
        self.assertEqual(_Handler.auth[-1], "Bearer secret")

    def test_no_token_header_by_default(self):
        _Handler.routes["/api/0/buckets/"] = (200, {})
        self.client.buckets()
        self.assertIsNone(_Handler.auth[-1])

    # ---------- 失败路径 ----------

    def test_http_error_becomes_unavailable(self):
        _Handler.routes["/api/0/buckets/missing/events"] = (404, {"error": "no bucket"})
        with self.assertRaises(aw_client.AwUnavailable) as ctx:
            self.client.events("missing", dt.datetime.now(), dt.datetime.now())
        self.assertIn("404", str(ctx.exception))

    def test_server_error_becomes_unavailable(self):
        _Handler.routes["/api/0/buckets/"] = (500, {"error": "boom"})
        with self.assertRaises(aw_client.AwUnavailable):
            self.client.buckets()
        self.assertFalse(self.client.ping()["connected"])

    def test_non_json_body_becomes_unavailable(self):
        _Handler.routes["/api/0/buckets/"] = (200, b"<html>nope</html>")
        with self.assertRaises(aw_client.AwUnavailable) as ctx:
            self.client.buckets()
        self.assertIn("JSON", str(ctx.exception))

    def test_connection_refused_is_unavailable(self):
        client = aw_client.AwClient(f"http://127.0.0.1:{_free_port()}", timeout=0.5)
        ping = client.ping()
        self.assertFalse(ping["connected"])
        self.assertTrue(ping["error"])
        with self.assertRaises(aw_client.AwUnavailable):
            client.buckets()


class Rfc3339Test(unittest.TestCase):
    def test_converts_to_utc_z(self):
        local = dt.datetime(2026, 10, 11, 4, 0).astimezone()
        text = aw_client.rfc3339(local)
        self.assertTrue(text.endswith("Z"))
        self.assertEqual(dt.datetime.fromisoformat(text.replace("Z", "+00:00")),
                         local.astimezone(dt.timezone.utc))


if __name__ == "__main__":
    unittest.main()
