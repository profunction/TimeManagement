# 像素时钟：专注 / 摸鱼状态看板（AWTRIX 3 + ESP32）

用一块 WS2812 像素屏物理显示你的「心流计时」和「摸鱼倒计时」。固件用开源项目
**AWTRIX 3**（原名 AWTRIX Light），联动脚本是本目录下的 Python 程序。

> 项目改名提醒：你说的 "AWTRIX Light" 现在的正式名字是 **AWTRIX 3**，仓库地址也
> 从 `Blueforcer/awtrix-light` 迁移到了 `Blueforcer/awtrix3`。作者还在维护一个更新的
> 重写版 `Blueforcer/awtrix-ng`（原生支持 ESP32-S3）。本指南以 AWTRIX 3 为主，
> 两者 API 思路基本一致。

---

## 1. GitHub 仓库与固件

### 1.1 clone 仓库

```bash
git clone https://github.com/Blueforcer/awtrix3.git
cd awtrix3
```

（可选，更新的重写版本：`git clone https://github.com/Blueforcer/awtrix-ng.git`）

### 1.2 硬件采购清单（预算控制在 100 元以内，国内淘宝/拼多多关键词）

| 部件 | 规格要求 | 淘宝搜索关键词 | 参考价 |
|---|---|---|---|
| 主控板 | **ESP32-DevKitC** 或 **ESP32 D1 mini32**（Wi-Fi + 足够 GPIO，Flash ≥4MB） | "ESP32 开发板 D1 mini32" | ¥15–25 |
| 像素屏 | **8×32 WS2812B/SK6812 FC-32 像素灯板**（256 颗灯珠，5V 供电，单根 DATA 线级联） | "FC-32 像素屏 WS2812 8x32" | ¥35–55 |
| 电源 | **5V/3A 及以上**的 USB 电源 + 数据/供电线（256 颗灯全亮时峰值电流可到 ~4–5A，预留余量） | "5V3A 手机充电头" | ¥10–15 |
| 其他 | 杜邦线若干、（可选）470µF/16V 电解电容（接在矩阵 5V-GND 间稳压）、亚克力/3D打印外壳 | "杜邦线 母对母" | ¥5–10 |

合计约 **65–105 元**，压线在百元上下；如果不想接线，直接买成品 **Ulanzi TC001 像素时钟**
（内置 ESP32-C3 + 8×32 屏 + 电池，官方支持刷 AWTRIX），价格通常在 120–150 元，超预算但省去全部焊接/接线工作，是"懒人路线"。

### 1.3 接线说明（DIY 路线）

AWTRIX 的矩阵数据引脚**不是固件里硬编码的**，而是在首次开机的 Web 配置向导里手动选择
GPIO 号的，所以接线只需要三根线：

| 像素屏引脚 | 接到 ESP32 | 说明 |
|---|---|---|
| 5V | ESP32 的 5V / VIN | 建议直接从电源接，不要只靠 ESP32 USB 供电给矩阵供电 |
| GND | ESP32 GND | 必须和 ESP32 共地 |
| DATA (DIN) | ESP32 任意**输出能力正常**的 GPIO，常用 `GPIO32` | 配置向导里要填这个引脚号，记下来 |

**避坑**：
- 不要选 `GPIO34–39`（仅输入，无法驱动 DATA 线）。
- 不要选 `GPIO6–11`（接内部 Flash）、`GPIO0/2/12/15`（启动选用的 strapping pin，接了外设可能导致开机异常)。
- 如果屏幕出现跳灯/花屏，优先怀疑：没加电容、电源电流不够、DATA 线太长没加 300Ω~470Ω 串联电阻。

### 1.4 刷机

**方式 A：浏览器刷机（最简单，推荐先用这个）**

1. 用 **Chrome 或 Edge** 打开 AWTRIX 的 Web Flasher 页面（在仓库 README 里能找到最新链接，
   通常形如 `https://blueforcer.github.io/awtrix3/` 或仓库 Releases 页附带的安装页面）。
2. USB 数据线把 ESP32 接到电脑，网页里选中对应的串口，点 Install。
3. 刷完后设备会开一个 Wi-Fi 热点（类似 `AWTRIX-XXXX`），手机/电脑连上它，
   按向导填入你家 Wi-Fi 的 SSID/密码，并在"硬件设置"里选矩阵尺寸 `32x8`、
   数据引脚（即你接线用的 GPIO 号）。

**方式 B：PlatformIO 本地编译刷机（要自定义固件/离线用这个）**

```bash
# 需要先装好 VS Code + PlatformIO 插件，或者用命令行版
pip install platformio

cd awtrix3
pio run -e esp32dev          # 编译，环境名以 platformio.ini 里实际定义的为准
pio run -e esp32dev -t upload --upload-port /dev/ttyUSB0   # 编译+刷机
```

刷完后同样走一次 Wi-Fi 配网 + 矩阵参数设置向导。

### 1.5 拿到设备 IP / 打开 API 文档

设备联网后，在路由器后台或 AWTRIX 自己的网页 UI（`设置 → 关于/网络`）里能看到它的局域网 IP，
记下来，比如 `192.168.1.50`。

**重要**：AWTRIX 的 Web UI 自带一个「API」帮助页（通常在设置菜单里，或直接访问
`http://<设备IP>/api`），会列出*你当前固件版本*准确的字段名（不同版本之间
`text`/`message`、`duration`/`durationMs` 等字段名可能有差异）。刷机联网后，
**务必先打开这个页面核对一下字段名**，如果和下面脚本里的 JSON 字段不完全一致，
照着设备自己给出的 schema 改一下 `awtrix_client.py` 里的 key 就行。

---

## 2. HTTP / MQTT API 用法

AWTRIX 支持两种推送方式，二选一即可（脚本里都实现了，用环境变量切换）：

### 2.1 HTTP（默认，零配置，推荐先用这个）

本机局域网直接 POST 到设备即可，不需要任何中间件：

```bash
curl -X POST "http://<设备IP>/api/custom?name=focus" \
     -H "Content-Type: application/json" \
     -d '{"text":"25:13","color":"#00FF55","icon":"cat"}'
```

- `name=focus` 是"自定义 App"的名字，重复用同一个名字推送 = 刷新这个 App 的内容。
- 清除一个自定义 App：POST 空对象 `{}` 到同一个 `name`。
- 一次性全屏通知/告警：`POST /api/notify`，payload 同样是 JSON，常用字段 `text`、
  `color`、`hold`（是否常驻直到手动关闭）、`sound`。

### 2.2 MQTT（如果你家里已经有 Home Assistant / MQTT broker，更适合长期联动）

AWTRIX 在设置里填好 MQTT broker 地址、用户名密码后，会订阅一套 `<prefix>/...` 主题，
其中 `<prefix>` 是你在设置里起的设备名（默认即设备名）：

```
topic:   <prefix>/custom/<appname>
payload: 跟 HTTP /api/custom 一样的 JSON 字符串
```

### 2.3 "摸鱼配额"的呈现方式

- **进度条**：JSON 里加 `"progress": 0-100` 和 `"progressC":"#颜色"`，AWTRIX 会在
  屏幕底部画一条进度条，天然适合做倒计时配额。
- **最后 3 分钟全屏红光闪烁**：AWTRIX 的部分版本支持 `"effect":"blink"`，但不同
  版本/固件支持程度不一致，**为了保证一定能跑通**，脚本采用更稳的做法——由 Python
  每秒自己交替推送"红底文字"和"清空(黑屏)"两帧，手搓出闪烁效果，不依赖固件是否
  支持某个 effect 名字。

---

## 3. 运行联动脚本

见同目录 `focus_tracker.py` 和 `awtrix_client.py`，用法：

```bash
pip install -r requirements.txt
cp .env.example .env     # 填入设备 IP / MQTT 配置
python focus_tracker.py focus          # 开始专注，心流计时开始走
python focus_tracker.py slack          # 切到摸鱼模式，15 分钟倒计时，最后3分钟闪红
python focus_tracker.py stop           # 清屏/回到空闲
python focus_tracker.py status         # 查看当前状态
python focus_tracker.py run            # 后台常驻进程：按当前状态持续刷新像素屏
```

把 `focus_tracker.py focus` / `slack` / `stop` 绑定到你习惯用的任意「专注状态来源」上
即可（全局热键、Raycast/AutoHotkey 脚本、现有的时间管理 App 在状态切换时调用一下这个
命令），`run` 常驻在后台负责把当前状态实时画到像素屏上。状态保存在
`~/.timemanagement/awtrix_state.json`，所以命令行调用和后台进程是解耦的。
