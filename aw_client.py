"""ActivityWatch 只读 HTTP 客户端（纯 stdlib，不引入第三方依赖）。

为什么"只读 + 只 GET"：

- PointLog 只需要**读** AW 的数据，从不写桶；
- 官方 REST 文档明确 aw-server(Python) 与 aw-server-rust 在 POST/query 出错行为上不一致
  （POST events 只接受 list、query 失败返回 500 而非 400 等），只走 GET 可同时兼容两者。

失败约定：一切网络/协议问题统一抛 `AwUnavailable`，路由层转 503、前端显示"未连接"。
ActivityWatch 没装、没启动、崩溃都**不影响** PointLog 的打卡 / 统计等既有功能。

时间约定：AW 存的是 UTC（RFC3339）；本模块只负责"带时区时间 → UTC 字符串"，
"某个时刻属于哪一天"由 activity.py 按项目的凌晨 4 点规则处理。
"""

import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:5600"
API_PREFIX = "/api/0"
DEFAULT_TIMEOUT = 5.0


class AwUnavailable(Exception):
    """连不上 ActivityWatch（未安装 / 未启动 / 地址错 / 超时 / 返回异常）。"""


def rfc3339(t: dt.datetime) -> str:
    """本地或任意带时区的时间 → AW 需要的 UTC RFC3339（…Z）。"""
    if t.tzinfo is None:
        t = t.astimezone()
    return t.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


class AwClient:
    """只读客户端：buckets / events。"""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, api_token: str | None = None,
                 timeout: float = DEFAULT_TIMEOUT):
        self.base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        self.api_token = (api_token or "").strip() or None
        self.timeout = float(timeout or DEFAULT_TIMEOUT)

    # ---------- 底层 ----------

    def _url(self, path: str, params: dict | None = None) -> str:
        url = f"{self.base_url}{API_PREFIX}/{path.lstrip('/')}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean)
        return url

    def _get_json(self, path: str, params: dict | None = None):
        req = urllib.request.Request(self._url(path, params), method="GET")
        req.add_header("Accept", "application/json")
        if self.api_token:                       # 老版本 AW 无鉴权；新版若启用 token 则带上
            req.add_header("Authorization", f"Bearer {self.api_token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:200]
            except OSError:
                pass
            raise AwUnavailable(f"HTTP {exc.code}（{path}）{detail}".strip()) from exc
        except OSError as exc:                   # URLError / 超时 / 拒绝连接 都是 OSError
            raise AwUnavailable(f"连接失败（{exc}）：{self.base_url}") from exc
        try:
            return json.loads(body or b"null")
        except json.JSONDecodeError as exc:
            raise AwUnavailable(f"返回内容不是 JSON（{path}）") from exc

    # ---------- 业务 ----------

    def buckets(self) -> dict:
        """全部桶的原始 dict：{bucket_id: {id, type, client, hostname, ...}}。"""
        raw = self._get_json("buckets/")
        return raw if isinstance(raw, dict) else {}

    def bucket_summaries(self) -> list[dict]:
        """整理成前端/聚合层好用的列表（只保留关心的字段）。"""
        out = []
        for bid, info in self.buckets().items():
            if not isinstance(info, dict):
                continue
            out.append({
                "id": str(info.get("id") or bid),
                "type": str(info.get("type") or ""),
                "client": str(info.get("client") or ""),
                "hostname": str(info.get("hostname") or ""),
            })
        out.sort(key=lambda b: (b["type"], b["id"]))
        return out

    def events(self, bucket_id: str, start: dt.datetime, end: dt.datetime,
               limit: int = -1) -> list:
        """某桶在 [start, end) 内的事件（AW 侧按 UTC 比较，返回含 timestamp/duration/data）。"""
        raw = self._get_json(f"buckets/{urllib.parse.quote(str(bucket_id))}/events",
                             {"start": rfc3339(start), "end": rfc3339(end), "limit": limit})
        if not isinstance(raw, list):
            raise AwUnavailable(f"事件返回格式异常（{bucket_id}）")
        return raw

    def ping(self) -> dict:
        """探活：不抛异常，返回 {connected, buckets, error}。"""
        try:
            n = len(self.buckets())
        except AwUnavailable as exc:
            return {"connected": False, "buckets": 0, "error": str(exc)}
        return {"connected": True, "buckets": n, "error": None}
