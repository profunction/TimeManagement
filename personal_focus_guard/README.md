# 个人专注控制器（基于 ActivityWatch）

自我施加的"摸鱼配额"工具：用 [ActivityWatch](https://activitywatch.net/) 的本地窗口监控数据
驱动一个分时段配额引擎，剩余 3 分钟原生通知提醒，配额用尽时温和干预（最小化黑名单窗口 +
居中反思弹窗），连续专注工作软件 45 分钟奖励 5 分钟配额。这是**你对自己电脑的自我管理工具**，
不涉及第三方上报，不对抗你本人终止进程的能力（你永远可以在任务管理器里关掉它——这是自律工具，
不是监控工具）。

---

## 1. 环境准备

### 1.1 关于 `aw-client-python` 仓库

```bash
git clone https://github.com/ActivityWatch/aw-client-python.git
```

**说明**：`aw-client-python` 本身是一个**库**（PyPI 包 `aw-client`），不是应用脚手架，
所以正确做法不是把我们的脚本塞进这个库仓库里改，而是：

- 如果你只是要用这个库 → 直接 `pip install aw-client`，不需要克隆源码。
- 如果你想改库本身的行为（比如自定义查询逻辑）→ 克隆下来后用可编辑模式安装：
  ```bash
  pip install -e ./aw-client-python
  ```

本目录（`personal_focus_guard/`）是独立的应用项目，`aw-client` 只是它的一个 pip 依赖。

### 1.2 虚拟环境 + 依赖安装

**venv 方式：**

```bash
cd personal_focus_guard
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**poetry 方式：**

```bash
cd personal_focus_guard
poetry init --name personal-focus-guard --python "^3.10" -n
poetry add aw-client plyer psutil
poetry add pywin32 --platform win32   # 仅 Windows 需要，强制最小化窗口要用到
poetry install
```

`requirements.txt` 内容见本目录，已按平台标注哪些依赖是 Windows 专属的。

### 1.3 确认 ActivityWatch 服务端已在跑，且能通信

1. 先正常安装并启动 **ActivityWatch 桌面端**（这是独立的程序，不是 pip 包），它会在本机
   `http://localhost:5600` 起一个 REST API 服务，并自带 `aw-watcher-window` /
   `aw-watcher-afk` 这两个后台监听器，持续记录当前前台窗口。
2. 验证服务是否在跑：
   ```bash
   curl http://localhost:5600/api/0/info
   ```
   能返回版本号 JSON 就说明服务正常。
3. 用 `aw-client` 做同样的事确认库能连上：
   ```python
   from aw_client import ActivityWatchClient
   client = ActivityWatchClient("focus-guard-smoketest")
   print(client.get_info())
   print(client.get_buckets().keys())   # 应该能看到类似 aw-watcher-window_<hostname> 的桶
   ```

`personal_focus_guard.py` 启动时会自动做这个检查，如果 AW 服务没起会直接报错退出并告诉你怎么修。

---

## 2. 运行

```bash
cp config.example.json config.json   # 按需改黑名单关键词 / 时间段 / 配额
python personal_focus_guard.py --config config.json
```

- 配置文件**热加载**：脚本每轮轮询都会重新读一次 `config.json`，改完保存立刻生效，不用重启。
- 日志同时打印在终端 + 写入 `~/.timemanagement/logs/personal_focus_guard.log`，方便复盘当天状态。

---

## 3. 打包成 Windows .exe（免装 Python）

```
build_windows_exe.bat
```

双击或在 Windows 的 cmd/PowerShell 里运行这个脚本，会自动建虚拟环境、装依赖、调用
PyInstaller 打包，产出 `dist\PersonalFocusGuard\PersonalFocusGuard.exe`。

**注意事项**：
- **必须在 Windows 上跑这个脚本**——PyInstaller 不支持跨平台编译，不能在 Linux/Mac 上生成
  Windows exe，所以这个 `.bat` 没法在开发这份代码的云端环境里验证，请在你自己的 Windows 机器
  上跑一遍。
- Python 需要是从 [python.org](https://www.python.org/downloads/) 装的完整版，自带 tkinter；
  Microsoft Store 版 Python 有时会缺 tkinter，打包/运行反思弹窗那部分会报错。
- 首次运行打包出的 exe，如果 Windows SmartScreen / 杀毒软件弹"未知发布者"警告，这是
  PyInstaller 打包的程序没有代码签名导致的常见提示，不是脚本本身有问题；点"仍要运行"即可，
  如果需要消除这个提示，需要自行购买代码签名证书对 exe 签名。
- 打包出来是整个 `dist\PersonalFocusGuard\` 文件夹（里面还有依赖的 dll），**不要只拷贝
  exe 单个文件**，把整个文件夹一起复制/分发。

---

## 3. 配置文件字段说明（`config.example.json`）

| 字段 | 说明 |
|---|---|
| `poll_interval_seconds` | 轮询间隔（秒），默认 5 |
| `quota_periods` | 时段数组，每项含 `name`、`start`(HH:MM)、`end`(HH:MM)、`quota_minutes` |
| `blacklist_keywords` | 娱乐类关键词（匹配窗口标题 + 进程名，大小写不敏感） |
| `work_keywords` | 工作类关键词，用于判定"专注工作"从而触发奖励 |
| `warning_threshold_seconds` | 剩余多少秒时触发"还剩3分钟"通知，默认 180 |
| `reward.focus_minutes_required` | 连续专注多少分钟触发奖励，默认 45 |
| `reward.bonus_minutes` | 每次奖励多少分钟配额，默认 5 |

时段之外（午休、下班后）不扣配额、不触发任何通知或干预。
