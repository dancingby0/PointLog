"""PointLog 专注计时器（桌面悬浮窗，Windows，纯标准库 tkinter）。

特点

- **悬浮置顶**：无边框、可拖动、始终置顶。关窗＝退出（会提示是否结束正在跑的会话）。
- **正计时 + 暂停/继续/结束**：暂停后时长不再增长（中断时间不算专注）。
- **标签**：点一下就用（画画 / 学习日语 / 学习英语 / 学数学 / 科研工作），也能自己输入。
- **可选上传**：默认**不上传**。勾"结束后自动上传"或手动点「上传」才写打卡记录，
  于是点数线 / 连续天数不会被计时器污染。服务端保证幂等（重复上传只更新那条记录）。
- **本地优先**：本地每秒自增显示，不依赖网络；上传失败会提示、会话仍在服务端。

用法

    python focus_timer.py                       # 连默认服务 http://127.0.0.1:5000
    python focus_timer.py --points 2            # 上传时用 2 点
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
DEFAULT_LABELS = ["画画", "学习日语", "学习英语", "学数学", "科研工作"]
SINGLE_INSTANCE_PORT = 5091        # 单实例锁：本地回环端口，被占用＝已有计时器在跑


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



class FocusTimer:
    """悬浮计时器：界面 + 状态机（与服务端会话保持一致）。"""

    def __init__(self, base_url: str, points: float = 1, labels=None,
                 wait_sec: float = 15.0):
        self.base = base_url.rstrip("/")
        self.points = points
        self.labels = list(labels or DEFAULT_LABELS)
        self.session = None          # 服务端返回的会话（含 id / state / segments）
        self.elapsed = 0             # 本地累计秒（显示用，与服务端在动作后对齐）
        self.label = ""
        self._drag = (0, 0)
        self._build_ui()
        if wait_sec > 0 and not self._server_ready(wait_sec):
            self.status.set("等不到 PointLog 服务；仍可计时，上传会失败")

    # ---------- 服务探活 ----------

    def _server_ready(self, timeout: float) -> bool:
        """launcher 会同时拉起本窗口，服务可能就差几百毫秒：先等一会儿再报"连不上"。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            ok, _ = http_json(f"{self.base}/api/focus/current", timeout=1.0)
            if ok:
                return True
            time.sleep(0.4)
        return False


    # ---------- 界面 ----------

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("PointLog 专注计时")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)                 # 无边框，更像悬浮窗
        self.root.configure(bg="#1f2430")
        self.root.geometry("+80+80")

        # 注意：StringVar/BooleanVar 必须先有 root（tkinter 需要默认根窗口），
        # 否则会抛 "Too early to create variable: no default root window"。
        self.status = tk.StringVar(value="就绪")
        self.time_var = tk.StringVar(value="00:00:00")
        self.label_var = tk.StringVar(value="未选标签")
        self.auto_upload = tk.BooleanVar(value=False)

        wrap = tk.Frame(self.root, bg="#1f2430", padx=12, pady=8)
        wrap.pack()

        bar = tk.Frame(wrap, bg="#1f2430")
        bar.pack(fill="x")
        tk.Label(bar, text="专注", fg="#8b93a7", bg="#1f2430",
                 font=("Segoe UI", 10)).pack(side="left")
        tk.Button(bar, text="✕", command=self.quit, bd=0, bg="#1f2430", fg="#8b93a7",
                  activebackground="#2b3242", activeforeground="#fff",
                  font=("Segoe UI", 10), cursor="hand2").pack(side="right")
        self.dot = tk.Label(bar, text="●", fg="#4b5563", bg="#1f2430", font=("Segoe UI", 10))
        self.dot.pack(side="right", padx=6)

        tk.Label(wrap, textvariable=self.time_var, fg="#e6e9f0", bg="#1f2430",
                 font=("Consolas", 30, "bold")).pack(pady=(2, 0))
        tk.Label(wrap, textvariable=self.label_var, fg="#6ee7b7", bg="#1f2430",
                 font=("Segoe UI", 11)).pack()

        self.row = tk.Frame(wrap, bg="#1f2430")
        self.row.pack(pady=8)
        self.btn_start = self._button(self.row, "开始", self.start, "#10b981")
        self.btn_pause = self._button(self.row, "暂停", self.pause, "#f59e0b")
        self.btn_resume = self._button(self.row, "继续", self.resume, "#3b82f6")
        self.btn_stop = self._button(self.row, "结束", self.stop, "#ef4444")

        tags = tk.Frame(wrap, bg="#1f2430")
        tags.pack(fill="x")
        for text in self.labels[:6]:
            chip = tk.Label(tags, text=text, fg="#c7d2fe", bg="#2b3242", padx=6, pady=2,
                            cursor="hand2", font=("Segoe UI", 9))
            chip.pack(side="left", padx=(0, 4), pady=2)
            chip.bind("<Button-1>", lambda _e, t=text: self.apply_label(t))

        entry_row = tk.Frame(wrap, bg="#1f2430")
        entry_row.pack(fill="x", pady=(4, 0))
        self.tag_entry = tk.Entry(entry_row, bg="#2b3242", fg="#e6e9f0", bd=0,
                                  insertbackground="#e6e9f0", font=("Segoe UI", 9))
        self.tag_entry.pack(side="left", fill="x", expand=True, ipady=3)
        self.tag_entry.bind("<Return>", lambda _e: self.apply_label())

        foot = tk.Frame(wrap, bg="#1f2430")
        foot.pack(fill="x", pady=(8, 0))
        tk.Checkbutton(foot, text="结束后自动上传", variable=self.auto_upload,
                       fg="#8b93a7", bg="#1f2430", selectcolor="#2b3242",
                       activebackground="#1f2430", activeforeground="#fff",
                       font=("Segoe UI", 9), bd=0).pack(side="left")
        self.btn_upload = self._button(foot, "上传", self.upload, "#6366f1", small=True)
        self.btn_upload.pack(side="right")

        tk.Label(wrap, textvariable=self.status, fg="#8b93a7", bg="#1f2430",
                 font=("Segoe UI", 8), anchor="w").pack(fill="x", pady=(6, 0))

        # 拖动（按住空白处）
        for widget in (self.root, wrap):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)
        self.root.bind("<Escape>", lambda _e: self.quit())
        self._refresh_buttons()
        self._tick()

    def _button(self, parent, text, command, color, small=False):
        return tk.Button(parent, text=text, command=command, bd=0, bg=color, fg="white",
                         activebackground=color, activeforeground="white", cursor="hand2",
                         font=("Segoe UI", 9 if small else 10, "bold"),
                         padx=8 if small else 12, pady=2 if small else 5)

    def _start_drag(self, event):
        self._drag = (event.x_root - self.root.winfo_x(),
                      event.y_root - self.root.winfo_y())

    def _on_drag(self, event):
        dx, dy = self._drag
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")


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
            self.upload()

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
        self.dot.configure(fg={"running": "#10b981", "paused": "#f59e0b"}.get(state, "#4b5563"))
        can_upload = state in ("paused", "stopped") and not (self.session or {}).get("entry_id")
        self.btn_upload.configure(state="normal" if can_upload else "disabled")

    def _tick(self):
        """本地每秒自增（不依赖网络）；与服务端对齐由各动作的返回完成。"""
        if (self.session or {}).get("state") == "running":
            self.elapsed += 1
        total = max(0, int(self.elapsed))
        self.time_var.set(f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}")
        self.root.after(POLL_MS, self._tick)

    def run(self):
        self.root.mainloop()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PointLog 专注计时器（桌面悬浮窗）")
    parser.add_argument("--base-url", default=DEFAULT_BASE, help="PointLog 服务地址")
    parser.add_argument("--points", type=float, default=1, help="上传时使用的点数（默认 1）")
    parser.add_argument("--list-labels", action="store_true", help="只打印当前档案的类别池")
    parser.add_argument("--wait", type=float, default=15.0,
                        help="启动时等待服务就绪的秒数（0＝不等待）")
    args = parser.parse_args(argv)

    labels = DEFAULT_LABELS
    ok, data = http_json(f"{args.base_url.rstrip('/')}/api/tags/diary")
    if ok and data.get("tags"):
        labels = data["tags"]

    if args.list_labels:
        print("\n".join(labels))
        return 0

    try:
        lock = acquire_instance_lock()
        if lock is None:                       # 已有悬浮窗在跑：静默退出，不叠窗口
            print("PointLog 专注计时器已在运行（如需重开，请先关掉旧窗口）。")
            return 0
        FocusTimer(args.base_url, args.points, labels, wait_sec=args.wait).run()
        lock.close()
    except tk.TclError as exc:                 # 无图形环境
        print(f"无法创建窗口（{exc}）。请在桌面环境运行，或用 --list-labels 查看标签。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
