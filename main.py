# -*- coding: utf-8 -*-
"""DesktopSprite 智能交互桌宠 V2 —— 主入口。

用法:
    python main.py             正常启动桌宠
    python main.py --selftest  离线自检（离屏渲染，不弹窗口）
"""
import datetime
import logging
import os
import random
import sys
import tempfile
import threading
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (QApplication, QMenu, QMessageBox,
                               QSystemTrayIcon)

from core import config, settings
from core.api_client import ApiClient
from core.bubble import BubbleWindow
from core.chat_input import ChatInputBox, ChatWorker
from core.concentration import ConcentrationDialog
from core.login_dialog import LoginDialog
from core.old_maid import OldMaidDialog
from core.pet_window import PetWindow
from core.router import DialogueRouter
from core.sprite import SpriteLibrary, choose_outfit, tag_of
from core.tavern import TavernPromptEngine, WEATHER_CN
from core.weather import WeatherCollector


def _setup_encoding():
    """Windows 控制台默认 GBK，统一为 UTF-8 避免中文乱码。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            # pythonw（无控制台）下流为 None，任何 print 都会抛 AttributeError；
            # 重定向到 devnull，保证静默启动路径不崩溃
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main():
    _setup_encoding()
    logging.basicConfig(level=logging.INFO,
                        format="[%(asctime)s] %(name)s %(levelname)s: %(message)s")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # 气泡隐藏后程序不退出

    active_mode = settings.load_settings().get("active_mode",
                                               config.ACTIVE_MODE_DEFAULT)
    pet = PetWindow(active_mode=active_mode)
    bubble = BubbleWindow()
    sprite = SpriteLibrary()
    router = DialogueRouter()
    weather = WeatherCollector()
    api = ApiClient()

    sprite.preload()
    sprite.image_changed.connect(lambda: pet.set_pixmap(sprite.current_pixmap))

    # ---------------------------------------------------------- 表情轮询机制
    # 装扮冷暖顺序：用于判断换装方向（越靠后越“冷”）
    _OUTFIT_WARMTH = {"夏装": 0, "秋装": 1, "冬装": 2, "家居": 3}
    _weather_ok = True
    _started_at = datetime.datetime.now()

    def speak_for_tag(tag):
        """取到带表情标签的图片 -> 弹对应情绪的台词气泡。"""
        now = datetime.datetime.now()
        text, emo = router.get_response(weather.get_condition(),
                                        emotion=tag, hour=now.hour)
        print(f"[Dialogue] 时间 {now:%H:%M} | 天气 {weather.get_condition()} | "
              f"表情 {tag} | 台词: {text} (emotion={emo})")
        bubble.show_text(text, anchor=pet)

    def repick():
        """1min 周期 / 左键点击触发：换装扮（如需要）-> 随机分组随机取图；
        取到特殊表情图片时立即弹出对应台词气泡。"""
        nonlocal _weather_ok
        if not pet.isVisible():
            return   # 已隐藏时暂停一切自动行为
        now = datetime.datetime.now()
        temp = weather.get_temp()

        # 天气不可用 -> 无法判断换装，说感冒台词
        # （启动后 15 秒内是首次拉取的宽限期，避免误报）
        if temp is None:
            if _weather_ok and (now - _started_at).total_seconds() > 15:
                bubble.show_text("有点感冒了……", anchor=pet)
                _weather_ok = False
        else:
            _weather_ok = True

        outfit = choose_outfit(now.hour, temp, weather.get_condition())
        if outfit != sprite.current_outfit:
            old = sprite.current_outfit
            sprite.set_outfit(outfit)
            print(f"[Outfit] 装扮切换 -> {sprite.current_outfit}")
            # 换装方向台词：换更厚的 -> 天凉了；换更薄的 -> 有点热了
            old_idx = _OUTFIT_WARMTH.get(old, -1)
            new_idx = _OUTFIT_WARMTH.get(outfit, -1)
            if 0 <= old_idx < new_idx:
                bubble.show_text("天凉了……你也要注意", anchor=pet)
            elif 0 <= new_idx < old_idx:
                bubble.show_text("有点热了", anchor=pet)

        tag = sprite.pick_random()
        if tag:
            speak_for_tag(tag)

    def on_double_click():
        """快速双击：在当前数字目录内切换图片（不换分组）。"""
        if sprite.pick_same_group():
            tag = sprite.current_tag
            if tag:
                speak_for_tag(tag)

    pet.clicked.connect(repick)
    pet.double_clicked.connect(on_double_click)
    pick_timer = QTimer()
    pick_timer.timeout.connect(repick)
    pick_timer.start(config.PICK_INTERVAL_MS)

    def speak_line(text, emo):
        """动作直接触发的对话：弹气泡后按情绪词同步图片。

        issue（对话与PNG不对应）：先当前数字目录找 -> 再当前装扮找 ->
        都没有则保持图片不变。
        """
        bubble.show_text(text, anchor=pet)
        if emo:
            sprite.pick_emotion(emo)

    # 拖拽结束 -> drag_drop 语料池
    def on_dragged():
        text, emo = router.get_pool_line("drag_drop")
        speak_line(text, emo)

    pet.dragged.connect(on_dragged)

    # ---------------------------------------------------------- 登录 / 对话
    login_dialog = None
    chat_box = ChatInputBox()
    tavern = TavernPromptEngine()

    def weather_env():
        """组装注入提示词的环境文本（天气 + 温度，线程内只读缓存）。"""
        text = WEATHER_CN.get(weather.get_condition(), "未知")
        temp = weather.get_temp()
        if temp is not None:
            text += f"，{temp:.0f}°C"
        return text

    chat_worker = ChatWorker(api, tavern, weather_env)

    def open_login():
        nonlocal login_dialog
        if login_dialog is None:
            login_dialog = LoginDialog(api)
        login_dialog.show()
        login_dialog.raise_()
        login_dialog.activateWindow()

    def open_chat():
        """issue 优化：不直接弹对话框，先气泡邀请，再在屏幕底部出现输入栏。"""
        if not api.is_connected:
            QMessageBox.warning(pet, "未连接",
                                "尚未接入 AI API，请先右键 -> 登录 完成配置。")
            return
        bubble.show_text("聊天？正好没什么事，随便聊聊吧", anchor=pet)
        QTimer.singleShot(1200, lambda: chat_box.show_box(pet))

    def send_to_ai(text):
        chat_box.set_busy(True)
        threading.Thread(target=chat_worker.run, args=(text,),
                         daemon=True).start()

    def on_ai_reply(text, emotion):
        chat_box.set_busy(False)
        bubble.show_text(text, duration_ms=config.CHAT_BUBBLE_DURATION_MS,
                         anchor=pet)
        # AI 回复的情绪标签驱动差分图（优先当前装扮，跨装扮兜底）
        if emotion and sprite.pick_by_tag(emotion):
            print(f"[Chat] AI 回复情绪 [{emotion}] -> 已切换对应差分图")
        elif emotion:
            print(f"[Chat] AI 回复情绪 [{emotion}] -> 无对应图片，保持当前")

    def on_ai_failed(err):
        chat_box.set_busy(False)
        bubble.show_text(f"请求失败：{err}", anchor=pet)

    chat_box.submitted.connect(send_to_ai)
    chat_worker.reply.connect(on_ai_reply)
    chat_worker.failed.connect(on_ai_failed)

    pet.login_requested.connect(open_login)
    pet.chat_requested.connect(open_chat)

    # ---------------------------------------------------------- 抽鬼牌游戏
    game_dialog = None

    def open_game():
        """先触发台词，再弹出游戏窗口。"""
        nonlocal game_dialog
        bubble.show_text("即使知道会输还要玩吗", anchor=pet)
        QTimer.singleShot(1200, show_game_dialog)

    def show_game_dialog():
        nonlocal game_dialog
        if game_dialog is None:
            # 悬停台词走 speak_line：气泡 + 按情绪词换 PNG（与 issue 逻辑一致）
            game_dialog = OldMaidDialog(router, on_line=speak_line)
        game_dialog.new_game()
        game_dialog.show()
        game_dialog.raise_()
        game_dialog.activateWindow()

    pet.game_requested.connect(open_game)

    # ---------------------------------------------------------- 神经衰弱游戏
    concentration_dialog = None

    def open_concentration():
        """先触发台词，再弹出游戏窗口。"""
        nonlocal concentration_dialog
        bubble.show_text("要来玩一局神经衰弱吗？", anchor=pet)
        QTimer.singleShot(1200, show_concentration_dialog)

    def show_concentration_dialog():
        nonlocal concentration_dialog
        if concentration_dialog is None:
            concentration_dialog = ConcentrationDialog(router)
        concentration_dialog.new_game()
        concentration_dialog.show()
        concentration_dialog.raise_()
        concentration_dialog.activateWindow()

    pet.concentration_requested.connect(open_concentration)

    # ---------------------------------------------------------------- 启动
    sprite.set_outfit(choose_outfit(datetime.datetime.now().hour,
                                    weather.get_temp(),
                                    weather.get_condition()))
    repick()
    pet.show()
    # 启动 3 秒后打个招呼（random_click 池），同样按情绪词同步图片
    def greet():
        text, emo = router.get_pool_line("random_click")
        speak_line(text, emo)

    QTimer.singleShot(3000, greet)

    # -------------------------------------------- 隐藏 / 托盘 / 活跃模式
    def show_pet():
        if not pet.isVisible():
            pet.show()
        note_activity()
        repick()

    def hide_pet():
        bubble.hide()
        chat_box.hide()
        pet.hide()

    def set_active_mode(on):
        nonlocal active_mode
        active_mode = on
        data = settings.load_settings()
        data["active_mode"] = on
        settings.save_settings(data)
        print(f"[ActiveMode] 活跃模式 {'开启' if on else '关闭'}")

    _last_activity = time.monotonic()

    def note_activity():
        nonlocal _last_activity
        _last_activity = time.monotonic()

    def wander():
        """活跃模式：无操作超时后随机位置散步，并按语料说一句。"""
        screen = (QGuiApplication.screenAt(pet.frameGeometry().center())
                  or QGuiApplication.primaryScreen())
        geo = screen.availableGeometry()
        x = random.randint(geo.left() + 10,
                           max(geo.left() + 10, geo.right() - pet.width() - 10))
        y = random.randint(geo.top() + 10,
                           max(geo.top() + 10, geo.bottom() - pet.height() - 10))
        pet.move(x, y)
        pet.moved.emit()
        text, emo = router.get_pool_line("idle_shift_surprise")
        print(f"[ActiveMode] 散步 -> ({x},{y}) | {text} (emotion={emo})")
        speak_line(text, emo)

    def check_idle():
        """10 分钟无任何指令：活跃模式 -> 散步；否则 -> 隐藏。"""
        nonlocal _last_activity
        if not pet.isVisible():
            return
        if time.monotonic() - _last_activity < config.IDLE_TIMEOUT:
            return
        _last_activity = time.monotonic()
        if active_mode:
            wander()
        else:
            hide_pet()

    idle_timer = QTimer()
    idle_timer.timeout.connect(check_idle)
    idle_timer.start(config.IDLE_CHECK_INTERVAL)

    pet.hide_requested.connect(hide_pet)
    pet.active_mode_toggled.connect(set_active_mode)
    for sig in (pet.clicked, pet.double_clicked, pet.dragged,
                pet.login_requested, pet.chat_requested, pet.game_requested,
                pet.concentration_requested):
        sig.connect(note_activity)
    chat_box.submitted.connect(note_activity)

    # 系统托盘：隐藏后可从这里重新显示
    tray = QSystemTrayIcon(QIcon(config.TRAY_ICON_PATH))
    tray.setToolTip("DesktopSprite")
    tray_menu = QMenu()
    tray_show_act = tray_menu.addAction("显示桌宠")
    tray_show_act.triggered.connect(show_pet)
    tray_menu.addSeparator()
    tray_quit_act = tray_menu.addAction("退出")
    tray_quit_act.triggered.connect(app.quit)
    tray.setContextMenu(tray_menu)
    tray.activated.connect(
        lambda reason: show_pet()
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick) else None)
    tray.show()

    pet.moved.connect(bubble.reposition)

    weather.start()
    app.aboutToQuit.connect(weather.stop)
    app.aboutToQuit.connect(pet.save_position)
    sys.exit(app.exec())


def selftest():
    """离线自检：离屏渲染，验证 V2 的图片库/装扮选择/语料路由/窗口气泡。"""
    _setup_encoding()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from core import settings as settings_mod
    from core.bubble import BubbleWindow
    from core.pet_window import PetWindow
    from core.weather import normalize_condition

    fails = []

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    app = QApplication(sys.argv)

    # ---- 图片库与装扮选择（V2 §1）----
    print("== V2.1 图片库与装扮选择 ==")
    lib = SpriteLibrary()
    n = lib.preload()
    check(f"预加载 {n} 个装扮目录", n >= 1)
    check("可用装扮包含夏装", "夏装" in lib.available_outfits())
    check("表情标签识别 (smile)", tag_of("kukuri_kao_smile_39.png") == "smile")
    check("表情标签识别 (worry)", tag_of("kukuri_kao_worry_36.png") == "worry")
    check("表情标签识别 (angry)", tag_of("kukuri_kao_angry_37.png") == "angry")
    check("表情标签识别 (无标签)", tag_of("kukuri_kao_14.png") is None)
    lib.set_outfit("夏装")
    lib.pick_random()
    check("随机取图有效", not lib.current_pixmap.isNull())
    groups = set()
    for _ in range(30):
        lib.pick_random()
        groups.add(lib._display[1])
    check("左键随机切换 1/2/3 分组", len(groups) >= 2)
    check("按情绪取图 (smile，跨装扮兜底)", lib.pick_by_tag("smile"))
    check("按情绪取图 (angry)", lib.pick_by_tag("angry"))
    check("按情绪取图 (不存在标签保持 False)", not lib.pick_by_tag("nonexist"))
    check("情绪取图后展示图有效", not lib.current_pixmap.isNull())

    # 双击：当前数字目录内切换图片
    lib.set_outfit("夏装")
    lib._display = ("夏装", "1", 0)
    before_key = lib.current_pixmap.cacheKey()
    ok = lib.pick_same_group()
    check("双击同组切换成功",
          ok and lib._display[:2] == ("夏装", "1")
          and lib.current_pixmap.cacheKey() != before_key)
    saved_entries = lib._outfits["夏装"]["1"]
    lib._outfits["夏装"]["1"] = saved_entries[:1]   # 模拟单张图分组
    check("单张图分组双击返回 False", not lib.pick_same_group())
    lib._outfits["夏装"]["1"] = saved_entries

    # 动作触发对话的情绪图同步（issue: 对话与PNG不对应）
    lib.set_outfit("夏装")
    lib._display = ("夏装", "1", 0)
    ok = lib.pick_emotion("sad")
    check("情绪图同步：当前分组内命中",
          ok and lib._display[:2] == ("夏装", "1")
          and lib._outfits["夏装"]["1"][lib._display[2]][1] == "sad")
    ok = lib.pick_emotion("worry")
    check("情绪图同步：分组没有 -> 装扮内跨分组",
          ok and lib._display[:2] == ("夏装", "3"))
    before = lib._display
    ok = lib.pick_emotion("meditation")
    check("情绪图同步：装扮内也没有 -> 保持图片不变",
          not ok and lib._display == before)

    # 底部 + 右侧羽化遮罩（issue: 桌宠突兀问题 / 底边残影亮线）
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QPixmap as _QPixmap
    probe = _QPixmap(100, 100)
    probe.fill(_Qt.white)
    faded = SpriteLibrary._apply_edge_fade(probe)
    img = faded.toImage()
    check("羽化：顶部保持不透明", img.pixelColor(50, 5).alpha() == 255)
    check("羽化：底边完全透明", img.pixelColor(50, 99).alpha() == 0)
    check("羽化：底边无残影亮线（倒数第2行也透明）",
          img.pixelColor(50, 98).alpha() == 0)
    check("羽化：右侧发梢渐隐",
          img.pixelColor(99, 50).alpha() < img.pixelColor(50, 50).alpha())
    check("羽化：左侧保持不透明", img.pixelColor(1, 50).alpha() == 255)

    check("深夜(23点)强制家居", choose_outfit(23, 30, "Sunny") == "家居")
    check("凌晨(2点)强制家居", choose_outfit(2, 30, "Sunny") == "家居")
    check("高温(30°C)穿夏装", choose_outfit(12, 30, "Sunny") == "夏装")
    check("低温(5°C)穿冬装", choose_outfit(12, 5, "Cloudy") == "冬装")
    check("温和(18°C)穿秋装", choose_outfit(12, 18, "Sunny") == "秋装")
    check("雨天(19°C)穿秋装", choose_outfit(12, 19, "Rain") == "秋装")
    check("雨天(5°C)穿冬装", choose_outfit(12, 5, "Rain") == "冬装")
    check("无温度数据回退默认装扮",
          choose_outfit(12, None, "Sunny") == config.DEFAULT_OUTFIT)

    # ---- 语料路由（V2 §4）----
    print("== V2.4 语料路由 ==")
    r = DialogueRouter()
    check("时段: 8点=早晨", r.get_period(8) == "morning")
    check("时段: 12点=白天", r.get_period(12) == "daytime")
    check("时段: 19点=傍晚", r.get_period(19) == "evening")
    check("时段: 23点=深夜", r.get_period(23) == "late_night")
    check("时段: 2点=深夜", r.get_period(2) == "late_night")
    text, emo = r.get_response("Sunny", emotion="serious", hour=8)
    check("早晨+晴天+serious 表情匹配", emo == "serious" and bool(text))
    text, emo = r.get_response("Rain", hour=8)
    check("早晨+雨天路由", bool(text))
    text, emo = r.get_response("Cloudy", hour=15)
    check("白天+阴天路由", bool(text))
    text, emo = r.get_response("Sunny", hour=23)
    check("深夜路由", bool(text))
    text, emo = r.get_pool_line("drag_drop")
    check("drag_drop 语料池", bool(text))

    # ---- 天气归一化（V2 依赖温度与天气标志）----
    print("== 天气归一化 ==")
    cases = {"Partly cloudy": "Cloudy", "Light rain": "Rain", "Clear": "Sunny",
             "Moderate snow": "Snow", "": "Unknown"}
    for desc, want in cases.items():
        got = normalize_condition(desc)
        check(f"{desc!r} -> {got}", got == want)

    # ---- 窗口与气泡 ----
    print("== 窗口与气泡 ==")
    pet = PetWindow()
    pet.set_pixmap(lib.current_pixmap)
    check("窗口尺寸 = 缩放后帧尺寸",
          pet.width() == lib.current_pixmap.width())
    bubble = BubbleWindow()
    bubble.show_text("V2 自检气泡。", anchor=pet)
    check("气泡窗口有效", bubble.width() > 0 and bubble.height() > 0)
    bubble.hide()

    # 单击/双击消歧（QTest 模拟真实鼠标事件）
    from PySide6.QtCore import QPoint as _QPoint
    from PySide6.QtTest import QTest
    clicks, dbls = [], []
    pet.clicked.connect(lambda: clicks.append(1))
    pet.double_clicked.connect(lambda: dbls.append(1))
    pet.show()
    QTest.qWait(50)
    pos = _QPoint(pet.width() // 2, pet.height() // 2)
    QTest.mouseClick(pet, _Qt.LeftButton, pos=pos)
    QTest.mouseClick(pet, _Qt.LeftButton, pos=pos)
    QTest.qWait(150)
    check("快速双击触发 double_clicked 且抑制单击", not clicks and len(dbls) == 1)
    QTest.mouseClick(pet, _Qt.LeftButton, pos=pos)
    QTest.qWait(QApplication.doubleClickInterval() + 200)
    check("间隔单击触发 clicked", len(clicks) == 1)
    pet.hide()

    # ---- 聊天输入浮层（issue 优化）----
    print("== 聊天输入浮层 ==")
    from core.chat_input import ChatInputBox
    box = ChatInputBox()
    check("聊天框素材已加载", not box._src.isNull())
    box.show_box(pet)
    check("聊天输入浮层尺寸有效", box.width() > 0 and box.height() > 0)
    check("输入栏以外区域已蒙版穿透", not box.mask().isEmpty())
    box.hide()

    # ---- 酒馆模式提示词引擎 ----
    print("== 酒馆模式提示词引擎 ==")
    import json as _json
    from core.tavern import TavernPromptEngine
    tmp_card = os.path.join(tempfile.gettempdir(), "pet_card_test.json")
    tmp_hist = os.path.join(tempfile.gettempdir(), "pet_hist_test.json")
    card = {"char_name": "测试角色", "user_name": "用户",
            "system_prompt": "系统人设",
            "mes_example": "<START>\n{{user}}: hi\n{{char}}: [smile]hello\n",
            "world_book": [{"keys": ["雨惑城"], "content": "世界书词条"}],
            "post_history_instructions": "后置指令"}
    with open(tmp_card, "w", encoding="utf-8") as f:
        _json.dump(card, f, ensure_ascii=False)
    eng = TavernPromptEngine(tmp_card, tmp_hist, max_history=4)
    msgs = eng.build_messages("提到雨惑城", current_weather="下雨")
    check("System 注入世界书词条", "世界书词条" in msgs[0]["content"])
    check("System 注入环境上下文", "时间" in msgs[0]["content"]
          and "下雨" in msgs[0]["content"])
    check("System 注入对话样本", "hello" in msgs[0]["content"])
    check("用户消息末尾带后置指令", "后置指令" in msgs[-1]["content"])
    text, emo = eng.parse_ai_response("[smile]那就休息吧。", "好累")
    check("情绪标签解析 (smile)", emo == "smile" and text == "那就休息吧。")
    text, emo = eng.parse_ai_response("<think>思考中</think>[worry]注意身体。", "困")
    check("思维链过滤 + 标签解析 (worry)",
          emo == "worry" and text == "注意身体。")
    text, emo = eng.parse_ai_response("没有标签的回复", "hi")
    check("无标签兜底 serious", emo == "serious" and text == "没有标签的回复")
    for i in range(6):
        eng.parse_ai_response(f"[smile]回复{i}", f"消息{i}")
    check("历史滑动窗口截断", len(eng.chat_history) == 4)
    msgs2 = eng.build_messages("新消息", current_weather="晴")
    check("组装消息历史条数不超窗口", len(msgs2) - 2 <= 4)
    os.remove(tmp_card)
    os.remove(tmp_hist)

    # ---- 抽鬼牌游戏 ----
    print("== 抽鬼牌游戏 ==")
    import random as _random
    from core.old_maid import JOKER, OldMaidDialog, OldMaidGame, card_file
    # 扑克牌素材映射覆盖 52 张普通牌 + 小丑
    card_png_dir = os.path.join(config.RESOURCE_DIR, "其他", "扑克牌", "png")
    check("卡牌素材覆盖 52 张普通牌",
          all(os.path.exists(os.path.join(card_png_dir,
                                          card_file((r, s))))
              for s in "♠♥♦♣" for r in "A23456789TJQK"))
    check("小丑素材存在",
          os.path.exists(os.path.join(card_png_dir, card_file(JOKER))))
    finished = joker_ok = no_pairs = True
    for _ in range(20):
        g = OldMaidGame()
        steps = 0
        while g.winner is None and steps < 200:
            if g.turn == "player":
                g.draw_from_ai(_random.randrange(len(g.ai_hand)))
            else:
                g.ai_turn()
            steps += 1
        if g.winner is None:
            finished = False
            break
        loser = g.player_hand if g.winner == "ai" else g.ai_hand
        if not any(c[0] == "JOKER" for c in loser):
            joker_ok = False
        for hand in (g.player_hand, g.ai_hand):
            if len({c[0] for c in hand}) != len(hand):
                no_pairs = False
    check("20 局模拟全部结束", finished)
    check("败者手持小丑", joker_ok)
    check("任意时刻手中无对子", no_pairs)
    dlg = OldMaidDialog(r)
    check("游戏窗口初始化发牌", len(dlg._game.player_hand) + len(dlg._game.ai_hand) > 0)
    check("游戏窗口按钮与牌数一致", len(dlg._card_btns) == len(dlg._game.ai_hand))

    # 悬停互动台词（issue: 抽鬼牌优化）
    text, emo = r.get_pool_line("old_maid_hover")
    check("old_maid_hover 语料池", bool(text))
    text, emo = r.get_pool_line("old_maid_hover_joker")
    check("old_maid_hover_joker 语料池", bool(text))
    called = []
    dlg_h = OldMaidDialog(r, on_line=lambda t, e: called.append((t, e)))
    dlg_h._game.turn = "player"
    # 悬停测试固定一手含小丑的牌：发牌随机，小丑约 51% 落在玩家手中，
    # 用 next(...) 在玖玖里手牌里找会抛 StopIteration 导致自检中断。
    dlg_h._game.ai_hand = [JOKER, ("A", "♠")]
    joker_idx, normal_idx = 0, 1
    _ch, _jch, _cd = (config.OLD_MAID_HOVER_CHANCE,
                      config.OLD_MAID_HOVER_JOKER_CHANCE,
                      config.OLD_MAID_HOVER_COOLDOWN_MS)
    config.OLD_MAID_HOVER_CHANCE = 1.0
    config.OLD_MAID_HOVER_JOKER_CHANCE = 1.0
    config.OLD_MAID_HOVER_COOLDOWN_MS = 0
    try:
        dlg_h._on_card_hover(normal_idx)
        dlg_h._on_card_hover(joker_idx)
    finally:
        config.OLD_MAID_HOVER_CHANCE = _ch
        config.OLD_MAID_HOVER_JOKER_CHANCE = _jch
        config.OLD_MAID_HOVER_COOLDOWN_MS = _cd
    check("悬停触发两条互动台词", len(called) == 2)
    check("普通牌悬停台词来自普通池",
          called[0][0] in [e["text"] for e in r.corpus["old_maid_hover"]])
    check("鬼牌悬停台词来自专用池",
          called[1][0] in [e["text"] for e in r.corpus["old_maid_hover_joker"]])
    check("悬停台词带有效情绪词",
          all(e in config.EMOTION_TAGS for _, e in called))
    dlg_h.close()
    # 明牌使用素材渲染（首个手牌标签带图片）
    first = None
    for i in range(dlg._player_row.count()):
        w = dlg._player_row.itemAt(i).widget()
        if w is not None:
            first = w
            break
    check("玩家明牌使用扑克牌素材",
          first is not None and first.pixmap() is not None
          and not first.pixmap().isNull())
    dlg.close()

    # 活跃模式语料池
    text, emo = r.get_pool_line("idle_shift_surprise")
    check("idle_shift_surprise 语料池", bool(text) and emo in config.EMOTION_TAGS)
    text, emo = r.get_pool_line("concentration")
    check("concentration 语料池", bool(text))

    # ---- 神经衰弱游戏 ----
    print("== 神经衰弱游戏 ==")
    from core.concentration import ConcentrationDialog, ConcentrationGame
    sim_ok = True
    for _ in range(10):
        g = ConcentrationGame(pairs=4)
        steps = 0
        while g.winner is None and steps < 300:
            steps += 1
            if g.turn == "player":
                while True:
                    avail = [i for i in range(len(g.board))
                             if not g.revealed[i] and not g.taken[i]]
                    res = g.player_pick(_random.choice(avail))
                    if res == "miss":
                        g.flip_back(*g.last_pair)
                        break
                    if res in ("match", "end"):
                        break
            else:
                i, j = g.ai_choose()
                res = g.ai_flip(i, j)
                if res == "miss":
                    g.flip_back(i, j)
        if g.winner is None or not all(g.taken) \
                or g.player_pairs + g.ai_pairs != 4:
            sim_ok = False
            break
    check("神经衰弱 10 局模拟正常结束", sim_ok)

    g2 = ConcentrationGame(pairs=4)
    # AI 记忆测试：已知同点数两张 -> 直接选
    by_rank = {}
    for i, (rank, _) in enumerate(g2.board):
        by_rank.setdefault(rank, []).append(i)
    a, b = next(v for v in by_rank.values() if len(v) == 2)
    g2.known = {a, b}
    g2.taken = [i not in (a, b) for i in range(len(g2.board))]
    pick = g2.ai_choose()
    check("玖玖里优先拿记忆中已知的对子", set(pick) == {a, b})

    # 记忆遗忘机制：已知牌超过 12 张后按难度随机遗忘
    g3 = ConcentrationGame(pairs=8)
    g3.known = set(range(16))
    g3.difficulty = "全力"
    check("全力模式不遗忘", g3.ai_forget() == 0 and len(g3.known) == 16)
    g3.known = set(range(12))
    g3.difficulty = "休闲"
    check("已知牌未超阈值不遗忘", g3.ai_forget() == 0 and len(g3.known) == 12)
    _random.seed(20261014)   # 固定种子，保证断言稳定
    means = {}
    for mode in ("认真", "休闲"):
        total = 0
        for _ in range(100):
            g4 = ConcentrationGame(pairs=8)
            g4.known = set(range(16))
            g4.difficulty = mode
            total += g4.ai_forget()
        means[mode] = total / 100
    _random.seed()
    check(f"遗忘均值 认真({means['认真']:.2f}) < 休闲({means['休闲']:.2f})",
          means["认真"] < means["休闲"])
    check("休闲模式确有遗忘", means["休闲"] > 2)

    cd = ConcentrationDialog(r)
    check("神经衰弱棋盘按钮数 = 16", len(cd._btns) == 16)
    check("难度选择器含三档", cd._difficulty.count() == 3)
    _settings_bak = settings_mod.load_settings()
    cd._difficulty.setCurrentText("休闲")
    check("难度切换应用到当前对局", cd._game.difficulty == "休闲")
    cd.new_game()
    check("再来一局保留难度选择", cd._game.difficulty == "休闲")
    settings_mod.save_settings(_settings_bak)
    cd._game.player_pairs = 3
    cd.new_game()
    check("再来一局重置计分", cd._game.player_pairs == 0
          and cd._game.ai_pairs == 0 and cd._game.winner is None)

    # 回归测试（issue：翻开两张后无法继续点击）
    from core.concentration import (_AI_STEP_MS, _FLIP_BACK_MS, _PAIR_DONE_MS)
    by_rank2 = {}
    for i2, (rank2, _) in enumerate(cd._game.board):
        by_rank2.setdefault(rank2, []).append(i2)
    a2, b2 = next(v for v in by_rank2.values() if len(v) == 2)
    cd._on_click(a2)
    cd._on_click(b2)
    check("配对后进入动画锁定", cd._lock)
    QTest.qWait(_PAIR_DONE_MS + 150)
    check("配对动画结束后可继续点击",
          not cd._lock and any(btn.isEnabled() for btn in cd._btns))
    # 玖玖里回合：第二张牌应正常翻开
    cd._game.turn = "ai"
    cd._start_ai_turn()
    QTest.qWait(_AI_STEP_MS + 150)
    i2, j2 = cd._ai_pending
    check("玖玖里第二张牌正常翻开", cd._game.revealed[j2] is True)
    QTest.qWait(_FLIP_BACK_MS + 150)   # 若 miss 等待翻回动画收尾
    cd.close()

    # ---- 设置持久化与 API 地址解析 ----
    print("== 设置与 API ==")
    tmp = os.path.join(tempfile.gettempdir(), "pet_settings_test.json")
    settings_mod.save_settings({"k": 1}, path=tmp)
    check("settings 读写", settings_mod.load_settings(path=tmp) == {"k": 1})
    os.remove(tmp)
    client = ApiClient()
    check("API 端点解析(裸域名)",
          client._resolve_endpoint("https://api.deepseek.com")
          == ["https://api.deepseek.com/chat/completions",
              "https://api.deepseek.com/v1/chat/completions"])
    check("API 端点解析(带/v1)",
          client._resolve_endpoint("https://api.openai.com/v1")
          == ["https://api.openai.com/v1/chat/completions"])
    check("API 端点解析(完整路径)",
          client._resolve_endpoint("https://x.com/v1/chat/completions")
          == ["https://x.com/v1/chat/completions"])

    print("SELFTEST RESULT:", "FAIL: " + ", ".join(fails) if fails else "ALL PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
