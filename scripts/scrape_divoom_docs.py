"""从 Divoom 官方 ShowDoc（docin.divoom-gz.com「第三方接口文档」）抓取 Times Gate 相关页面。

用法：python scripts/scrape_divoom_docs.py
官方文档首页：http://docin.divoom-gz.com/web/#/5
旧地址 doc.divoom-gz.com 已迁移废弃（仅剩 developer@divoom.com 联系页）。
"""

import html
import json
import re
import time
import urllib.request
from pathlib import Path

API = 'https://docin.divoom-gz.com/server/index.php?s=/api/page/info'
DOCS_DIR = Path(__file__).parent.parent / 'docs'

# (page_id, 输出文件名, 所属章节)
PAGES = [
    # 通用（TimeGate 也依赖）
    (24, '00-common/command-format', '通用'),
    (25, '00-common/find-device', '通用'),
    (145, '00-common/diy-net-data-clock', '通用'),
    (135, '00-common/command-list-batch', '通用'),
    (136, '00-common/url-command-file', '通用'),
    # TimeGate > 系统
    (140, '01-system/reboot', '系统'),
    (102, '01-system/set-brightness', '系统'),
    (103, '01-system/get-all-setting', '系统'),
    (104, '01-system/weather-area-setting', '系统'),
    (105, '01-system/set-time-zone', '系统'),
    (106, '01-system/system-time', '系统'),
    (107, '01-system/screen-switch', '系统'),
    (108, '01-system/get-device-time', '系统'),
    (109, '01-system/set-temperature-mode', '系统'),
    (110, '01-system/set-mirror-mode', '系统'),
    (111, '01-system/set-hour-mode', '系统'),
    (112, '01-system/get-weather', '系统'),
    (138, '01-system/set-gallery-time', '系统'),
    (353, '01-system/set-rgb-information', '系统'),
    # TimeGate > 表盘/频道
    (113, '02-dial/sub-dial-type', '表盘'),
    (114, '02-dial/individual-dial-list', '表盘'),
    (115, '02-dial/whole-dial-list', '表盘'),
    (116, '02-dial/select-whole-dial', '表盘'),
    (117, '02-dial/select-channel-type', '表盘'),
    (118, '02-dial/get-channel-information', '表盘'),
    (119, '02-dial/select-individual-dial', '表盘'),
    (120, '02-dial/select-individual-visualizer', '表盘'),
    # TimeGate > 工具
    (121, '03-tool/countdown', '工具'),
    (122, '03-tool/stopwatch', '工具'),
    (123, '03-tool/scoreboard', '工具'),
    (124, '03-tool/noise', '工具'),
    (125, '03-tool/play-buzzer', '工具'),
    # TimeGate > 动画/自定义内容
    (126, '04-animation/get-my-like-img-list', '动画'),
    (127, '04-animation/get-img-upload-list', '动画'),
    (128, '04-animation/play-divoom-gif', '动画'),
    (129, '04-animation/play-gif', '动画'),
    (130, '04-animation/play-gif-in-all-gif', '动画'),
    (133, '04-animation/send-animation', '动画'),
    (134, '04-animation/send-text', '动画'),
    (141, '04-animation/clear-text-area', '动画'),
    (131, '04-animation/get-font-list', '动画'),
    (132, '04-animation/send-display-list', '动画'),
]


def fetch_page(page_id: int) -> dict:
    body = f'page_id={page_id}'.encode()
    req = urllib.request.Request(API, data=body, method='POST')
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def main() -> None:
    index = []
    for page_id, rel_path, section in PAGES:
        data = fetch_page(page_id)
        if data.get('error_code') != 0:
            print(f'!! page {page_id} 拉取失败: {data.get("error_message")}')
            continue
        page = data['data']
        title = page['page_title'].strip()
        content = html.unescape(page['page_content'] or '(本页无内容)').strip()
        out = DOCS_DIR / (rel_path + '.md')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            f'# {title}\n\n'
            f'> 来源：Divoom 官方 ShowDoc「第三方接口文档」TimeGate 章节，'
            f'page_id={page_id}（http://docin.divoom-gz.com/web/#/5/{page_id}），'
            f'页面最后更新时间戳 {page["addtime"]}。\n\n'
            f'{content}\n',
            encoding='utf-8',
        )
        index.append((section, title, rel_path + '.md'))
        print(f'ok page {page_id}: {title} -> {out.name}')
        time.sleep(0.3)  # 对文档站客气一点

    lines = [
        '# Divoom Times Gate 官方 API 文档（本地镜像）',
        '',
        f'- 来源：http://docin.divoom-gz.com/web/#/5（ShowDoc「第三方接口文档」，共 {len(index)} 页）',
        '- 抓取方式：`python scripts/scrape_divoom_docs.py`（官方更新后可重跑）',
        '- 说明：硬件版本 402（Times Gate）走 `http://<IP>:9000/divoom_api`，POST + JSON body；'
        '文档中标注的 `LocalToken` 在实测固件上未校验。',
        '',
        '| 章节 | 页面 | 文件 |',
        '|---|---|---|',
    ]
    for section, title, path in index:
        lines.append(f'| {section} | {title} | [{path}]({path}) |')
    (DOCS_DIR / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'\n共 {len(index)} 页，索引写入 docs/README.md')


if __name__ == '__main__':
    main()
