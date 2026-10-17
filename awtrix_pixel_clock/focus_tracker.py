#!/usr/bin/env python3
"""CLI + background daemon that renders focus/slacking state onto an AWTRIX pixel matrix.

Usage:
    python focus_tracker.py focus     # enter focus mode (flow timer, counts up, green)
    python focus_tracker.py slack     # enter slacking mode (15 min cap, countdown bar)
    python focus_tracker.py stop      # back to idle, clears the screen
    python focus_tracker.py status    # print current state
    python focus_tracker.py run       # long-running loop: keeps pushing frames to the matrix

`focus` / `slack` / `stop` just write a small state file and exit immediately — bind them to
a hotkey, launcher script, or a hook in your own time-tracking app. `run` is the process that
actually talks to the AWTRIX device; keep exactly one instance of it running in the background
(e.g. via a terminal, tmux, systemd/launchd, or Task Scheduler).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from awtrix_client import AwtrixClient, AwtrixConfig

STATE_DIR = Path(os.environ.get("TIMEMANAGEMENT_HOME", Path.home() / ".timemanagement"))
STATE_FILE = STATE_DIR / "awtrix_state.json"

APP_NAME = "focus_status"
SLACK_LIMIT_SECONDS = 15 * 60
RED_ALERT_SECONDS = 3 * 60

FOCUS_COLOR = "#00FF55"
SLACK_COLOR = "#FFA000"
SLACK_PROGRESS_COLOR = "#FFA000"
ALERT_COLOR = "#FF0000"

# AWTRIX accepts either a built-in LaMetric icon id (numeric string) or the name of an icon
# you uploaded yourself in the AWTRIX web UI (Icons -> Upload, 8x8 PNG/GIF). Set your own here;
# leave as None to render text-only, which always works with zero extra setup.
FOCUS_ICON: str | None = os.environ.get("AWTRIX_ICON_CAT")  # e.g. "cat" if you uploaded one


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {"mode": "idle", "started_at": None}
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"mode": "idle", "started_at": None}


def _save_state(mode: str, started_at: float | None) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"mode": mode, "started_at": started_at}))


def cmd_focus(_args: argparse.Namespace) -> None:
    _save_state("focus", time.time())
    print("切换到专注模式")


def cmd_slack(_args: argparse.Namespace) -> None:
    _save_state("slack", time.time())
    print(f"切换到摸鱼模式，上限 {SLACK_LIMIT_SECONDS // 60} 分钟")


def cmd_stop(_args: argparse.Namespace) -> None:
    _save_state("idle", None)
    print("回到空闲状态")


def cmd_status(_args: argparse.Namespace) -> None:
    state = _load_state()
    mode = state["mode"]
    started_at = state["started_at"]
    if started_at is None:
        print(f"mode={mode}")
        return
    elapsed = int(time.time() - started_at)
    if mode == "slack":
        remaining = max(0, SLACK_LIMIT_SECONDS - elapsed)
        print(f"mode={mode} elapsed={elapsed}s remaining={remaining}s")
    else:
        print(f"mode={mode} elapsed={elapsed}s")


def _fmt_mmss(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _render_focus(client: AwtrixClient, elapsed: int) -> None:
    payload = {
        "text": f"{_fmt_mmss(elapsed)}",
        "color": FOCUS_COLOR,
    }
    if FOCUS_ICON:
        payload["icon"] = FOCUS_ICON
    client.push_custom_app(APP_NAME, payload)


def _render_slack(client: AwtrixClient, elapsed: int) -> str:
    """Returns the recommended sleep interval for the next tick (tighter near the deadline)."""
    remaining = SLACK_LIMIT_SECONDS - elapsed

    if remaining <= 0:
        client.push_notify({"text": "摸鱼超时，回去干活！", "color": ALERT_COLOR, "hold": True})
        client.clear_app(APP_NAME)
        _save_state("idle", None)
        return "5"

    if remaining <= RED_ALERT_SECONDS:
        # Hand-rolled blink: alternate a red full-text frame with a blank frame every ~1s,
        # instead of relying on a firmware "blink" effect that may differ between versions.
        if int(time.time()) % 2 == 0:
            client.push_custom_app(
                APP_NAME,
                {
                    "text": _fmt_mmss(remaining),
                    "color": ALERT_COLOR,
                    "background": "#330000",
                    "progress": int(100 * remaining / SLACK_LIMIT_SECONDS),
                    "progressC": ALERT_COLOR,
                },
            )
        else:
            client.push_custom_app(APP_NAME, {"text": " ", "color": "#000000"})
        return "1"

    client.push_custom_app(
        APP_NAME,
        {
            "text": _fmt_mmss(remaining),
            "color": SLACK_COLOR,
            "progress": int(100 * remaining / SLACK_LIMIT_SECONDS),
            "progressC": SLACK_PROGRESS_COLOR,
        },
    )
    return "5"


def cmd_run(_args: argparse.Namespace) -> None:
    client = AwtrixClient(AwtrixConfig.from_env())
    last_mode = None
    try:
        while True:
            state = _load_state()
            mode = state["mode"]
            started_at = state["started_at"]
            elapsed = int(time.time() - started_at) if started_at else 0

            if mode != last_mode and mode == "idle":
                client.clear_app(APP_NAME)

            sleep_for = 5.0
            if mode == "focus":
                _render_focus(client, elapsed)
            elif mode == "slack":
                sleep_for = float(_render_slack(client, elapsed))
            # mode == "idle": nothing to push, just idle-poll for a state change

            last_mode = mode
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        pass
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("focus", help="进入专注模式").set_defaults(func=cmd_focus)
    sub.add_parser("slack", help="进入摸鱼模式（15分钟上限）").set_defaults(func=cmd_slack)
    sub.add_parser("stop", help="回到空闲，清屏").set_defaults(func=cmd_stop)
    sub.add_parser("status", help="查看当前状态").set_defaults(func=cmd_status)
    sub.add_parser("run", help="后台常驻：持续把状态推送到像素屏").set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
