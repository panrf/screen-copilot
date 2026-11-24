# screen-copilot

> **Screen-reading GUI automation for AI agents** — drive already-logged-in web pages and desktop apps when browser automation (CDP / Playwright) is blocked.

给 AI Agent 装上"眼睛和手"：**截屏 → 视觉理解 → 键鼠执行 → 截图验收**。

不接管浏览器进程、不需要调试端口、不需要账号密码，因此在反自动化机制严格的环境里依然可用。

---

## 为什么需要它

主流的浏览器自动化都要靠调试通道（CDP）：

- Playwright / Selenium 需要启动带调试参数的浏览器
- 而 Chrome / Edge 111+ 在**默认配置目录**下会主动忽略 `--remote-debugging-port`（防止恶意程序窃取登录态）
- 企业安全软件会直接终结任何带远程调试端口的浏览器进程——通常几分钟内

于是出现一个尴尬局面：**任务本身很简单**（在已登录的页面里搜一下、点几下、填两栏），但所有自动化入口都被封死。

读屏方案的思路是绕开这一层：既然人眼看屏幕就能操作，那就让模型也"看屏幕"。

```
┌─────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  截屏    │ → │ 视觉理解  │ → │ 键鼠执行  │ → │ 截图验收  │
│ PIL     │   │ VLM      │   │ pyautogui│   │ PIL      │
└─────────┘   └──────────┘   └──────────┘   └──────────┘
                  ↑                               │
                  └──────── 一次只做一个动作 ──────┘
```

代价是慢（每步要走一次视觉推理），收益是**几乎什么界面都能操作**：老式 ERP、政务系统、没有 API 的内部后台、桌面客户端。

---

## 核心：一个必须修好的坑

**DPI 缩放**。这是这类方案 80% 的故障来源。

Windows 在 125% / 150% 缩放下，DPI-unaware 的 Python 进程看到的是**虚拟分辨率**（如 1280×800），而截图给出的是**物理分辨率**（1920×1200）。坐标按 1.5 倍错位，症状是"点了完全没反应"，极易被误判成页面有透明遮罩。

修法只有一个，且必须在 `import pyautogui` **之前**执行：

```python
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)   # pragma: Windows only
import pyautogui
```

本仓库的 `scripts/screenops.py` 已在模块顶部内置此逻辑。**不要绕开脚本临时手写 pyautogui 代码**，否则会重新踩这个坑。

---

## 安装

### 作为 AI Agent 技能

仓库根目录的 `SKILL.md` 就是技能定义（WorkBuddy / Claude Code 等兼容 `SKILL.md` 约定的宿主可直接识别）。

```bash
# WorkBuddy
git clone https://github.com/panrf/screen-copilot.git ~/.workbuddy/skills/screen-copilot

# Claude Code
git clone https://github.com/panrf/screen-copilot.git ~/.claude/skills/screen-copilot
```

### 只当命令行工具用

```bash
git clone https://github.com/panrf/screen-copilot.git
cd screen-copilot
pip install -r requirements.txt
```

依赖：Python 3.9+ / Windows（DPI 修复依赖 Win32 API）/ `pyautogui`、`pyperclip`、`pillow`。

---

## 快速开始

```bash
# 1. 先诊断坐标系：screenshot 尺寸必须等于系统分辨率
python scripts/screenops.py size

# 2. 抓一张图，交给视觉模型读
python scripts/screenops.py grab --out shot.png

# 3. 按窗口标题精准激活（不要乱点标签栏）
python scripts/screenops.py focus "记事本"

# 4. 点击物理像素坐标
python scripts/screenops.py click 1267 990

# 5. 中文输入走剪贴板（type 只支持 ASCII）
python scripts/screenops.py paste --file msg.txt --enter

# 6. 判断输入框是否真的聚焦
python scripts/screenops.py testfocus 1267 1000
```

## 命令一览

| 命令 | 用途 |
|:---|:---|
| `size` | 诊断坐标系（截图尺寸 vs 系统分辨率） |
| `grab [--out PATH]` | 全屏截图，输出路径与尺寸 |
| `windows` | 列出可见窗口标题 |
| `focus KEYWORD` | 按标题关键字激活窗口 |
| `click X Y [--double] [--right]` | 点击物理像素坐标 |
| `move X Y` | 移动鼠标（滚动前定位用） |
| `scroll N [--at X Y]` | 滚动，N>0 上、N<0 下 |
| `key NAME` | 单键：`enter` `tab` `esc` `space` `pagedown`… |
| `hotkey K1 K2 …` | 组合键，如 `hotkey ctrl v` |
| `type TEXT` | 仅 ASCII（中文请用 `paste`） |
| `paste [--file F] [--text T] [--click X Y] [--enter]` | 剪贴板粘贴，中文安全 |
| `testfocus X Y` | 点击后按空格判焦，输出 `FOCUS_OK` / `FOCUS_FAIL` |

---

## 三条铁律

1. **坐标只从当次截图来。** 绝不复用上一轮坐标，绝不用记忆里的位置。动作前截图，动作后截图验收。
2. **对外动作先确认。** 发消息、提交表单、发布内容，先把最终内容交给用户看并取得明确同意，才执行。
3. **不碰无关窗口和标签。** 只操作目标窗口（按标题 `focus` 精准激活）；长期协作先把目标页分离成独立窗口；切页面用地址栏导航，不要点标签栏。

配套两条工程纪律：

- **一次只做一个动作。** 连续盲发多个动作是失控的根源，中间任何一步错位，后面全废且难定位。
- **同一动作失败两次就换路。** 换坐标 → 换命令 → 请用户手动点一下。这比反复试更省时间。

---

## 什么时候别用它

| 情况 | 应该怎么做 |
|:---|:---|
| 有正规 API / MCP 连接器 | 优先走接口，界面操作是最后手段 |
| 支付、删除、授权、合同签署 | 由用户本人点击，不可代劳 |
| 网银、密码管理器等高敏页面 | 只看不动 |
| 高频批量任务（> 数千次操作） | 读屏太慢，应推动对方提供 API |

---

## 已知限制

- **慢**：每步一次视觉推理，适合几十次量级的操作，不适合流水线
- **依赖视觉模型的位置判断精度**：坐标偏小时按截图真实像素换算（1920/1080 ≈ 1.778）
- **DPI 修复仅 Windows**：macOS / Linux 需移除该调用，并改用对应平台的截图与输入库
- **页面结构大改会失效**：同一站点改版后需重新量坐标

---

## 目录结构

```
screen-copilot/
├── SKILL.md                          # 技能定义（何时用/何时不用、五步闭环、工具表、故障速查）
├── scripts/screenops.py              # 统一 CLI，内置 DPI 修复
├── references/
│   ├── troubleshooting.md            # 10 类故障的根因与处置
│   └── playbooks.md                  # 6 套剧本：发消息/搜索筛选/表单/批量录入/文件对话框/窗口分离
├── docs/DESIGN-NOTES.md              # 设计取舍与踩坑记录
└── requirements.txt
```

---

## English

**screen-copilot** gives an AI agent eyes and hands. Instead of driving the browser through CDP (which is frequently blocked by enterprise security software, and ignored by Chrome/Edge 111+ on default profiles), it captures the screen, lets a vision model read it, and replays mouse/keyboard actions — then screenshots again to verify.

Works with any GUI: web apps, legacy desktop software, systems with no API. Trade-off: slower than protocol-level automation, but vastly more compatible. Human-in-the-loop confirmation is mandatory for any outbound action.

The one bug that matters: **DPI scaling**. On a 150% display, a DPI-unaware Python process sees a 1280×800 coordinate space while screenshots are 1920×1200 — every click lands 1.5× off. Fix it once, before importing `pyautogui`, and never hand-roll your own input code again.

## License

MIT © 2026 panrf
