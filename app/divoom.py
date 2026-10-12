"""Times Gate 设备客户端（自 timeGate tg.py 移植，实测陷阱注释原样保留）。

协议：单台设备，POST http://<IP>:9000/divoom_api，JSON body；
五块屏用 LcdArray（如 [1,0,0,0,0]）或 LcdIndex（0~4）指定。

硬约束：所有写操作经过 _device_lock 串行——多屏交错逐帧推送会损坏设备
播放器状态（实测唯一解法 SysReboot）。这不是优化，是保命。
"""
import base64
import io
import logging
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

from .render import (SCREEN_SIZE, banner_strips, extract_frames, parse_hex_color,
                     render_text_frame)

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
CONTENT = ROOT / 'content'  # push-all 素材 / quota 预览图的目录


def load_env() -> dict:
    env = {}
    env_file = ROOT / '.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                env[key.strip()] = value.strip()
    return env


ENV = load_env()
DEVICE_IP = ENV.get('DEVICE_IP', '192.168.3.96')
API = f'http://{DEVICE_IP}:9000/divoom_api'
DEVICE_ID = int(ENV.get('DEVICE_ID', '0') or '0')


class DeviceError(RuntimeError):
    """设备拒绝了命令（非零返回码）。"""


_device_lock = threading.RLock()  # 可重入：push_gif 内部调 push_frames，两层都拿同一把锁
_pic_id = None


def next_pic_id() -> int:
    # 官方要求 PicID 唯一且递增。注意必须保证同一进程内多次调用互不相同
    # （教训：按时间戳取整会在同一时间片里产生重复 ID，导致设备疯狂 Loading）
    global _pic_id
    _pic_id = (_pic_id or int(time.time())) + 1
    return _pic_id


def api_call(payload: dict) -> dict:
    r = requests.post(API, json=payload, timeout=10)
    data = r.json()
    if data.get('ReturnCode') != 0:
        raise DeviceError(f'设备拒绝命令 {payload.get("Command")}: {data.get("ReturnMessage")}')
    return data


def parse_lcd_array(spec: str) -> list:
    if spec.lower() == 'all':
        return [1, 1, 1, 1, 1]
    chosen = {int(x) for x in spec.split(',')}
    return [1 if i in chosen else 0 for i in range(5)]


def lcd_array_for(lcd_index: int) -> list:
    return [1 if i == lcd_index else 0 for i in range(5)]


def screens_of(lcd_array: list) -> list:
    return [i for i, v in enumerate(lcd_array) if v]


def push_frames(frames: list, lcd_array: list, speed_ms: int = 900) -> int:
    """把若干张（PIL）图片作为多帧动画推到指定屏幕。返回帧数。"""
    payload_frames = []
    for frame in frames:
        buf = io.BytesIO()
        frame.save(buf, format='JPEG', quality=95)
        payload_frames.append(base64.b64encode(buf.getvalue()).decode())
    pic_id = next_pic_id()
    with _device_lock:
        for offset, pic_data in enumerate(payload_frames):
            api_call({
                'Command': 'Draw/SendHttpGif',
                'LcdArray': lcd_array,
                'PicNum': len(payload_frames),
                'PicWidth': SCREEN_SIZE,
                'PicOffset': offset,
                'PicID': pic_id,
                'PicSpeed': speed_ms,
                'PicData': pic_data,
            })
    return len(payload_frames)


def push_gif(img: 'Image', lcd_array: list, speed_ms: int = 120) -> dict:
    """把 GIF（或静态图片，任意图自动缩放）逐帧推到指定屏幕。"""
    frames = extract_frames(img)
    n = push_frames(frames, lcd_array, speed_ms=speed_ms)
    log.info('已推 %d 帧 @%dms -> 屏幕 %s', n, speed_ms, screens_of(lcd_array))
    return {'screens': screens_of(lcd_array), 'frames': n, 'speed_ms': speed_ms}


def push_image(img: 'Image', lcd_array: list) -> dict:
    """推单张图片（动画输入取首帧）。"""
    n = push_frames(extract_frames(img)[:1], lcd_array, speed_ms=900)
    return {'screens': screens_of(lcd_array), 'frames': n, 'speed_ms': 900}


def push_text(lines: list, lcd_index: int, color: str = '#00FF66', bg: str = '#080820') -> dict:
    """文字 -> 服务端 PIL 渲染成图片 -> 推到指定屏。

    为什么不走 Draw/SendHttpText：通道本身可用（2026-09-18 重测出字，早先
    "固件失效"是误判），但字体由设备从云端拉取，滚动重绘会间歇触发
    "Loading+沙漏"，实测还把播放器搞成三态轮闪、清文字也回不去，
    SysReboot 才恢复。服务端渲染零云端依赖，是稳定性选择。
    """
    frame = render_text_frame(lines, color=parse_hex_color(color), bg=parse_hex_color(bg))
    n = push_frames([frame], lcd_array_for(lcd_index), speed_ms=900)
    log.info('已推文字画面 -> 屏幕 %d: %s', lcd_index, ' | '.join(lines))
    return {'screens': [lcd_index], 'frames': n, 'lines': lines}


def clear_text(lcd_index: int) -> dict:
    """清掉指定屏上 Draw/SendHttpText 叠的文字（清历史叠字用）。"""
    with _device_lock:
        api_call({'Command': 'Draw/ClearHttpText', 'LcdId': lcd_index, 'TextId': -1})
    return {'screens': [lcd_index]}


def set_dial(lcd_index: int, clock_id: int, lcd_independence: int = 0) -> dict:
    """把某块屏切回官方表盘。"""
    with _device_lock:
        api_call({
            'Command': 'Channel/SetClockSelectId',
            'ClockId': clock_id,
            'LcdIndex': lcd_index,
            'LcdIndependence': lcd_independence,
        })
    return {'screens': [lcd_index], 'clock_id': clock_id}


def push_banner(img: 'Image', screens: list, speed_ms: int = 100) -> dict:
    """横幅模式：宽幅 GIF 缩放到 len(screens)*128 宽、居中裁 128 高、竖切条数=屏数，
    从左到右对应 screens 列表，拼成一幅跨屏画面。"""
    strips = banner_strips(img, len(screens))
    for strip_index, frames in enumerate(strips):
        push_frames(frames, lcd_array_for(screens[strip_index]), speed_ms=speed_ms)
    log.info('已推横幅 -> 屏幕 %s（%d 帧每条）', screens, len(strips[0]))
    return {'screens': screens, 'frames': len(strips[0]), 'speed_ms': speed_ms}


def fetch_quota() -> tuple | None:
    """查询 GLM Coding Plan 额度，返回 (5 小时窗口剩余 %, 月度剩余 %)。

    端点来自官方插件 zai-coding-plugins 的 query-usage.mjs：
    GET <base>/api/monitor/usage/quota/limit，Authorization 直接放 token。
    返回的 percentage 是"已用"百分比，这里换算成剩余。
    """
    base = ENV.get('ANTHROPIC_BASE_URL', 'https://open.bigmodel.cn').rstrip('/')
    parsed = urlparse(base)
    base = f'{parsed.scheme}://{parsed.netloc}'  # 只取协议+域名，路径丢弃（与官方插件一致）
    token = ENV.get('ANTHROPIC_AUTH_TOKEN', '')
    if not token:
        return None
    r = requests.get(
        f'{base}/api/monitor/usage/quota/limit',
        headers={'Authorization': token},
        timeout=10,
    )
    limits = r.json().get('data', {}).get('limits', [])
    used = {}
    for item in limits:
        if item.get('type') == 'TOKENS_LIMIT':
            used['5h'] = item.get('percentage')
        elif item.get('type') == 'TIME_LIMIT':
            used['month'] = item.get('percentage')
    rem_5h = None if used.get('5h') is None else 100 - used['5h']
    rem_month = None if used.get('month') is None else 100 - used['month']
    return rem_5h, rem_month


def quota(lcd_index: int = 4) -> dict:
    """把 GLM 额度画面推到指定屏，返回抓到的数值。"""
    result = fetch_quota()
    rem_5h = rem_month = None
    if result is None:
        lines = ['GLM', 'no token']
    else:
        rem_5h, rem_month = result
        lines = ['GLM']
        if rem_5h is not None:
            lines.append(f'5H {rem_5h}%')
        if rem_month is not None:
            lines.append(f'MO {rem_month}%')
    frame = render_text_frame(lines)
    CONTENT.mkdir(parents=True, exist_ok=True)
    frame.save(CONTENT / 'quota_preview.png')  # 本地预览
    push_frames([frame], lcd_array_for(lcd_index), speed_ms=900)
    log.info('已推额度画面 -> 屏幕 %d: %s', lcd_index, ' | '.join(lines))
    return {'screens': [lcd_index], 'lines': lines,
            'remaining_5h_percent': rem_5h, 'remaining_month_percent': rem_month,
            'placeholder': result is None}


def push_all() -> dict:
    """content/ 目录约定（详见 content/README.md）：
    screen1_art.gif        -> 第 1 块屏（个人艺术）
    noldus_left/mid/right  -> 第 2/3/4 块屏（公司三联，存在时优先）
    side_effect/logo.gif   -> 两侧备用（仅 noldus 三联缺失时启用）
    最后刷新第 5 块额度屏。
    """
    plan = [('screen1_art.gif', parse_lcd_array('0'))]
    if all((CONTENT / f'noldus_{p}.gif').exists() for p in ('left', 'mid', 'right')):
        plan += [(f'noldus_{p}.gif', parse_lcd_array(str(i)))
                 for i, p in enumerate(('left', 'mid', 'right'), start=1)]
    else:
        plan += [('side_effect.gif', parse_lcd_array('1,3')),
                 ('logo.gif', parse_lcd_array('2'))]
    pushed, skipped = [], []
    for filename, lcd_array in plan:
        path = CONTENT / filename
        if not path.exists():
            skipped.append(filename)
            log.warning('跳过缺失的 %s', filename)
            continue
        with _device_lock:
            push_gif(Image.open(path), lcd_array)
        pushed.append({'file': filename, 'screens': screens_of(lcd_array)})
        time.sleep(2)  # 温和推送：动画之间留间隔，避免压垮固件
    return {'pushed': pushed, 'skipped': skipped, 'quota': quota(4)}  # 约定：第 5 块屏显示额度


def cloud_info() -> dict:
    """云端查五屏完整配置（Get5LcdInfoV2）。"""
    if not DEVICE_ID:
        raise RuntimeError('未配置 DEVICE_ID（.env）：向设备发任意一条 LAN 命令，'
                           '响应 JSON 里自带 DeviceId 字段，填进 .env 重启服务即可')
    r = requests.post(
        'https://app.divoom-gz.com/Channel/Get5LcdInfoV2',
        json={'DeviceId': DEVICE_ID, 'DeviceType': 'LCD'},
        timeout=10,
    )
    return r.json()


def device_health() -> dict:
    """设备在线检查（只读命令 Device/GetDeviceTime，3 秒超时）。

    不复用 api_call 的返回码检查：这条命令的响应包是 error_code/UTCTime
    结构（官方文档示例），ReturnCode 字段未必存在。
    """
    try:
        r = requests.post(API, json={'Command': 'Device/GetDeviceTime'}, timeout=3)
    except requests.RequestException as e:
        return {'online': False, 'ip': DEVICE_IP, 'error': f'{e.__class__.__name__}: {e}',
                'hint': '设备换网后 IP 会变：路由器后台查新 IP，更新 .env 的 DEVICE_IP 后重启服务'}
    if r.status_code != 200:
        return {'online': False, 'ip': DEVICE_IP, 'error': f'HTTP {r.status_code}'}
    return {'online': True, 'ip': DEVICE_IP, 'device_time': r.json()}
