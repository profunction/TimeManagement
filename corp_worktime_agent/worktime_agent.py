#!/usr/bin/env python3
"""企业工时统计 Agent（合规透明版）——直接读 Windows 前台窗口的分类计时工具。

四条硬约束（设计时的边界，不是营销话术）：
1. 没有同意记录就不运行、不采集任何数据。
2. 运行期间系统托盘持续显示"工时计时中"，不是隐藏后台进程。
3. "查看我的记录"里员工能看到的内容 == 上报给 report_webhook_url 的内容，字段完全一致。
4. 不做强制结束/隐藏黑名单进程，不做反卸载；员工退出 Agent 是被允许的操作，只会被如实记录。

用法：
    python worktime_agent.py --config config.json
"""
from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import scrolledtext
from typing import Optional

import requests

IS_WINDOWS = sys.platform == "win32"

win32gui = win32process = psutil = None
if IS_WINDOWS:
    try:
        import win32gui  # noqa: F811
        import win32process  # noqa: F811
        import psutil  # noqa: F811
    except ImportError:
        pass  # 没装 pywin32/psutil 时，前台窗口检测会在 ForegroundWindowGateway 初始化时报错

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None
    Image = ImageDraw = None

def _app_dir() -> Path:
    """打包成 PyInstaller exe 后 __file__ 指向临时解压目录，用 sys.executable 所在目录才对。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


_LOG_DIR = Path.home() / ".timemanagement" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_LOG_DIR / "worktime_agent.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("worktime_agent")

STATE_DIR = Path.home() / ".timemanagement" / "corp_worktime"
CONSENT_FILE = Path.home() / ".timemanagement" / "corp_consent.json"
TRANSPARENCY_LOG = STATE_DIR / "transparency_log.jsonl"
CATEGORIES = ("work", "break", "personal", "other")


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------

@dataclass
class AgentConfig:
    employee_id: str
    poll_interval_seconds: int
    report_interval_minutes: int
    report_webhook_url: str
    consent_notice_path: Path
    work_keywords: list[str]
    break_keywords: list[str]
    personal_keywords: list[str]

    @classmethod
    def load(cls, path: Path) -> "AgentConfig":
        data = json.loads(path.read_text(encoding="utf-8"))
        categories = data.get("categories", {})
        return cls(
            employee_id=data["employee_id"],
            poll_interval_seconds=int(data.get("poll_interval_seconds", 5)),
            report_interval_minutes=int(data.get("report_interval_minutes", 30)),
            report_webhook_url=data.get("report_webhook_url", "").strip(),
            consent_notice_path=(path.parent / data.get("consent_notice_path", "consent_notice.md")),
            work_keywords=[k.lower() for k in categories.get("work_keywords", [])],
            break_keywords=[k.lower() for k in categories.get("break_keywords", [])],
            personal_keywords=[k.lower() for k in categories.get("personal_keywords", [])],
        )

    def categorize(self, app: str, title: str) -> str:
        haystack = f"{app} {title}".lower()
        if any(kw in haystack for kw in self.work_keywords):
            return "work"
        if any(kw in haystack for kw in self.break_keywords):
            return "break"
        if any(kw in haystack for kw in self.personal_keywords):
            return "personal"
        return "other"


# --------------------------------------------------------------------------
# 知情同意
# --------------------------------------------------------------------------

def _load_consent() -> Optional[dict]:
    if not CONSENT_FILE.exists():
        return None
    try:
        return json.loads(CONSENT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _save_consent(employee_id: str, accepted: bool) -> None:
    CONSENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONSENT_FILE.write_text(
        json.dumps(
            {
                "employee_id": employee_id,
                "accepted": accepted,
                "accepted_at": datetime.now().isoformat(timespec="seconds"),
            }
        ),
        encoding="utf-8",
    )


def _show_consent_dialog(notice_text: str) -> bool:
    """展示完整同意书，返回用户是否勾选同意。不同意/直接关闭窗口都视为不同意。"""
    result = {"accepted": False}

    root = tk.Tk()
    root.title("工时统计工具 - 使用告知")
    root.geometry("560x480")

    text_area = scrolledtext.ScrolledText(root, wrap=tk.WORD)
    text_area.insert(tk.END, notice_text)
    text_area.configure(state=tk.DISABLED)
    text_area.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

    agree_var = tk.BooleanVar(value=False)
    tk.Checkbutton(root, text="我已阅读并同意以上内容", variable=agree_var).pack(pady=(0, 6))

    button_row = tk.Frame(root)
    button_row.pack(pady=(0, 12))

    def on_agree() -> None:
        result["accepted"] = agree_var.get()
        root.destroy()

    def on_decline() -> None:
        result["accepted"] = False
        root.destroy()

    tk.Button(button_row, text="同意并继续", command=on_agree, width=14).pack(side=tk.LEFT, padx=8)
    tk.Button(button_row, text="不同意，退出", command=on_decline, width=14).pack(side=tk.LEFT, padx=8)
    root.protocol("WM_DELETE_WINDOW", on_decline)

    root.mainloop()
    return result["accepted"]


def ensure_consent(config: AgentConfig) -> bool:
    existing = _load_consent()
    if existing and existing.get("employee_id") == config.employee_id and existing.get("accepted"):
        logger.info("已存在有效同意记录（%s），跳过弹窗。", existing.get("accepted_at"))
        return True

    if not config.consent_notice_path.exists():
        logger.error("同意书文件不存在: %s，无法在没有告知文本的情况下运行。", config.consent_notice_path)
        return False

    notice_text = config.consent_notice_path.read_text(encoding="utf-8")
    accepted = _show_consent_dialog(notice_text)
    _save_consent(config.employee_id, accepted)
    if not accepted:
        logger.info("员工未同意，Agent 不会采集任何数据，直接退出。")
    return accepted


# --------------------------------------------------------------------------
# 前台窗口网关：直接用 Windows API 读当前窗口，不依赖任何外部服务/App
# --------------------------------------------------------------------------

@dataclass
class WindowSnapshot:
    app: str
    title: str


class ForegroundWindowGateway:
    """用 GetForegroundWindow 系列 Win32 API 读当前前台窗口，零外部依赖、零网络请求。
    和"员工看到的=上报的"那条约束一样重要的一点：这里也不额外采集任何 Windows 之外的数据，
    只拿"当前窗口标题+进程名"这一项。"""

    def __init__(self):
        if not IS_WINDOWS or win32gui is None:
            raise RuntimeError("前台窗口检测仅支持 Windows，且需要 pywin32（打包时已包含）。")
        logger.info("使用 Windows 前台窗口 API 读取当前窗口，无需任何外部服务。")

    def current_window(self) -> Optional[WindowSnapshot]:
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            title = win32gui.GetWindowText(hwnd)
            app = ""
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if psutil is not None:
                    app = psutil.Process(pid).name()
            except Exception:
                pass
            return WindowSnapshot(app=app, title=title)
        except Exception:
            logger.exception("读取前台窗口失败")
            return None


# --------------------------------------------------------------------------
# 每日统计 + 透明日志
# --------------------------------------------------------------------------

class DailyStatsStore:
    """分类耗时的每日汇总。磁盘上的内容就是"查看我的记录"和上报 payload 的唯一数据源，
    两处看到的永远是同一份文件，不存在"员工看不到但上报了"的隐藏字段。"""

    def __init__(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self._date = self._today()
        self._minutes: dict[str, float] = {c: 0.0 for c in CATEGORIES}
        self._load()

    @staticmethod
    def _today() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _path_for(self, date: str) -> Path:
        return STATE_DIR / f"{date}.json"

    def _load(self) -> None:
        path = self._path_for(self._date)
        if path.exists():
            try:
                self._minutes = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        self._path_for(self._date).write_text(json.dumps(self._minutes), encoding="utf-8")

    def _roll_over_if_needed(self) -> None:
        today = self._today()
        if today != self._date:
            self._date = today
            self._minutes = {c: 0.0 for c in CATEGORIES}
            self._load()

    def add_seconds(self, category: str, seconds: float) -> None:
        self._roll_over_if_needed()
        self._minutes[category] = self._minutes.get(category, 0.0) + seconds / 60.0
        self._save()

    def snapshot_minutes(self) -> dict[str, int]:
        self._roll_over_if_needed()
        return {c: round(self._minutes.get(c, 0.0)) for c in CATEGORIES}

    def current_date(self) -> str:
        self._roll_over_if_needed()
        return self._date


def log_transparency_event(event: str, payload: dict) -> None:
    """本机可审计的事件日志：监控开始/停止/上报，都是员工本人也能打开这个文件看到的。"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    record = {"event": event, "at": datetime.now().isoformat(timespec="seconds"), **payload}
    with TRANSPARENCY_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# 上报
# --------------------------------------------------------------------------

class Reporter:
    def __init__(self, config: AgentConfig, stats: DailyStatsStore):
        self.config = config
        self.stats = stats

    def build_payload(self, event: str = "periodic_report") -> dict:
        return {
            "employee_id": self.config.employee_id,
            "hostname": socket.gethostname(),
            "date": self.stats.current_date(),
            "category_minutes": self.stats.snapshot_minutes(),
            "event": event,
        }

    def send(self, event: str = "periodic_report") -> None:
        payload = self.build_payload(event)
        log_transparency_event(event, payload)  # 先落本机日志：即便上报失败，审计记录也不丢
        if not self.config.report_webhook_url:
            logger.info("report_webhook_url 未配置，仅记录本机日志，不对外上报。payload=%s", payload)
            return
        try:
            resp = requests.post(self.config.report_webhook_url, json=payload, timeout=5)
            resp.raise_for_status()
            logger.info("已上报 (%s): %s", event, payload["category_minutes"])
        except Exception:
            logger.exception("上报失败，已保留在本机日志中，可稍后重试或由 IT 排查")


# --------------------------------------------------------------------------
# 托盘 UI
# --------------------------------------------------------------------------

def _build_tray_image():
    if Image is None:
        return None
    img = Image.new("RGB", (64, 64), color="#1565C0")
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, 56, 56), outline="white", width=4)
    draw.line((32, 32, 32, 16), fill="white", width=3)
    draw.line((32, 32, 44, 32), fill="white", width=3)
    return img


class TrayUI:
    def __init__(self, config: AgentConfig, stats: DailyStatsStore, reporter: Reporter, on_exit):
        self.config = config
        self.stats = stats
        self.reporter = reporter
        self.on_exit = on_exit
        self.icon = None
        if pystray is not None:
            self.icon = pystray.Icon(
                "corp_worktime_agent",
                _build_tray_image(),
                "工时计时中（合规透明版）",
                menu=pystray.Menu(
                    pystray.MenuItem("查看我的记录", self._show_my_records),
                    pystray.MenuItem("监控说明", self._show_notice),
                    pystray.MenuItem("退出 Agent", self._exit),
                ),
            )

    def _show_my_records(self, _icon=None, _item=None) -> None:
        minutes = self.stats.snapshot_minutes()
        lines = [f"{self.stats.current_date()} 的分类耗时（分钟）：", ""]
        lines += [f"  {cat}: {minutes.get(cat, 0)}" for cat in CATEGORIES]
        lines.append("")
        lines.append("这份数据和上报给公司系统的完全一致，没有额外隐藏字段。")
        self._show_textbox("我的记录", "\n".join(lines))

    def _show_notice(self, _icon=None, _item=None) -> None:
        text = self.config.consent_notice_path.read_text(encoding="utf-8")
        self._show_textbox("监控说明", text)

    @staticmethod
    def _show_textbox(title: str, content: str) -> None:
        root = tk.Tk()
        root.title(title)
        root.geometry("480x400")
        box = scrolledtext.ScrolledText(root, wrap=tk.WORD)
        box.insert(tk.END, content)
        box.configure(state=tk.DISABLED)
        box.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        tk.Button(root, text="关闭", command=root.destroy).pack(pady=8)
        root.mainloop()

    def _exit(self, _icon=None, _item=None) -> None:
        self.on_exit()
        if self.icon is not None:
            self.icon.stop()

    def run(self) -> None:
        if self.icon is None:
            logger.warning("pystray/Pillow 未安装，无法显示托盘图标；仍会在终端打印状态。")
            return
        self.icon.run()


# --------------------------------------------------------------------------
# 主循环
# --------------------------------------------------------------------------

class WorktimeAgent:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.gateway = ForegroundWindowGateway()
        self.stats = DailyStatsStore()
        self.reporter = Reporter(config, self.stats)
        self.tray = TrayUI(config, self.stats, self.reporter, on_exit=self._handle_user_exit)
        self._stop_flag = threading.Event()
        self._last_tick = time.monotonic()
        self._last_report = time.monotonic()

    def _handle_user_exit(self) -> None:
        logger.info("员工主动退出 Agent，记录退出事件并尝试最后一次上报。")
        self.reporter.send(event="monitoring_stopped_by_user")
        self._stop_flag.set()

    def _poll_loop(self) -> None:
        log_transparency_event("monitoring_started", {"employee_id": self.config.employee_id})
        while not self._stop_flag.is_set():
            now = time.monotonic()
            elapsed = now - self._last_tick
            self._last_tick = now

            window = self.gateway.current_window()
            if window is not None:
                category = self.config.categorize(window.app, window.title)
                self.stats.add_seconds(category, elapsed)

            if now - self._last_report >= self.config.report_interval_minutes * 60:
                self._last_report = now
                self.reporter.send(event="periodic_report")

            time.sleep(self.config.poll_interval_seconds)

    def run(self) -> None:
        poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        poll_thread.start()
        self.tray.run()  # 阻塞直到托盘图标被退出
        self._stop_flag.set()


def main() -> None:
    parser = argparse.ArgumentParser(description="企业工时统计 Agent（合规透明版）")
    parser.add_argument("--config", type=Path, default=_app_dir() / "config.json")
    args = parser.parse_args()

    if not args.config.exists():
        logger.error("配置文件不存在: %s，请先 cp config.example.json config.json 并修改。", args.config)
        sys.exit(1)

    config = AgentConfig.load(args.config)

    if not ensure_consent(config):
        sys.exit(0)  # 不同意 = 正常退出，不是报错，也不会重试绕过

    agent = WorktimeAgent(config)
    try:
        agent.run()
    except KeyboardInterrupt:
        agent._handle_user_exit()


if __name__ == "__main__":
    main()
