# 企业工时统计 Agent（合规透明版）

与上一个方案的根本区别：**这是给员工本人用的、他自己能看到数据、自己能知情同意的统计工具**，
不是绕开员工感知/对抗员工终止能力的监控软件。具体体现在四条硬约束上，代码里也是照这个
顺序实现的：

1. **先同意，后运行**——没有同意记录，Agent 直接退出，不采集任何数据。
2. **常驻可见**——系统托盘图标全程显示"工时计时中"，不是后台隐藏进程。
3. **我能看自己的数据**——托盘菜单"查看我的记录"能看到的内容，和上报给公司的内容完全一致，
   不存在"员工看不到但上报了"的字段。
4. **不做强制 kill，不做反卸载**——只统计时长分类，不最小化/结束黑名单进程；员工退出 Agent
   是被允许的操作，只是会被如实记一条"监控于 X 时间被本人停止"的日志（上报同一份 webhook），
   而不是被技术手段拦住不让退出。

> **先考虑现成方案**：如果公司已经有预算做员工工时管理，**优先用成熟产品**而不是这套 DIY
> 脚本——它们的合规披露、审计日志、跨平台支持都比自己写的完善：
> - **Microsoft Intune**（设备合规策略 + 应用使用报告，走 MDM 体系，员工入职协议里天然覆盖）
> - **ActivTrak / Teramind** 等专业员工监控产品（内置同意弹窗、可配置的数据最小化、仅统计模式）
>
> 下面这套方案直接用 Windows 自带的 API 读前台窗口，不依赖任何外部服务或第三方 App，
> 打包出来的 exe 员工双击就能用，适合**想要一个轻量级、自己可控数据流向的统计层**的场景，
> 不是要替代上述产品。

---

## 1. 部署前必须先做的事（技术之外，但比代码更重要）

技术上"合规"只是必要条件，真正让这件事合法合规的是制度层面：

1. **书面告知**：在员工手册 / 入职协议 / IT 使用政策里写清楚：监控的目的（工时统计而非内容
   审查）、采集的数据范围（仅应用分类耗时，不含按键记录、不含截屏、不含具体网址）、数据留存
   期限、谁能看到数据、员工本人如何查看自己的数据、离职后数据如何处理。
2. **知情同意**：这份书面政策要让员工签字确认或在 Agent 首次运行时弹窗勾选同意（本项目的
   `consent_notice.md` 就是给法务/HR 填这段文字用的模板）。
3. **咨询当地劳动法规**：员工监控在不同国家/地区（尤其欧盟 GDPR、部分国内地方性规定）有
   明确的告知与最小化要求，部署前建议法务过一遍。

本项目只负责把"技术实现尊重上述制度"这件事做对，不能替代法务审查。

---

## 2. 环境准备

```bash
cd corp_worktime_agent
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**不需要安装或启动任何外部服务**——前台窗口数据直接通过 Windows API 读取，员工机器上除了这个
exe 本身，不需要再装别的东西。

---

## 3. 配置

```bash
cp config.example.json config.json
```

| 字段 | 说明 |
|---|---|
| `employee_id` | 员工标识（建议用域账号/工号，而不是明文姓名拼音） |
| `categories.work_keywords` / `break_keywords` / `personal_keywords` | 按关键词把窗口分类，三类之外归为 `other` |
| `report_webhook_url` | 公司内部系统/企业微信机器人/钉钉机器人的 Webhook 地址，留空则只在本机记录，不上报 |
| `report_interval_minutes` | 多久上报一次当天的汇总统计，默认 30 分钟 |
| `consent_notice_path` | 同意书文本文件路径，首次运行时完整展示给员工 |

`consent_notice.md` 是法务/HR 需要填写的同意书模板，**上线前必须替换成公司审核过的正式文本**。

---

## 4. 运行

```bash
python worktime_agent.py --config config.json
```

- 首次运行会弹出同意书对话框，不勾选"我已阅读并同意"就无法继续，Agent 直接退出。
- 同意后，系统托盘会出现一个图标，鼠标悬浮提示"工时计时中"；右键菜单：
  - **查看我的记录** —— 弹出今天（及可选的历史）各分类耗时，员工自己随时能看。
  - **监控说明** —— 重新显示同意书内容。
  - **退出 Agent** —— 正常退出，退出事件会被记录并在允许的情况下上报（如实记录"几点被谁停止"，
    不是技术上防止退出）。

---

## 5. 打包成 Windows .exe（免装 Python）

```
build_windows_exe.bat
```

在 Windows 上运行这个脚本，自动建虚拟环境、装依赖、调用 PyInstaller 打包，产出
`dist\CorpWorktimeAgent\CorpWorktimeAgent.exe`。

**注意事项**（和 `personal_focus_guard` 那份一致，额外多一条）：
- 必须在 Windows 上跑，PyInstaller 不支持跨平台编译，这个 `.bat` 在开发环境（Linux 云端）里
  没法验证，请在你自己的 Windows 机器上跑一遍。
- Python 用 python.org 的完整版（带 tkinter），不要用 Microsoft Store 版。
- SmartScreen/杀毒软件对未签名 exe 的"未知发布者"提示是正常现象，不代表程序有问题。
- 打包产物是整个 `dist\CorpWorktimeAgent\` 文件夹，分发时要整体复制，不能只拷贝 exe。
- **额外这一条是企业部署专属的**：批量分发给多台机器前，务必先把 `consent_notice.md`
  换成法务/HR 审核过的正式文本，并把 `config.example.json` 里的 `employee_id`
  按每台机器/每个员工单独生成（不要全公司共用一份配置，否则"查看我的记录"和上报数据
  会对不上号）。

---

## 6. 打包成一键安装程序（可选）

用 [Inno Setup](https://jrsoftware.org/isdl.php)（免费）把 `dist\CorpWorktimeAgent\` 文件夹
打成单文件安装包，员工双击安装，不需要管理员权限，有开始菜单项和可选桌面图标。

> 说明：这里用 Inno Setup 产出 `Setup.exe` 而不是严格意义上的 `.msi`（后者要用更繁琐的
> WiX Toolset）——装出来的用户体验一致（向导安装、开始菜单、卸载入口），只是文件后缀不同，
> 这是大多数 Windows 桌面软件实际采用的方案。

**步骤**：

1. 先跑完第 5 步的 `build_windows_exe.bat`，确认 exe 已生成。
2. 安装 Inno Setup：https://jrsoftware.org/isdl.php
3. 运行 `build_installer.bat`，产出 `installer_output\CorpWorktimeAgent-Setup.exe`。

**重要**：安装包里的 `consent_notice.md` 和 `config.json` 只在**第一次安装**时从模板生成，
后续用新版安装包覆盖升级时不会被覆盖——所以上线前必须先把 `dist\CorpWorktimeAgent\
consent_notice.md`（打包前的源文件，不是装好之后的那份）换成法务/HR 审核过的正式文本，
再跑 `build_installer.bat`，这样打出来的安装包首次安装时员工看到的才是正式版本。

同上，这部分我没法在 Linux 云端实际编译验证，`ISCC.exe` 如果报语法错误，把报错发我。

---

## 7. 数据最小化说明

上报给 `report_webhook_url` 的 JSON，字段和"查看我的记录"里员工看到的完全一致：

```json
{
  "employee_id": "u10234",
  "hostname": "LAPTOP-7F2K",
  "date": "2026-10-17",
  "category_minutes": {"work": 412, "break": 35, "personal": 18, "other": 9},
  "event": "periodic_report"
}
```

不包含具体窗口标题、不包含按键记录、不包含截屏。如果业务上确实需要更细的数据（比如具体应用
名称），必须先更新 `consent_notice.md` 并让员工重新确认同意，且"查看我的记录"展示的内容要
同步加上这部分，保持"员工看到的 = 上报的"这条底线不被打破。
