"""服务端画面渲染与帧提取（自 timeGate tg.py 移植）。

设备只认 128x128 的 JPEG 帧流。这里负责两件事：
把任意图缩放成可用帧；把文字画成图片——设备端文字渲染（SendHttpText）
自 2026-09-05 固件起静默失效，所有文字一律电脑端画好再推。
"""
from PIL import Image, ImageDraw, ImageFont, ImageSequence

SCREEN_SIZE = 128  # 每块屏原生分辨率（实测：16/32/64 的图会被放大铺满）
MAX_FRAMES = 60  # 设备单次动画上限


def render_text_frame(lines: list, color=(0, 255, 102), bg=(8, 8, 20)) -> 'Image':
    """把几行文字渲染成 128x128 图片，矢量字体自动缩放到刚好装下。"""
    if not lines:
        lines = ['']
    img = Image.new('RGB', (SCREEN_SIZE, SCREEN_SIZE), bg)
    draw = ImageDraw.Draw(img)
    line_h = SCREEN_SIZE // len(lines)
    font = ImageFont.load_default(9)  # 行数极多时下面的循环可能一次都不进，先兜底
    for size in range(int(line_h * 1.4), 9, -2):
        font = ImageFont.load_default(size)
        if all(draw.textbbox((0, 0), line, font=font)[2] <= SCREEN_SIZE - 8 for line in lines):
            break
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((SCREEN_SIZE - w) // 2, i * line_h + (line_h - h) // 2 - bbox[1]),
                  line, fill=color, font=font)
    return img


def parse_hex_color(s: str) -> tuple:
    """'#RRGGBB' 或 'RRGGBB' -> (r, g, b)，格式不对抛 ValueError。"""
    s = s.strip().lstrip('#')
    if len(s) != 6:
        raise ValueError(f'颜色格式应为 #RRGGBB，收到: {s!r}')
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        raise ValueError(f'颜色格式应为 #RRGGBB，收到: {s!r}')


def extract_frames(img: 'Image') -> list:
    """把 GIF/图片变成 <=60 张 128x128 RGB 帧队列。

    16/32/64 的像素画用最近邻放大（保持硬朗的像素块），其他用平滑缩放。
    """
    frames = []
    for frame in ImageSequence.Iterator(img):
        rgb = frame.convert('RGB')
        if rgb.size != (SCREEN_SIZE, SCREEN_SIZE):
            resample = Image.NEAREST if rgb.size[0] in (16, 32, 64) else Image.LANCZOS
            rgb = rgb.resize((SCREEN_SIZE, SCREEN_SIZE), resample)
        frames.append(rgb)
        if len(frames) == MAX_FRAMES:
            break
    return frames


def banner_strips(img: 'Image', strips_n: int = 3) -> list:
    """宽幅图 -> strips_n 条帧序列（每条 128x128，横跨指定屏幕拼一幅画）。

    缩放到 strips_n*128 宽、居中裁出 128 高，再竖切 strips_n 份。
    """
    w_total = strips_n * SCREEN_SIZE
    h_scaled = round(img.height * w_total / img.width)
    if h_scaled < SCREEN_SIZE:
        raise ValueError(f'图片太扁（宽高比 {img.width / img.height:.1f}:1）：'
                         f'横幅要求缩放到 {w_total}px 宽后至少有 128px 高可裁，当前只有 {h_scaled}px')
    frames = []
    for f in ImageSequence.Iterator(img):
        rgb = f.convert('RGB').resize((w_total, h_scaled), Image.LANCZOS)
        top = (h_scaled - SCREEN_SIZE) // 2
        frames.append(rgb.crop((0, top, w_total, top + SCREEN_SIZE)))
    frames = frames[:MAX_FRAMES]
    return [
        [fr.crop((strip * SCREEN_SIZE, 0, (strip + 1) * SCREEN_SIZE, SCREEN_SIZE))
         for fr in frames]
        for strip in range(strips_n)
    ]
