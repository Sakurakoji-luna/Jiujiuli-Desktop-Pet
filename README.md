# DesktopSprite 智能交互桌宠（V2）

Windows 桌面宠物：极低资源占用，**条件路由规则架构**。采集系统时间与 wttr.in
天气（免 API Key）选择装扮（夏装/冬装/秋装/家居），随机换图触发特殊表情台词；
支持接入 OpenAI 兼容 AI API（如 DeepSeek）进行对话。

技术栈：Python + PySide6（透明无边框窗口）+ requests（天气 / AI API）。

> 📖 **用户手册请见 [使用文档.md](使用文档.md)**（操作方式、装扮与换图机制、对话触发机制、AI 接入、语料库自定义、常见问题）。
> 需求说明见 [接口文档v2.md](接口文档v2.md)。

## 目录结构

```
桌宠项目/
├── main.py               # 入口（--selftest 离线自检）
├── run.bat               # 一键启动（UTF-8 控制台）
├── run_silent.vbs        # 静默启动（已放入系统启动文件夹，开机自启）
├── core/
│   ├── config.py         # 全部可调参数：装扮阈值、换图周期、路由时段、API 配置
│   ├── sprite.py         # 图片库：装扮选择 + 随机分组取图 + 表情标签识别
│   ├── pet_window.py     # 透明无边框窗口、拖拽、右键菜单（登录/对话/退出）
│   ├── weather.py        # wttr.in 低频轮询（天气标志 + 温度）
│   ├── router.py         # 语料路由：时段 x 天气 x 表情标签
│   ├── bubble.py         # 台词气泡框
│   ├── api_client.py     # OpenAI 兼容 API 客户端（含连通性检测）
│   ├── login_dialog.py   # 登录对话框（API 接入界面）
│   ├── chat_input.py     # 聊天输入浮层（屏幕底部，蒙版穿透）+ 后台请求
│   ├── tavern.py         # 酒馆模式提示词引擎（角色卡/世界书/滑动记忆/情绪解析）
│   ├── old_maid.py       # 抽鬼牌小游戏（逻辑模型 + Qt 界面，右键入口）
│   ├── concentration.py  # 神经衰弱小游戏（AI 记忆翻牌，复用扑克牌素材）
│   └── settings.py       # settings.json 读写（位置 + API 配置）
├── data/
│   ├── dialogues.json    # 本地语料库（morning/daytime/evening/late_night/...）
│   ├── kukuri_card.json  # 玖玖里角色卡（人设/对话样本/世界书/后置输出指令）
│   ├── chat_history.json # 聊天短期记忆（运行时自动生成）
│   └── settings.json     # 窗口位置 + API 配置（运行时自动生成）
└── resource/             # 装扮目录（子文件夹 1,2,3 = 动作连贯分组）
    ├── 夏装/  冬装/  秋装/  家居/
    └── 其他/聊天框.png    # 聊天输入栏 UI 素材（1280x720 全屏设计）
```

## 快速开始

```bat
pip install -r requirements.txt
python main.py        # 或双击 run.bat
python main.py --selftest   # 离线自检（离屏渲染，不弹窗口）
```

## V2 核心机制（对照接口文档v2）

| 文档条款 | 实现 |
| --- | --- |
| §1 更换表情轮询机制 | `core/sprite.py`：深夜(22~6)强制家居，其余按温度+天气选装扮；去掉帧轮播，1 分钟周期随机取图；左键点击 = 同装扮下随机切换 1/2/3 分组取图 |
| §2.1 右键登录 | `core/login_dialog.py` + `core/api_client.py`：API 地址/Key/模型填写界面，测试连接按钮验证网址与 Key 可用性 |
| §2.1 右键对话 | `core/chat_input.py`：未登录提示「未连接」；已连接先弹邀请气泡「聊天？正好没什么事，随便聊聊吧」，再在屏幕底部出现聊天输入栏（AI 回复显示在桌宠头顶气泡）——issue 优化：不再突兀弹出对话框 |
| §2.2 左键换表情 | 左键 = 随机分组随机取图（`pet_window.clicked` -> `repick()`） |
| §3 特殊表情 | 文件名含 sad/smile/worry/serious/meditation 标签的图片被选中时，立即弹对应情绪台词气泡 |
| §4 语料库 | `data/dialogues.json` 五时段结构 + random_click + drag_drop；`router.py` 按 时段x天气 选池、按表情标签优先匹配 |

## 开发说明

- **装扮阈值**（`core/config.py`）：`TEMP_HOT=26`/`TEMP_COLD=12`/`RAIN_TEMP_HOT=28`/`RAIN_TEMP_COLD=18`，雨天阈值与晴天分开。
- **单击/双击消歧**：`pet_window` 用「延迟单击 + 系统双击间隔窗口」区分——单击延迟到双击间隔后再触发，窗口内的第二次点击取消单击并发出 `double_clicked`，由 `sprite.pick_same_group()` 在当前数字目录内换图。
- **对话与PNG对应**（issue）：动作直接触发的对话（拖拽/打招呼）在弹气泡后调用 `sprite.pick_emotion()` 按情绪词找图——当前数字目录 → 当前装扮文件夹 → 找不到则保持图片不变。
- **隐藏与托盘**（issue）：右键「隐藏」隐藏桌宠，`QSystemTrayIcon` 常驻系统托盘（单击图标重新显示、右键退出）；「活跃模式」开启时 10 分钟无操作 → 随机位置散步 + `idle_shift_surprise` 语料，关闭则 10 分钟后自动隐藏。
- **抽鬼牌素材**（issue）：明牌使用 `resource/其他/扑克牌/png/` 真实卡图（按手牌数动态缩放），牌背用渐变圆角样式模拟，素材缺失自动降级为文字牌。
- **神经衰弱记忆遗忘**：已知牌超过 `CONCENTRATION_FORGET_THRESHOLD`（12 张）后，玖玖里每回合按难度概率随机遗忘已知位置——全力 0 / 认真 0.1 / 休闲 0.3，难度在游戏窗口选择并持久化。
- **抽鬼牌悬停互动**（issue）：悬停玖玖里的牌背按概率触发互动台词（`old_maid_hover` / 鬼牌专用池 `old_maid_hover_joker`，台词有微妙变化），经 `speak_line` 弹气泡并按情绪词换 PNG。
- **边缘羽化遮罩**（issue 桌宠突兀问题/残影亮线）：`sprite._apply_edge_fade()` 在预加载时用 `DestinationIn` 混合模式做底部（`FADE_RATIO`=25%）与右侧（`RIGHT_FADE_RATIO`=8%）Alpha 渐变；整画布填充 + 百分比停靠点、透明点提前到 98%，杜绝 int() 取整导致的底边 1~2px 残影亮线。
- **路由时段**：`PERIODS = {late_night(22,6), morning(6,9), daytime(9,17), evening(17,22)}`，`late_night` 跨零点。
- **API 兼容**：`api_client._resolve_endpoint()` 兼容 `https://host`、`https://host/v1`、完整路径三种写法；`test()` 用最小请求探测接口，404 时自动尝试 `/v1` 变体，401/403 直接报鉴权错误。
- **酒馆模式提示词**（对照 `AI对话的调优.md`）：`tavern.py` 四层上下文注入——角色卡（人设+对话样本）+ 世界书关键词触发 + 滑动窗口历史（持久化短期记忆）+ 后置 `[emotion]` 输出指令；`parse_ai_response()` 过滤 `<think>` 思维链并剥离情绪标签，标签驱动 `sprite.pick_by_tag()` 切换差分图（当前装扮优先、跨装扮兜底）。
- **线程模型**：天气轮询与 AI 请求均在工作线程执行（守护线程），UI 主线程通过 Qt 信号接收结果，不阻塞界面。
- **自检**：`python main.py --selftest` 覆盖图片库预加载、表情标签识别、装扮选择规则、时段/天气/表情路由、气泡窗口、设置持久化、API 端点解析，共 30+ 项断言。
