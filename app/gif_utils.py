"""GIF 保存工具：强制全画布帧（角落点技巧，v2）。

设备的 GIF 解码器不处理差分帧（PIL 默认只编码变化区域），会导致
灰色残块 / 播放卡顿。

v1 教训：给全图像素 +1 通道偏移会让 255 值的白色绕回 0——白色 logo
在暗背景上每 4 帧轮变色（用户看到"logo 一闪一闪"）。
v2 做法：奇偶帧在左上/右下角各画一个 1 像素微亮点，相邻两帧的差异
包围盒恒为全画布，逼 PIL 写整帧；画面内容本身零改动。
"""
from pathlib import Path

from PIL import Image, ImageDraw


def save_gif_fullframes(frames: list, path: Path, duration_ms: int) -> None:
    forced = []
    for k, frame in enumerate(frames):
        img = frame.convert('RGB')
        d = ImageDraw.Draw(img)
        if k % 2 == 0:
            d.point((0, 0), fill=(3, 3, 4))
        else:
            d.point((img.width - 1, img.height - 1), fill=(3, 3, 4))
        forced.append(img)
    forced[0].save(path, save_all=True, append_images=forced[1:],
                   duration=duration_ms, loop=0, optimize=False)

    check = Image.open(path)
    for i in range(check.n_frames):
        check.seek(i)
        if check.dispose_extent != (0, 0, check.width, check.height):
            raise RuntimeError(f'{path.name} 第 {i} 帧仍是差分帧 {check.dispose_extent}')
    print(f'{path.name}: {check.n_frames} 帧 @ {duration_ms}ms（全画布帧校验通过）')
