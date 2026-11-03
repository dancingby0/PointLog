"""PointLog 专注计时器（桌面悬浮窗，Windows，纯标准库 tkinter）。

三种形态（参考 patina 的收起方式）：

- **小球**：屏幕上一个小圆点，只显示"已专注 Xm"，最不打扰；单击展开成长条。
- **长条**：时间 + 标签 + 「详情」按钮；单击长条本体或点「详情」进入完整窗口。
- **完整**：时间、开始/暂停/继续/结束、标签快捷点选与自定义、上传、状态提示。

``Esc`` 逐级退回（完整 → 长条 → 小球 → 退出）；按住任意处可拖动，拖动不会误触发切换。

其他能力

- 正计时 + 暂停/继续/结束；暂停期间时长不增长（中断不算专注）。
- 标签来自档案的类别池（**可在设置页自行增删改名**），也能临时输入。
- 上传是显式动作（默认不上传），服务端保证幂等；服务不可用也能正常计时。
- 单实例：重复启动只保留一个悬浮窗。

用法

    python focus_timer.py                       # 连默认服务 http://127.0.0.1:5000
    python focus_timer.py --points 2            # 上传时用 2 点
    python focus_timer.py --view full           # 启动即展开完整窗口
    python focus_timer.py --list-labels         # 只打印当前档案的类别池

依赖：仅标准库（tkinter / urllib / json），无需 pip install。
"""

import argparse
import json
import time
import tkinter as tk
import urllib.error
import urllib.request
from tkinter import messagebox
from urllib.parse import quote

DEFAULT_BASE = "http://127.0.0.1:5000"
POLL_MS = 1000
SINGLE_INSTANCE_PORT = 5091        # 单实例锁：本地回环端口，被占用＝已有计时器在跑
SNAP_PX = 28                       # 拖到离屏幕边缘这么近就吸附
DRAG_THRESHOLD = 3                 # 位移超过这么多像素算拖动（不算点击）
DEFAULT_AUTO_SYNC_MIN = 15         # 默认自动同步间隔（分钟），0＝关闭


class ApiResult(dict):
    """接口返回体 + 状态码，便于区分"未登录(409)"与其它错误。"""

    @property
    def status(self):
        return self.get("_status")


def http_json(url: str, method: str = "GET", body=None, timeout: float = 5.0):
    """极简 JSON 请求；返回 (ok, data)。data 里带 _status（HTTP 状态码）。"""
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            payload = json.loads(raw) if raw else {}
            payload["_status"] = resp.status
            return True, ApiResult(payload)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read() or b"{}")
            detail = payload.get("error", "")
        except (json.JSONDecodeError, OSError):
            payload = {}
        payload["error"] = detail or f"HTTP {exc.code}"
        payload["_status"] = exc.code
        return False, ApiResult(payload)
    except OSError as exc:
        return False, ApiResult({"error": f"连不上 PointLog（{exc}）", "_status": None})

BG = "#1f2430"                     # 面板底色
BORDER = "#3a4256"
FG = "#e6e9f0"
MUTED = "#8b93a7"
ACCENT_TEXT = "#6ee7b7"
CHIP_BG = "#2b3242"
VIEWS = ("ball", "bar", "full")


def acquire_instance_lock():
    """单实例锁：返回持有中的 socket（保持绑定直到进程退出），已被占用则返回 None。

    用"绑定本地回环端口"而不是锁文件：进程被杀/崩溃后由系统自动释放，
    不会留下残留锁导致"再也起不来"。
    """
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
    except OSError:
        sock.close()
        return None
    return sock                      # 故意不 close：出了作用域也由进程生命周期决定


def http_json(url: str, method: str = "GET", body=None, timeout: float = 5.0):
    """极简 JSON 请求；返回 (ok, data)，网络问题不抛异常（交给界面提示）。"""
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        return True, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read() or b"{}").get("error", "")
        except (json.JSONDecodeError, OSError):
            pass
        return False, {"error": detail or f"HTTP {exc.code}"}
    except OSError as exc:
        return False, {"error": f"连不上 PointLog（{exc}）"}


def fmt_clock(seconds: int) -> str:
    """秒 → HH:MM:SS（完整窗口用）。"""
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def fmt_short(seconds: int) -> str:
    """秒 → "1h23m" / "45m"（小球与长条用，省地方）。"""
    total = int(round(max(0, seconds) / 60.0))
    if total <= 0:
        return "0m"
    h, m = divmod(total, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"



BG = "#1f2430"                     # 面板底色
BORDER = "#3a4256"
FG = "#e6e9f0"
MUTED = "#8b93a7"
ACCENT_TEXT = "#6ee7b7"
CHIP_BG = "#2b3242"
VIEWS = ("ball", "bar", "full")


class FocusTimer:
    """悬浮计时器：界面 + 状态机（与服务端会话保持一致）。"""

    def __init__(self, base_url: str, points: float = 1, labels=None,
                 wait_sec: float = 15.0, view: str = "ball",
                 auto_sync_min: float = DEFAULT_AUTO_SYNC_MIN):
        self.base = base_url.rstrip("/")
        self.points = points
        self.labels = list(labels or [])
        self.session = None          # 服务端返回的会话（含 id / state / segments）
        self.elapsed = 0             # 本地累计秒（显示用，与服务端在动作后对齐）
        self.label = ""
        self._drag = None
        self._press_at = None
        self._moved = False
        self._anchor = ("right", "bottom")     # 贴边方向：决定展开时往哪边长
        self.auto_sync_min = float(auto_sync_min or 0)
        self._next_sync = time.time() + self.auto_sync_min * 60 if self.auto_sync_min else 0
        self._build_ui(view or "ball")
        if wait_sec is not None and wait_sec > 0 and not self._server_ready(wait_sec):
            self.status.set("等不到 PointLog 服务；仍可计时，稍后会自动重试同步")
        elif wait_sec is not None:
            # 服务在：拉一次标签池，并把上次没传完的会话补传（短超时，失败不影响启动）
            self._sync_labels()
            if self.auto_sync_min:
                self._auto_sync(quiet=True)
        # wait_sec=None：明确"不联网"（测试用，避免对不可用地址等超时）


    # ---------- 服务 ----------

    def _server_ready(self, timeout: float) -> bool:
        """launcher 会同时拉起本窗口，服务可能就差几百毫秒：先等一会儿再报"连不上"。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            ok, _ = http_json(f"{self.base}/api/focus/current", timeout=1.0)
            if ok:
                return True
            time.sleep(0.4)
        return False

    def _sync_labels(self):
        """从服务端重取类别池（用户在设置页增删/改名后，展开窗口即可看到最新）。"""
        ok, data = http_json(f"{self.base}/api/tags/diary", timeout=2.0)
        if ok and isinstance(data.get("tags"), list):
            self.labels = list(data["tags"])
            self._render_chips()

    # ---------- 界面 ----------

    def _build_ui(self, view: str):
        self.root = tk.Tk()
        self.root.title("PointLog 专注计时")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)                 # 无边框，更像悬浮窗
        self.root.configure(bg=BG)
        self.root.geometry("+80+80")

        # 注意：StringVar/BooleanVar 必须先有 root（tkinter 需要默认根窗口），
        # 否则会抛 "Too early to create variable: no default root window"。
        self.status = tk.StringVar(value="就绪")
        self.time_var = tk.StringVar(value="00:00:00")
        self.label_var = tk.StringVar(value="未选标签")
        self.auto_upload = tk.BooleanVar(value=True)      # 默认开启：结束后自动上传
        self.view = tk.StringVar(value="ball")

        self.frames = {}
        self._build_ball()
        self._build_bar()
        self._build_full()

        self.root.bind("<Escape>", lambda _e: self._on_escape())
        self._apply_view(view)
        self.place_bottom_right()          # 默认停在屏幕右下角
        self._refresh_buttons()
        self._tick()

    def _build_ball(self):
        """小球：一个圆点 + 短短时长；单击展开成长条。"""
        frame = tk.Frame(self.root, bg=BG)
        self.ball = tk.Canvas(frame, width=58, height=58, bg=BG,
                              highlightthickness=0, cursor="hand2")
        self.ball.pack()
        self._ring = self.ball.create_oval(4, 4, 54, 54, fill=CHIP_BG, outline=BORDER, width=2)
        self._ring_text = self.ball.create_text(29, 29, text="0m", fill=FG,
                                               font=("Segoe UI", 10, "bold"))
        self._ring_dot = self.ball.create_oval(40, 8, 48, 16, fill="#4b5563", outline="")
        self._bind_drag(self.ball, click=self._on_ball_click)
        self.frames["ball"] = frame

    def _build_bar(self):
        """长条：时间 + 标签 + 「详情」按钮。"""
        frame = tk.Frame(self.root, bg=BG, padx=10, pady=5)
        self.bar_dot = tk.Label(frame, text="●", fg="#4b5563", bg=BG, font=("Segoe UI", 9))
        self.bar_dot.pack(side="left")
        self.bar_time = tk.Label(frame, textvariable=self.time_var, fg=FG, bg=BG,
                                 font=("Consolas", 13, "bold"))
        self.bar_time.pack(side="left", padx=(6, 0))
        self.bar_label = tk.Label(frame, textvariable=self.label_var, fg=ACCENT_TEXT, bg=BG,
                                  font=("Segoe UI", 9))
        self.bar_label.pack(side="left", padx=(8, 10))
        tk.Button(frame, text="详情", command=lambda: self._apply_view("full"), bd=0,
                  bg=CHIP_BG, fg="#c7d2fe", activebackground="#3a4256",
                  activeforeground="#fff", font=("Segoe UI", 8), padx=8, pady=1,
                  cursor="hand2").pack(side="left")
        tk.Button(frame, text="○", command=lambda: self._apply_view("ball"), bd=0,
                  bg=BG, fg=MUTED, activebackground=CHIP_BG, activeforeground="#fff",
                  font=("Segoe UI", 10), padx=4, cursor="hand2").pack(side="left", padx=(4, 0))
        tk.Button(frame, text="✕", command=self.quit, bd=0, bg=BG, fg=MUTED,
                  activebackground=CHIP_BG, activeforeground="#fff",
                  font=("Segoe UI", 9), padx=4, cursor="hand2").pack(side="left")
        self._bind_drag(frame)
        for widget in (self.bar_dot, self.bar_time, self.bar_label):
            self._bind_drag(widget)
        self.frames["bar"] = frame


    def _build_full(self):
        """完整窗口：时间、四个按钮、标签 chip + 自定义输入、上传、状态。"""
        wrap = tk.Frame(self.root, bg=BG, padx=12, pady=8)
        self.frames["full"] = wrap

        head = tk.Frame(wrap, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="专注", fg=MUTED, bg=BG, font=("Segoe UI", 10)).pack(side="left")
        for text, handler in (("✕", self.quit),
                              ("▭", lambda: self._apply_view("bar")),
                              ("○", lambda: self._apply_view("ball"))):
            tk.Button(head, text=text, command=handler, bd=0, bg=BG, fg=MUTED,
                      activebackground=CHIP_BG, activeforeground="#fff",
                      font=("Segoe UI", 10), padx=4, cursor="hand2",
                      ).pack(side="right", padx=(2, 0))
        self.dot = tk.Label(head, text="●", fg="#4b5563", bg=BG, font=("Segoe UI", 10))
        self.dot.pack(side="right", padx=6)

        tk.Label(wrap, textvariable=self.time_var, fg=FG, bg=BG,
                 font=("Consolas", 30, "bold")).pack(pady=(2, 0))
        tk.Label(wrap, textvariable=self.label_var, fg=ACCENT_TEXT, bg=BG,
                 font=("Segoe UI", 11)).pack()

        self.row = tk.Frame(wrap, bg=BG)
        self.row.pack(pady=8)
        self.btn_start = self._button(self.row, "开始", self.start, "#10b981")
        self.btn_pause = self._button(self.row, "暂停", self.pause, "#f59e0b")
        self.btn_resume = self._button(self.row, "继续", self.resume, "#3b82f6")
        self.btn_stop = self._button(self.row, "结束", self.stop, "#ef4444")

        self.tags_box = tk.Frame(wrap, bg=BG)
        self.tags_box.pack(fill="x")
        self._render_chips()

        entry_row = tk.Frame(wrap, bg=BG)
        entry_row.pack(fill="x", pady=(4, 0))
        self.tag_entry = tk.Entry(entry_row, bg=CHIP_BG, fg=FG, bd=0,
                                  insertbackground=FG, font=("Segoe UI", 9))
        self.tag_entry.pack(side="left", fill="x", expand=True, ipady=3)
        self.tag_entry.bind("<Return>", lambda _e: self.apply_label())

        foot = tk.Frame(wrap, bg=BG)
        foot.pack(fill="x", pady=(8, 0))
        tk.Checkbutton(foot, text="结束后自动上传", variable=self.auto_upload,
                       fg=MUTED, bg=BG, selectcolor=CHIP_BG,
                       activebackground=BG, activeforeground="#fff",
                       font=("Segoe UI", 9), bd=0).pack(side="left")
        self.btn_upload = self._button(foot, "上传", self.upload, "#6366f1", small=True)
        self.btn_upload.pack(side="right")

        sync_text = (f"自动同步：每 {self.auto_sync_min:g} 分钟"
                     if self.auto_sync_min else "自动同步：已关闭")
        tk.Label(wrap, text=sync_text, fg=MUTED, bg=BG,
                 font=("Segoe UI", 8), anchor="w").pack(fill="x", pady=(4, 0))
        tk.Label(wrap, textvariable=self.status, fg=MUTED, bg=BG,
                 font=("Segoe UI", 8), anchor="w").pack(fill="x", pady=(2, 0))

        self._bind_drag(wrap)          # 空白处拖动

    def _render_chips(self):
        """按当前标签池渲染快捷 chip（标签可能被用户在设置页改动，需可重绘）。"""
        if not hasattr(self, "tags_box"):
            return
        for child in self.tags_box.winfo_children():
            child.destroy()
        shown = self.labels[:6]
        for text in shown:
            chip = tk.Label(self.tags_box, text=text, fg="#c7d2fe", bg=CHIP_BG,
                            padx=6, pady=2, cursor="hand2", font=("Segoe UI", 9))
            chip.pack(side="left", padx=(0, 4), pady=2)
            chip.bind("<Button-1>", lambda _e, t=text: self.apply_label(t))
        if not shown:
            tk.Label(self.tags_box, text="（类别池是空的，可在设置页添加）", fg=MUTED,
                     bg=BG, font=("Segoe UI", 8)).pack(side="left")

    def _apply_view(self, name: str):
        """切换形态：只显示当前那个，并沿"贴边方向"展开（默认右下 → 向左上）。

        关键：记住切换前后的宽高，把贴住的那条边钉住，这样窗口不会"跳"到别处。
        """
        if name not in VIEWS:
            name = "ball"
        old_x, old_y = self.root.winfo_x(), self.root.winfo_y()
        old_w, old_h = self.root.winfo_width(), self.root.winfo_height()

        for key, frame in self.frames.items():
            if key != name:
                frame.pack_forget()
        self.frames[name].pack()
        self.root.update_idletasks()

        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()
        side_v, side_h = self._anchor

        x = old_x
        if side_v == "right":                 # 贴右边 → 向左长
            x = old_x + old_w - w if old_w > 1 else x
        y = old_y
        if side_h == "bottom":                # 贴底边 → 向上长
            y = old_y + old_h - h if old_h > 1 else y

        self.root.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
        self.view.set(name)

    # ---------- 屏幕贴边 ----------

    def _screen(self) -> tuple[int, int]:
        return self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def place_bottom_right(self, margin: int = 16):
        """初始位置：屏幕右下角（贴边；底部留一点余量避开任务栏/托盘）。"""
        self.root.update_idletasks()
        w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        sw, sh = self._screen()
        # 任务栏通常 40~48px、有些机器在右侧；这里用 56px 余量，既贴边又不被遮住
        x = max(0, sw - w - margin)
        y = max(0, sh - h - 56)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self._anchor = ("right", "bottom")

    def _snap_to_edges(self):
        """松手后：靠近哪条边就贴上去，并记下贴边方向（决定之后往哪边展开）。"""
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        sw, sh = self._screen()
        x, y = self.root.winfo_x(), self.root.winfo_y()

        side_v = "right" if (sw - (x + w)) <= max(SNAP_PX, sw - x - w) else "left"
        side_h = "bottom" if (sh - (y + h)) <= max(SNAP_PX, sh - y - h) else "top"

        nx, ny = x, y
        if (sw - (x + w)) <= SNAP_PX:          # 贴右
            nx, side_v = sw - w, "right"
        elif x <= SNAP_PX:                     # 贴左
            nx, side_v = 0, "left"
        if (sh - (y + h)) <= SNAP_PX:          # 贴下
            ny, side_h = sh - h, "bottom"
        elif y <= SNAP_PX:                     # 贴上
            ny, side_h = 0, "top"

        nx = max(0, min(nx, sw - w))
        ny = max(0, min(ny, sh - h))
        self.root.geometry(f"{w}x{h}+{nx}+{ny}")
        self._anchor = (side_v, side_h)

    def _on_ball_click(self):
        self._apply_view("bar")

    def _on_escape(self):
        """Esc 逐级退回：完整 → 长条 → 小球 → 退出。"""
        current = self.view.get()
        if current == "full":
            self._apply_view("bar")
        elif current == "bar":
            self._apply_view("ball")
        else:
            self.quit()

    def _button(self, parent, text, command, color, small=False):
        return tk.Button(parent, text=text, command=command, bd=0, bg=color, fg="white",
                         activebackground=color, activeforeground="white", cursor="hand2",
                         font=("Segoe UI", 9 if small else 10, "bold"),
                         padx=8 if small else 12, pady=2 if small else 5)

    # ---------- 拖动 / 点击区分 ----------

    def _bind_drag(self, widget, click=None):
        """按住可拖动窗口；没移动就算一次点击（click 回调）。"""
        widget.bind("<ButtonPress-1>", self._press)
        widget.bind("<B1-Motion>", self._on_drag)
        if click is not None:
            widget.bind("<ButtonRelease-1>", lambda _e, cb=click: self._release(cb))
        else:
            widget.bind("<ButtonRelease-1>", self._release)

    def _press(self, event):
        self._moved = False
        self._drag = (event.x_root - self.root.winfo_x(),
                      event.y_root - self.root.winfo_y())
        self._press_at = (event.x_root, event.y_root)

    def _on_drag(self, event):
        if not self._drag:
            return
        if self._press_at and (abs(event.x_root - self._press_at[0]) > 3
                               or abs(event.y_root - self._press_at[1]) > 3):
            self._moved = True
        dx, dy = self._drag
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def _release(self, click=None):
        moved = self._moved
        if click is not None and not moved:
            click()
        elif moved:
            self._snap_to_edges()          # 拖动结束 → 靠近边缘就吸附
        self._drag = None
        self._press_at = None
        self._moved = False

    # ---------- 自动同步 ----------

    def _auto_sync(self, quiet: bool = False):
        """把所有"已结束且未上传"的会话批量上传到点数系统（服务端幂等）。"""
        ok, data = http_json(f"{self.base}/api/focus/sync", "POST",
                             {"points": self.points}, timeout=3.0)
        if not ok:
            if not quiet:
                self.status.set(f"自动同步失败：{data.get('error')}")
            return 0
        count = int(data.get("count") or 0)
        if count:
            self.status.set(f"已自动同步 {count} 条专注记录到点数系统")
            self._refresh_buttons()
        elif not quiet:
            self.status.set("自动同步：没有待同步的记录")
        return count

    def _maybe_auto_sync(self):
        """按设定的间隔触发自动同步（在 _tick 里每秒检查）。"""
        if not self.auto_sync_min:
            return                              # 0＝关闭
        now = time.time()
        if self._next_sync and now < self._next_sync:
            return
        self._next_sync = now + self.auto_sync_min * 60   # 先重排，避免失败时每秒重试
        self._auto_sync()


    # ---------- 交互 ----------

    def apply_label(self, text=None):
        """设置标签（点选 chip 或输入框回车）；计时中也能改，上传时生效。"""
        self.label = (text if text is not None else self.tag_entry.get()).strip()[:40]
        self.label_var.set(self.label or "未选标签")
        return self.label

    def start(self):
        label = self.apply_label()
        ok, data = http_json(f"{self.base}/api/focus/sessions", "POST",
                             {"label": label, "points": self.points})
        if not ok:
            self.status.set(f"开始失败：{data.get('error')}")
            self._apply_view("full")          # 展开窗口，避免提示被藏在小球里
            return
        self.session = data
        self.elapsed = 0
        self.status.set("计时中…")
        self._refresh_buttons()

    def pause(self):
        self._act("pause", "已暂停")

    def resume(self):
        self._act("resume", "继续计时…")

    def stop(self):
        self._act("stop", "已结束")
        if self.auto_upload.get():
            self._auto_sync()          # 结束即同步（覆盖所有待同步会话，不止这一条）

    def _act(self, action, hint):
        if not self.session:
            self.status.set("还没有开始计时")
            return
        ok, data = http_json(f"{self.base}/api/focus/sessions/"
                             f"{quote(str(self.session['id']))}/{action}", "POST")
        if not ok:
            self.status.set(f"{hint}失败：{data.get('error')}")
            return
        self.session = data
        self.elapsed = int(data.get("elapsed_sec") or self.elapsed)
        self.status.set(f"{hint}（{data.get('elapsed_text', '')}）")
        self._refresh_buttons()

    def upload(self):
        if not self.session:
            self.status.set("还没有可上传的会话")
            return
        label = self.apply_label()
        ok, data = http_json(f"{self.base}/api/focus/sessions/"
                             f"{quote(str(self.session['id']))}/upload", "POST",
                             {"points": self.points, "label": label})
        if not ok:
            self.status.set(f"上传失败：{data.get('error')}")
            return
        self.session = data.get("session") or self.session
        entry = data.get("entry") or {}
        self.status.set(f"已上传：{entry.get('content', '')}（{entry.get('points')} 点）")
        self._refresh_buttons()

    def quit(self):
        running = bool(self.session and self.session.get("state") == "running")
        if running and not messagebox.askokcancel(
                "退出计时器", "计时还在进行，退出会结束当前会话（时长已存在 PointLog）。确定退出？"):
            return
        if running:
            http_json(f"{self.base}/api/focus/sessions/"
                      f"{quote(str(self.session['id']))}/stop", "POST")
        self.root.destroy()

    # ---------- 刷新 ----------

    def _refresh_buttons(self):
        state = (self.session or {}).get("state")
        for btn, show in ((self.btn_start, state in (None, "stopped")),
                          (self.btn_pause, state == "running"),
                          (self.btn_resume, state == "paused"),
                          (self.btn_stop, state in ("running", "paused"))):
            if show:
                btn.pack(side="left", padx=3)
            else:
                btn.pack_forget()
        color = {"running": "#10b981", "paused": "#f59e0b"}.get(state, "#4b5563")
        self.dot.configure(fg=color)
        self.bar_dot.configure(fg=color)
        self.ball.itemconfigure(self._ring_dot, fill=color)
        can_upload = state in ("paused", "stopped") and not (self.session or {}).get("entry_id")
        self.btn_upload.configure(state="normal" if can_upload else "disabled")

    def _tick(self):
        """本地每秒自增（不依赖网络）；与服务端对齐由各动作的返回完成。"""
        if (self.session or {}).get("state") == "running":
            self.elapsed += 1
        self.time_var.set(fmt_clock(self.elapsed))
        self.ball.itemconfigure(self._ring_text, text=fmt_short(self.elapsed))
        self._maybe_auto_sync()
        self.root.after(POLL_MS, self._tick)

    def run(self):
        self.root.mainloop()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PointLog 专注计时器（桌面悬浮窗）")
    parser.add_argument("--base-url", default=DEFAULT_BASE, help="PointLog 服务地址")
    parser.add_argument("--points", type=float, default=1, help="上传时使用的点数（默认 1）")
    parser.add_argument("--view", default="ball", choices=VIEWS,
                        help="启动时的形态（默认 ball 小球）")
    parser.add_argument("--list-labels", action="store_true", help="只打印当前档案的类别池")
    parser.add_argument("--wait", type=float, default=15.0,
                        help="启动时等待服务就绪的秒数（0＝不等待）")
    parser.add_argument("--auto-sync", type=float, default=DEFAULT_AUTO_SYNC_MIN,
                        metavar="MIN", help=f"每隔多少分钟自动同步到点数系统"
                                            f"（默认 {DEFAULT_AUTO_SYNC_MIN}，0＝关闭）")
    args = parser.parse_args(argv)

    labels = []
    ok, data = http_json(f"{args.base_url.rstrip('/')}/api/tags/diary")
    if ok and isinstance(data.get("tags"), list):
        labels = data["tags"]

    if args.list_labels:
        print("\n".join(labels))
        return 0

    try:
        lock = acquire_instance_lock()
        if lock is None:                       # 已有悬浮窗在跑：静默退出，不叠窗口
            print("PointLog 专注计时器已在运行（如需重开，请先关掉旧窗口）。")
            return 0
        FocusTimer(args.base_url, args.points, labels,
                   wait_sec=args.wait, view=args.view,
                   auto_sync_min=args.auto_sync).run()
        lock.close()
    except tk.TclError as exc:                 # 无图形环境
        print(f"无法创建窗口（{exc}）。请在桌面环境运行，或用 --list-labels 查看标签。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
