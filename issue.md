## 聊天框问题：

issue：用户反馈点击对话后对话框出现的过于突兀；

解决方案：点击对话后不直接出现对话框而是桌宠附近出现一个聊天框，显示文字：“聊天？正好没什么事，随便聊聊吧”

之后在桌宠下方出现聊天框用于用户输入，聊天框的素材位于

"resource/其他/聊天框.png"

（已解决）

## 桌宠突兀问题：

目前的桌宠呈现明显的方形

解决方案：

### 底部与边缘“动态羽化遮罩”（解决半身像刀切截断感）

仔细观察你之前提取的玖玖里素材（如 `kukuri_kao_13.png`），她的身体在胸部以下、以及右侧飘起的双马尾发梢处是被画布边缘直接切掉的。如果直接悬空放在桌面上，这个平直的底边就会显得非常突兀。

你可以通过 PyQt 的 `QPainter` 在预加载图片时，**用代码自动为所有图片的底部（和边缘）加上一层渐隐透明过渡（Alpha Gradient Mask）**，让她的身体下半部分自然地“融化”在桌面背景里，像幽灵或全息投影一样柔和：

Python

```
from PyQt5.QtGui import QPixmap, QPainter, QLinearGradient, QColor
from PyQt5.QtCore import Qt, QPointF

def apply_bottom_fade(pixmap, fade_ratio=0.25):
    """    为半身像底部添加渐隐透明效果，消除刀切方形边缘    fade_ratio: 底部渐变区域占总高度的比例 (0.25 表示底部 25% 开始渐隐)    """
    if pixmap.isNull():
        return pixmap

    # 创建一个带透明通道的画布副本
    result = QPixmap(pixmap.size())
    result.fill(Qt.transparent)

    painter = QPainter(result)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    # 1. 先画原图
    painter.drawPixmap(0, 0, pixmap)

    # 2. 设置混合模式为 DestinationIn（保留原图RGB，但乘以渐变遮罩的Alpha值）
    painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)

    # 3. 创建从上到下的线性渐变（上方完全不透明，底部边缘完全透明）
    height = pixmap.height()
    fade_start_y = height * (1.0 - fade_ratio)

    gradient = QLinearGradient(QPointF(0, fade_start_y), QPointF(0, height))
    gradient.setColorAt(0.0, QColor(0, 0, 0, 255)) # 渐变起点：保持原样
    gradient.setColorAt(1.0, QColor(0, 0, 0, 0))   # 画布底边：完全透明

    # 4. 在底部区域绘制渐变遮罩
    painter.fillRect(0, int(fade_start_y), pixmap.width(), int(height - fade_start_y), gradient)
    painter.end()

    return result
```

*使用方法：在你的 `load_animations_by_keyword` 函数中，将 `QPixmap(full_path)` 替换为 `apply_bottom_fade(QPixmap(full_path))` 即可一键处理所有差分图*

（已解决）

## 对话和png不对应问题：

 目前的每个json的相应语句中都有对应的情绪词，大部分的情况下都是由于png发生变化角色的对话变化；但是例如，拖拽时产生的对话就是先出现对话，但是并后续没有根据情绪词更改图片；

解决方案为这些动作直接触发的对话增加判断，在当前数字文件目录下找到对应的表情png，如果没有去所在的服装文件夹中找，如果所在服装文件夹也没有则直接结束

（已解决）

## 桌宠的位置设计：

### 1.右键新增功能：隐藏；

点击之后，桌宠应该消失在桌面但是可以借助win：显示隐藏的图表中找到并再次显示在桌面；

### 2.新增功能2：活跃模式；

开启之后，每10min桌宠未接收到任何指令会出现在桌面随机位置，并按照json切换状态，并显示对话框：

```json
{
  "idle_shift_surprise": [
    {
      "text": "……哼，看你盯着屏幕那么入迷，连我在旁边都注意不到吗？别误会，我只是自己随便散步过来的。",
      "emotion_state": "worry"
    },
    {
      "text": "好歹也分一点注意力给我啊。一直把我晾在角落里，信不信我真的从桌面上跳下去？",
      "emotion_state": "sad"
    },
    {
      "text": "……怎么突然把我移到这里？你该不会是在搞什么恶趣味的实验吧？",
      "emotion_state": "worry"
    },
    {
      "text": "喂。虽然这里风景不错……但你一直不理人，是不是觉得我很碍事？",
      "emotion_state": "sad"
    },
    {
      "text": "无聊死了……人类的专注力原来能持续这么久吗？真佩服你啊。",
      "emotion_state": "meditation"
    },
    {
      "text": "……咳，既然你这么专心，那我就勉强在这里监督你好了。不许偷懒哦。",
      "emotion_state": "smile"
    }
  ]
}
```

如果未开启活跃模式则在10min无动作后隐藏；

（已解决）

## 抽鬼牌素材：

卡牌素材在"resource/其他/扑克牌/png"下，优化抽鬼牌游戏

（已解决）



## 抽鬼牌优化：

现在优化抽鬼牌游戏，在我抽取玖玖里的卡牌时，检测我的鼠标停留的位置，每张牌都可能会出现json语言用于和user交互；为我编写json台词，注意移动到鬼牌时的台词会发生微弱变化；

注意要跟随json语言的表情来更换png，逻辑和对话和png不对应问题中一样；



# 
