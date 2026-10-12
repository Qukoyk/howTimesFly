from PIL import Image

from app import divoom
from app.render import render_text_frame


def _capture(monkeypatch):
    sent = []
    monkeypatch.setattr(divoom, 'api_call',
                        lambda payload: (sent.append(payload), {'ReturnCode': 0})[1])
    return sent


def test_push_frames_payload(monkeypatch):
    sent = _capture(monkeypatch)
    frames = [render_text_frame(['A']), render_text_frame(['B'])]
    n = divoom.push_frames(frames, [1, 0, 0, 0, 0], speed_ms=500)
    assert n == 2
    assert len(sent) == 2
    assert all(p['Command'] == 'Draw/SendHttpGif' for p in sent)
    assert [p['PicOffset'] for p in sent] == [0, 1]
    assert sent[0]['PicNum'] == 2
    assert sent[0]['PicID'] == sent[1]['PicID']  # 同一次推送共用 PicID
    assert sent[0]['LcdArray'] == [1, 0, 0, 0, 0]
    assert sent[0]['PicSpeed'] == 500


def test_next_pic_id_increments():
    assert divoom.next_pic_id() < divoom.next_pic_id()


def test_clear_text_payload(monkeypatch):
    sent = _capture(monkeypatch)
    divoom.clear_text(3)
    assert sent == [{'Command': 'Draw/ClearHttpText', 'LcdId': 3, 'TextId': -1}]


def test_set_dial_payload(monkeypatch):
    sent = _capture(monkeypatch)
    divoom.set_dial(4, 57)
    assert sent[0]['Command'] == 'Channel/SetClockSelectId'
    assert sent[0]['ClockId'] == 57
    assert sent[0]['LcdIndex'] == 4


def test_push_gif_targets_requested_screen(monkeypatch):
    sent = _capture(monkeypatch)
    result = divoom.push_gif(Image.new('RGB', (64, 64), 'red'),
                             divoom.lcd_array_for(2), speed_ms=120)
    assert len(sent) == 1
    assert sent[0]['LcdArray'] == [0, 0, 1, 0, 0]
    assert result == {'screens': [2], 'frames': 1, 'speed_ms': 120}


def test_push_text_is_server_rendered(monkeypatch):
    sent = _capture(monkeypatch)
    divoom.push_text(['GLM', '5H 87%'], 4)
    # 不走 Draw/SendHttpText（设备端文字渲染已失效），走图片通道
    assert len(sent) == 1
    assert sent[0]['Command'] == 'Draw/SendHttpGif'
    assert sent[0]['LcdArray'] == [0, 0, 0, 0, 1]


def test_push_text_rejects_bad_color(monkeypatch):
    _capture(monkeypatch)
    try:
        divoom.push_text(['hi'], 0, color='nope')
        raise AssertionError('非法颜色应该被拒绝')
    except ValueError:
        pass


def test_push_banner_targets_requested_screens(monkeypatch):
    sent = _capture(monkeypatch)
    result = divoom.push_banner(Image.new('RGB', (256, 200), 'red'), [0, 4])
    assert len(sent) == 2  # 两屏两条，各一帧
    assert sent[0]['LcdArray'] == [1, 0, 0, 0, 0]
    assert sent[1]['LcdArray'] == [0, 0, 0, 0, 1]
    assert result['screens'] == [0, 4]


def test_quota_targets_requested_screen(monkeypatch, tmp_path):
    sent = _capture(monkeypatch)
    monkeypatch.setattr(divoom, 'fetch_quota', lambda: (87, 65))
    monkeypatch.setattr(divoom, 'CONTENT', tmp_path)  # 预览图写临时目录
    result = divoom.quota(2)
    assert sent[0]['LcdArray'] == [0, 0, 1, 0, 0]
    assert result['screens'] == [2]
    assert result['remaining_5h_percent'] == 87
    assert result['remaining_month_percent'] == 65
