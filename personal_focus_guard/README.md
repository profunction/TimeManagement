# 个人专注控制器

自我施加的"摸鱼配额"工具：直接用 Windows 自带的 API 读当前前台窗口，驱动一个分时段配额引擎，
剩余 3 分钟原生通知提醒，配额用尽时温和干预（最小化黑名单窗口 + 居中反思弹窗），连续专注工作
软件 45 分钟奖励 5 分钟配额。这是**你对自己电脑的自我管理工具**，不涉及第三方上报，不对抗你
本人终止进程的能力（你永远可以在任务管理器里关掉它——这是自律工具，不是监控工具）。

**不依赖任何外部服务**：不需要装 ActivityWatch 或任何其他后台程序，打包出来的 exe 双击就能用。

---

## 1. 环境准备

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
poetry add plyer psutil
poetry add pywin32 --platform win32   # Windows 专属，读前台窗口/强制最小化要用到
poetry install
```

`requirements.txt` 内容见本目录，已按平台标注哪些依赖是 Windows 专属的。

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
PyInstaller 打包，产出 `dist\PersonalFocusGuard\PersonalFocusGuard.exe`。打包后的 exe
**自带所有依赖，不需要用户再装任何别的软件**，双击就能用。

**注意事项**：
- **必须在 Windows 上跑这个脚本**——PyInstaller 不支持跨平台编译，不能在 Linux/Mac 上生成
  Windows exe，所以这个 `.bat` 没法在开发这份代码的云端环境里验证，请在你自己的 Windows 机器
  上跑一遍。
- Python 需要是从 [python.org](https://www.python.org/downloads/) 装的完整版，自带 tkinter；
  Microsoft Store 版 Python 有时会缺 tkinter，打包/运行反思弹窗那部分会报错；另外
  Microsoft Store 版的 `python` 命令有时只是个提示去商店安装的桩程序，`build_windows_exe.bat`
  会自动检测这种情况并给出修复提示。
- 首次运行打包出的 exe，如果 Windows SmartScreen / 杀毒软件弹"未知发布者"警告，这是
  PyInstaller 打包的程序没有代码签名导致的常见提示，不是脚本本身有问题；点"仍要运行"即可，
  如果需要消除这个提示，需要自行购买代码签名证书对 exe 签名。
- 打包出来是整个 `dist\PersonalFocusGuard\` 文件夹（里面还有依赖的 dll），**不要只拷贝
  exe 单个文件**，把整个文件夹一起复制/分发。

---

## 4. 打包成一键安装程序（可选，更像"正式 app"）

上一步产出的是"一个文件夹，解压/拷贝后双击里面的 exe"，能用但不太像正式软件。这一步用
[Inno Setup](https://jrsoftware.org/isdl.php)（免费）把它做成**单文件安装包**：双击安装、
自动建开始菜单项、可选桌面图标、在"添加或删除程序"里能正常卸载。

> 说明：严格意义上的 `.msi` 要用微软的 WiX Toolset（纯 XML 写安装脚本，上手成本高很多）。
> Inno Setup 产出的是 `Setup.exe`，但用户体验跟 `.msi` 装出来的效果完全一样（向导式安装、
> 开始菜单、卸载入口），而且是绝大多数 Windows 桌面软件实际在用的方案，所以这里选了它。

**步骤**：

1. 先按第 3 步跑完 `build_windows_exe.bat`，确认 `dist\PersonalFocusGuard\PersonalFocusGuard.exe`
   已经生成。
2. 安装 Inno Setup（一路下一步就行）：https://jrsoftware.org/isdl.php
3. 运行：
   ```
   build_installer.bat
   ```
   会自动找到 Inno Setup 的编译器，读取 `installer.iss`，产出
   `installer_output\PersonalFocusGuard-Setup.exe`。

这个 `Setup.exe` 就是最终可以发给别人用的东西：装在 `%LOCALAPPDATA%` 下，**不需要管理员
权限**，装完有开始菜单项，装的时候可以勾选"创建桌面快捷方式"。升级重装时不会覆盖用户已有的
`config.json`（只在第一次安装时从模板生成）。

**这部分我没法在这边（Linux 云端）实际跑一遍验证**——Inno Setup 是 Windows 专属工具，`installer.iss`
的语法我是照着 Inno Setup 文档写的，但没有真机编译测试过；如果 `build_installer.bat` 跑的时候
`ISCC.exe` 报语法错误，把报错贴给我，我根据具体报错调整 `installer.iss`。

---

## 5. 配置文件字段说明（`config.example.json`）

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
