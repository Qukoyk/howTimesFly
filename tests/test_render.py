import io

from PIL import Image

from app.render import (SCREEN_SIZE, MAX_FRAMES, banner_strips, extract_frames,
                        parse_hex_color, render_text_frame)


def _gif(frames_n: int, size=(32, 32)) -> Image:
    imgs = [Image.new('RGB', size, (i * 20 % 256, 100, 150)) for i in range(frames_n)]
    buf = io.BytesIO()
    imgs[0].save(buf, format='GIF', save_all=True, append_images=imgs[1:],
                 duration=100, loop=0)
    buf.seek(0)
    return Image.open(buf)


def test_render_text_frame_size_and_content():
    img = render_text_frame(['GLM', '5H 87%'])
    assert img.size == (SCREEN_SIZE, SCREEN_SIZE)
    assert img.getpixel((2, 2)) == (8, 8, 20)  # 角落是背景色
    sampled = {img.getpixel((x, y)) for y in range(0, SCREEN_SIZE, 4)
               for x in range(0, SCREEN_SIZE, 4)}
    assert (0, 255, 102) in sampled  # 文字色出现


def test_render_text_frame_empty_lines_guard():
    img = render_text_frame([])
    assert img.size == (SCREEN_SIZE, SCREEN_SIZE)


def test_parse_hex_color():
    assert parse_hex_color('#00FF66') == (0, 255, 102)
    assert parse_hex_color('080820') == (8, 8, 32)
    for bad in ('#12345', 'zzzzzz', ''):
        try:
            parse_hex_color(bad)
            raise AssertionError(f'{bad!r} 应该被拒绝')
        except ValueError:
            pass


def test_extract_frames_resizes_to_screen():
    frames = extract_frames(_gif(3, size=(64, 64)))
    assert len(frames) == 3
    assert all(f.size == (SCREEN_SIZE, SCREEN_SIZE) for f in frames)


def test_extract_frames_caps_at_60():
    assert len(extract_frames(_gif(70))) == MAX_FRAMES


def test_extract_frames_static_image():
    frames = extract_frames(Image.new('RGB', (300, 200), 'red'))
    assert len(frames) == 1
    assert frames[0].size == (SCREEN_SIZE, SCREEN_SIZE)


def test_banner_strips_makes_three_strips():
    strips = banner_strips(_gif(2, size=(384, 200)))
    assert len(strips) == 3
    assert all(len(s) == 2 for s in strips)
    assert all(f.size == (SCREEN_SIZE, SCREEN_SIZE) for s in strips for f in s)


def test_banner_strips_strip_count_param():
    strips = banner_strips(_gif(1, size=(256, 200)), 2)  # 跨两屏
    assert len(strips) == 2
    assert all(f.size == (SCREEN_SIZE, SCREEN_SIZE) for s in strips for f in s)


def test_banner_strips_too_flat_rejected():
    try:
        banner_strips(Image.new('RGB', (300, 50), 'blue'))  # 缩到 384 宽后仅 64px 高，裁不出 128
        raise AssertionError('太扁的图应该被拒绝')
    except ValueError:
        pass
