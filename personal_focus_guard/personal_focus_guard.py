#!/usr/bin/env python3
"""个人专注控制器——直接读 Windows 前台窗口的自我管理工具。

这是你对自己电脑施加的自律工具，不是监控/管控他人的软件：
- 所有数据只留在本机（用 Windows API 直接读当前前台窗口，不依赖任何外部服务/第三方 App，
  不上报任何第三方）。
- "强制最小化窗口 + 反思弹窗" 只是行为提示，不对抗你本人：你随时可以在任务管理器里结束这个
  Python 进程，这是自我约束工具应有的边界，不是防护墙。

用法：
    python personal_focus_guard.py --config config.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Optional

try:
    from plyer import notification as plyer_notification
except ImportError:
    plyer_notification = None

IS_WINDOWS = sys.platform == "win32"

win32gui = win32con = win32process = psutil = None
if IS_WINDOWS:
    try:
        import win32con  # noqa: F811
        import win32gui  # noqa: F811
        import win32process  # noqa: F811
        import psutil  # noqa: F811
    except ImportError:
        pass  # 没装 pywin32/psutil 时，强制最小化功能会被跳过并打日志提醒

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
        logging.FileHandler(_LOG_DIR / "personal_focus_guard.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("personal_focus_guard")

REFLECTION_COOLDOWN_SECONDS = 60  # 同一时段内，反思弹窗最短间隔，避免配额用尽后每轮都弹


# --------------------------------------------------------------------------
# 配置模型
# --------------------------------------------------------------------------

@dataclass
class TimePeriod:
    name: str
    start: dt_time
    end: dt_time
    quota_minutes: int

    @classmethod
    def from_dict(cls, d: dict) -> "TimePeriod":
        return cls(
            name=d["name"],
            start=datetime.strptime(d["start"], "%H:%M").time(),
            end=datetime.strptime(d["end"], "%H:%M").time(),
            quota_minutes=int(d["quota_minutes"]),
        )

    def contains(self, now: dt_time) -> bool:
        return self.start <= now <= self.end


@dataclass
class RewardRule:
    focus_minutes_required: int = 45
    bonus_minutes: int = 5


@dataclass
class GuardConfig:
    poll_interval_seconds: int
    quota_periods: list[TimePeriod]
    blacklist_keywords: list[str]
    work_keywords: list[str]
    warning_threshold_seconds: int
    reward: RewardRule
    notification_app_name: str

    @classmethod
    def load(cls, path: Path) -> "GuardConfig":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            poll_interval_seconds=int(data.get("poll_interval_seconds", 5)),
            quota_periods=[TimePeriod.from_dict(p) for p in data["quota_periods"]],
            blacklist_keywords=[k.lower() for k in data.get("blacklist_keywords", [])],
            work_keywords=[k.lower() for k in data.get("work_keywords", [])],
            warning_threshold_seconds=int(data.get("warning_threshold_seconds", 180)),
            reward=RewardRule(**data.get("reward", {})),
            notification_app_name=data.get("notification_app_name", "专注守护"),
        )

    def period_at(self, now: dt_time) -> Optional[TimePeriod]:
        """返回当前时间所属的配额时段；午休/下班后等空隙返回 None（不扣配额不干预）。"""
        for period in self.quota_periods:
            if period.contains(now):
                return period
        return None

    def matches_blacklist(self, app: str, title: str) -> bool:
        haystack = f"{app} {title}".lower()
        return any(kw in haystack for kw in self.blacklist_keywords)

    def matches_work(self, app: str, title: str) -> bool:
        haystack = f"{app} {title}".lower()
        return any(kw in haystack for kw in self.work_keywords)


# --------------------------------------------------------------------------
# 前台窗口网关：直接用 Windows API 读当前窗口，不依赖任何外部服务/App
# --------------------------------------------------------------------------

@dataclass
class WindowSnapshot:
    app: str
    title: str


class ForegroundWindowGateway:
    """用 GetForegroundWindow 系列 Win32 API 读当前前台窗口，零外部依赖、零网络请求。
    只要打包出来的 exe 本身能跑（自带 pywin32/psutil），双击就能用，不需要用户另外装/开
    任何别的软件。"""

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
                pass  # 拿不到进程名（比如系统窗口/权限问题）时，仍然用标题继续判断
            return WindowSnapshot(app=app, title=title)
        except Exception:
            logger.exception("读取前台窗口失败")
            return None


# --------------------------------------------------------------------------
# 配额与奖励状态
# --------------------------------------------------------------------------

@dataclass
class PeriodState:
    date: str = ""
    used_seconds: float = 0.0
    bonus_seconds: float = 0.0
    warned: bool = False
    exhausted_notified: bool = False
    last_reflection_at: float = 0.0  # time.monotonic()

    def quota_seconds(self, base_minutes: int) -> float:
        return base_minutes * 60 + self.bonus_seconds

    def remaining_seconds(self, base_minutes: int) -> float:
        return max(0.0, self.quota_seconds(base_minutes) - self.used_seconds)


class FocusRewardTracker:
    """跟踪"连续专注工作软件"的时长，达到门槛时发出一次奖励信号。"""

    def __init__(self, reward: RewardRule):
        self.reward = reward
        self._consecutive_seconds = 0.0

    def observe(self, is_work: bool, elapsed_seconds: float) -> bool:
        """喂入这一轮 tick 的"是否在工作软件"和经过的秒数。
        恰好跨过门槛的那一刻返回 True（代表应发放一次奖励），随后重新计数，
        允许同一时段内再专注一轮获得下一次奖励。"""
        if not is_work:
            self._consecutive_seconds = 0.0
            return False
        self._consecutive_seconds += elapsed_seconds
        required = self.reward.focus_minutes_required * 60
        if self._consecutive_seconds >= required:
            self._consecutive_seconds = 0.0
            return True
        return False


# --------------------------------------------------------------------------
# 干预动作：通知 / 最小化 / 反思弹窗
# --------------------------------------------------------------------------

class InterventionController:
    def __init__(self, app_name: str):
        self.app_name = app_name

    def notify(self, title: str, message: str) -> None:
        if plyer_notification is None:
            logger.info("[系统通知-降级为终端] %s: %s", title, message)
            return
        try:
            plyer_notification.notify(title=title, message=message, app_name=self.app_name, timeout=8)
        except Exception:
            logger.exception("发送系统通知失败，降级为终端打印")
            logger.info("[系统通知-降级为终端] %s: %s", title, message)

    def minimize_blacklisted_windows(self, keywords: list[str]) -> int:
        """最小化所有标题/进程名命中黑名单关键词的可见顶层窗口。仅 Windows 实现，其他平台跳过。"""
        if not IS_WINDOWS or win32gui is None:
            logger.warning("当前环境不支持强制最小化窗口（需要 Windows + pywin32），已跳过。")
            return 0

        minimized = 0

        def _enum_handler(hwnd, _extra) -> None:
            nonlocal minimized
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return
            process_name = ""
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if psutil is not None:
                    process_name = psutil.Process(pid).name()
            except Exception:
                pass
            haystack = f"{process_name} {title}".lower()
            if any(kw in haystack for kw in keywords):
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                minimized += 1

        win32gui.EnumWindows(_enum_handler, None)
        return minimized

    def show_reflection_dialog(self, breathing_seconds: int = 10) -> None:
        """居中弹窗：倒计时结束前关闭按钮保持禁用。这是行为提示，不是安全边界——
        用户本人随时可以从任务管理器结束整个进程，脚本不会、也不应该阻止这一点。"""
        import tkinter as tk  # 延迟导入：没有图形环境时也能跑配额逻辑的单测

        root = tk.Tk()
        root.title("专注提醒")
        root.resizable(False, False)
        root.attributes("-topmost", True)

        width, height = 380, 220
        x = (root.winfo_screenwidth() - width) // 2
        y = (root.winfo_screenheight() - height) // 2
        root.geometry(f"{width}x{height}+{x}+{y}")

        tk.Label(
            root,
            text="本时段摸鱼配额已用尽。\n\n深呼吸 10 秒，想想手头真正要做的事，\n然后回到主任务。",
            wraplength=320,
            justify="center",
            pady=20,
        ).pack()

        countdown_var = tk.StringVar(value=str(breathing_seconds))
        tk.Label(root, textvariable=countdown_var, font=("Arial", 16, "bold")).pack()

        close_button = tk.Button(root, text="我已深呼吸，关闭", state=tk.DISABLED, command=root.destroy)
        close_button.pack(pady=10)
        root.protocol("WM_DELETE_WINDOW", lambda: None)  # 倒计时内先忽略右上角关闭

        def tick(remaining: int) -> None:
            if remaining <= 0:
                countdown_var.set("可以关闭了")
                close_button.config(state=tk.NORMAL)
                root.protocol("WM_DELETE_WINDOW", root.destroy)
                return
            countdown_var.set(str(remaining))
            root.after(1000, tick, remaining - 1)

        tick(breathing_seconds)
        root.mainloop()


# --------------------------------------------------------------------------
# 主循环
# --------------------------------------------------------------------------

class PersonalFocusGuard:
    def __init__(self, config_path: Path, gateway: Optional[ForegroundWindowGateway] = None):
        self.config_path = config_path
        self.config = GuardConfig.load(config_path)
        self.gateway = gateway or ForegroundWindowGateway()
        self.intervention = InterventionController(self.config.notification_app_name)
        self.period_states: dict[str, PeriodState] = {}
        self.focus_tracker = FocusRewardTracker(self.config.reward)
        self._last_tick = time.monotonic()

    def _reload_config(self) -> None:
        try:
            self.config = GuardConfig.load(self.config_path)
        except Exception:
            logger.exception("重新加载配置文件失败，继续使用上一份有效配置")

    def _state_for(self, period: TimePeriod) -> PeriodState:
        today = datetime.now().strftime("%Y-%m-%d")
        state = self.period_states.get(period.name)
        if state is None or state.date != today:
            state = PeriodState(date=today)
            self.period_states[period.name] = state
        return state

    def run_forever(self) -> None:
        logger.info("个人专注控制器已启动，Ctrl+C 退出。")
        while True:
            self._tick()
            time.sleep(self.config.poll_interval_seconds)

    def _tick(self) -> None:
        self._reload_config()
        now_monotonic = time.monotonic()
        elapsed = now_monotonic - self._last_tick
        self._last_tick = now_monotonic

        window = self.gateway.current_window()
        if window is None:
            return

        period = self.config.period_at(datetime.now().time())

        self._handle_focus_reward(window, period, elapsed)

        if period is None:
            return  # 午休/下班后：不扣配额、不触发任何干预

        if not self.config.matches_blacklist(window.app, window.title):
            return

        state = self._state_for(period)
        state.used_seconds += elapsed
        remaining = state.remaining_seconds(period.quota_minutes)

        logger.info(
            "[%s] 命中黑名单 app=%r title=%r 已用=%.0fs 剩余=%.0fs",
            period.name, window.app, window.title, state.used_seconds, remaining,
        )

        if remaining <= 0:
            self._exhaust_intervention(period, state)
        elif remaining <= self.config.warning_threshold_seconds and not state.warned:
            state.warned = True
            self.intervention.notify(
                "摸鱼配额预警",
                f"本时段摸鱼额度仅剩 {max(1, int(remaining // 60))} 分钟，建议喝口水回到主任务。",
            )

    def _handle_focus_reward(
        self, window: WindowSnapshot, period: Optional[TimePeriod], elapsed: float
    ) -> None:
        is_work = self.config.matches_work(window.app, window.title)
        if not self.focus_tracker.observe(is_work, elapsed):
            return
        if period is None:
            return  # 专注发生在时段外（比如加班），没有对应的娱乐池可以奖励
        state = self._state_for(period)
        state.bonus_seconds += self.config.reward.bonus_minutes * 60
        logger.info(
            "连续专注满 %d 分钟，奖励 [%s] 时段 %d 分钟配额",
            self.config.reward.focus_minutes_required, period.name, self.config.reward.bonus_minutes,
        )
        self.intervention.notify(
            "专注奖励",
            f"连续专注 {self.config.reward.focus_minutes_required} 分钟！"
            f"奖励 {self.config.reward.bonus_minutes} 分钟摸鱼额度。",
        )

    def _exhaust_intervention(self, period: TimePeriod, state: PeriodState) -> None:
        if not state.exhausted_notified:
            state.exhausted_notified = True
            self.intervention.notify(
                "摸鱼配额已用尽", f"[{period.name}] 时段配额已用完，即将收起当前窗口。"
            )

        minimized = self.intervention.minimize_blacklisted_windows(self.config.blacklist_keywords)

        now = time.monotonic()
        if minimized > 0 and now - state.last_reflection_at >= REFLECTION_COOLDOWN_SECONDS:
            state.last_reflection_at = now
            self.intervention.show_reflection_dialog(breathing_seconds=10)


def main() -> None:
    parser = argparse.ArgumentParser(description="个人专注控制器（基于 Windows 前台窗口 API）")
    parser.add_argument(
        "--config", type=Path, default=_app_dir() / "config.json",
        help="配置文件路径，默认同目录下的 config.json",
    )
    args = parser.parse_args()

    if not args.config.exists():
        logger.error(
            "配置文件不存在: %s\n请先执行: cp config.example.json config.json 并按需修改。",
            args.config,
        )
        sys.exit(1)

    guard = PersonalFocusGuard(args.config)
    try:
        guard.run_forever()
    except KeyboardInterrupt:
        logger.info("已退出。")


if __name__ == "__main__":
    main()
