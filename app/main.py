"""howTimesFly API —— Times Gate 推送服务器（FastAPI + Swagger UI）。

启动：uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
文档：http://127.0.0.1:8000/docs
"""
import io
import logging

import requests
from fastapi import FastAPI, File, Form, HTTPException, Path as PathParam, Query, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from . import divoom
from .divoom import DeviceError

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

app = FastAPI(
    title='howTimesFly API',
    version='0.1.0',
    description=(
        '往 Divoom Times Gate（单台、五块 128×128 屏）推内容的局域网 API。'
        '屏幕编号 0-4，从左到右。\n\n'
        '已知固件边界（实测）：单次动画最多 60 帧；服务内部对设备写操作强制串行'
        '（多屏交错推送会损坏播放器状态）；设备端文字渲染已失效，`/text` 由服务端'
        '渲染成图片推送。协议文档镜像见仓库 docs/。'
    ),
)


def _open_image(file: UploadFile) -> Image.Image:
    data = file.file.read()
    try:
        return Image.open(io.BytesIO(data))
    except UnidentifiedImageError:
        raise HTTPException(400, f'{file.filename!r} 不是有效的图片/GIF 文件')


def _call_device(fn, *args, **kwargs):
    """统一把设备/网络错误翻译成 502 人话。"""
    try:
        return fn(*args, **kwargs)
    except DeviceError as e:
        raise HTTPException(502, str(e))
    except requests.RequestException:
        raise HTTPException(
            502,
            f'设备不在线：连不上 {divoom.DEVICE_IP}:9000。设备换网后 IP 会变——'
            f'路由器后台查新 IP，更新 .env 的 DEVICE_IP 后重启服务（可先看 GET /health）')


class TextBody(BaseModel):
    text: str = Field(min_length=1, max_length=512, description='要显示的文字；换行用 \\n')
    text_color: str = Field('#00FF66', description='文字颜色 #RRGGBB')
    bg_color: str = Field('#080820', description='背景颜色 #RRGGBB')


def _parse_screens(s: str) -> list:
    """'1,2,3' -> [1, 2, 3]，并校验：2-5 个互不重复的 0-4 编号。"""
    try:
        screens = [int(x) for x in s.split(',')]
    except ValueError:
        raise HTTPException(400, f'屏幕参数应为逗号分隔的编号（如 1,2,3），收到: {s!r}')
    if (not 2 <= len(screens) <= 5
            or len(set(screens)) != len(screens)
            or any(not 0 <= i <= 4 for i in screens)):
        raise HTTPException(400, '屏幕参数应为 2-5 个互不重复的编号（0-4），从左到右排列，如 1,2,3')
    return screens


class DialBody(BaseModel):
    clock_id: int = Field(ge=0, description='官方表盘 ClockId（整机模式可用 GET /screens 查，'
                                           '或官方 App 里看；例如 57、581）')
    lcd_independence: int = Field(0, description='0 跟随整机模式，1 独立屏')


@app.post('/screens/{lcd_index}/gif', summary='推 GIF/动画到一块屏')
def push_gif_endpoint(
    lcd_index: int = PathParam(ge=0, le=4, description='屏幕编号 0-4，从左到右'),
    file: UploadFile = File(description='GIF 或静态图片；16/32/64 像素画自动最近邻放大，其余平滑缩放'),
    speed_ms: int = Form(120, ge=30, le=3000, description='帧间隔（毫秒）'),
):
    img = _open_image(file)
    return _call_device(divoom.push_gif, img, divoom.lcd_array_for(lcd_index), speed_ms)


@app.post('/screens/{lcd_index}/image', summary='推单张图片到一块屏（动画输入取首帧）')
def push_image_endpoint(
    lcd_index: int = PathParam(ge=0, le=4, description='屏幕编号 0-4，从左到右'),
    file: UploadFile = File(description='任意格式静态图片'),
):
    img = _open_image(file)
    return _call_device(divoom.push_image, img, divoom.lcd_array_for(lcd_index))


@app.post('/screens/{lcd_index}/text', summary='推文字到一块屏（服务端渲染成图片）')
def push_text_endpoint(
    body: TextBody,
    lcd_index: int = PathParam(ge=0, le=4, description='屏幕编号 0-4，从左到右'),
):
    try:
        return _call_device(divoom.push_text, body.text.split('\n'), lcd_index,
                            body.text_color, body.bg_color)
    except ValueError as e:  # parse_hex_color：颜色格式不对
        raise HTTPException(400, str(e))


@app.post('/screens/{lcd_index}/clear-text', summary='清除一块屏上叠的文字')
def clear_text_endpoint(lcd_index: int = PathParam(ge=0, le=4, description='屏幕编号 0-4')):
    return _call_device(divoom.clear_text, lcd_index)


@app.post('/screens/{lcd_index}/dial', summary='把一块屏切回官方表盘')
def set_dial_endpoint(
    body: DialBody,
    lcd_index: int = PathParam(ge=0, le=4, description='屏幕编号 0-4'),
):
    return _call_device(divoom.set_dial, lcd_index, body.clock_id, body.lcd_independence)


@app.post('/banner', summary='推宽幅图：裁条横跨多块屏拼一幅画')
def push_banner_endpoint(
    file: UploadFile = File(description='宽幅 GIF/图片，宽高比需大于「屏数:1」才够裁'),
    screens: str = Form('1,2,3', description='横幅跨的屏幕编号，从左到右逗号分隔，条数=屏数（2-5 块）'),
    speed_ms: int = Form(100, ge=30, le=3000, description='帧间隔（毫秒）'),
):
    img = _open_image(file)
    target = _parse_screens(screens)
    try:
        return _call_device(divoom.push_banner, img, target, speed_ms)
    except ValueError as e:  # banner_strips：图片太扁
        raise HTTPException(400, str(e))


@app.post('/push-all', summary='按 content/ 目录约定一键推全部五块屏（约 10 秒，屏间留间隔）')
def push_all_endpoint():
    return _call_device(divoom.push_all)


@app.post('/quota', summary='刷新 GLM Coding Plan 额度显示')
def quota_endpoint(
    lcd_index: int = Query(4, ge=0, le=4, description='额度显示到哪块屏（默认第 5 块）'),
):
    return _call_device(divoom.quota, lcd_index)


@app.get('/screens', summary='云端查五块屏完整配置（Get5LcdInfoV2）')
def screens_endpoint():
    try:
        return divoom.cloud_info()
    except RuntimeError as e:  # DEVICE_ID 未配置
        raise HTTPException(502, str(e))
    except requests.RequestException:
        raise HTTPException(502, 'Divoom 云端 API（app.divoom-gz.com）不可达')


@app.get('/health', summary='设备在线检查（只读，不动屏幕）')
def health_endpoint():
    return divoom.device_health()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
