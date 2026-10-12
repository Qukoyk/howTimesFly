# howTimesFly

> 把 Divoom Times Gate 变成一个「显示官方 App 不支持的任意内容」的通用工具。
>
> 名字来源：Times Gate 是一台时钟（Time Flies），而我们让它显示任何会随时间变化的东西（How Times Fly）。

## 为什么做这个

Times Gate 是五块 128×128 LCD 小屏组成的桌面时钟设备（原生分辨率实测：1px 棋盘格细节可辨；
16/32/64 的画面会被缩放铺满）。官方 App 提供的表盘（天气、股价、社媒数据）有限，
但设备本身留了完整的局域网 HTTP API——**Divoom 官方在 ShowDoc 上维护着「第三方接口文档」**，
本仓库的 docs/ 目录就是这份文档中 Times Gate 相关内容的完整本地镜像（42 页，重跑
scripts/ 脚本可更新；官方内容不入库，见目录结构说明）。

本项目想解决一件事：**让每块屏显示我们想让它显示的东西**，并且让不懂 API 的人也能用。

## 三阶段路线图

### 阶段一（短期）：推内容 ✅ 已完成验证

仓库：`D:\Codes\timeGate`（命令行推送工具）。

技术事实（全部实测验证，2026-09-05）：

- 设备只开一个 TCP 端口 **9000**，API 为 `POST http://<设备IP>:9000/divoom_api`，JSON body；
- **可以指定单块屏**：`Draw/SendHttpGif` / `Device/PlayGif` 带 `LcdArray`（如 `[1,0,0,0,0]`），
  `Draw/SendHttpText` / `Channel/SetClockSelectId` 带 `LcdIndex`（0~4）；
- **自定义内容可上屏**：逐帧推 JPG 动画（`Draw/SendHttpGif`）、叠滚动文字（`Draw/SendHttpText`）、
  让设备自己下载 URL 上的 GIF（`Device/PlayGif`）、自定义数据表盘（`Draw/SendHttpItemList` + NetData）；
- **跨屏同步各播各画（2026-09-06 实测）**：`Device/PlayGifLCDs` 一条命令带
  `LCD0GifFile`~`LCD4GifFile` 五个数组，五屏同时开播各自内容——开机动画同款的统一时钟入口。
  陷阱清单：`Device/PlayGif` 多文件是播放列表不是分屏映射；`Draw/CommandList`/
  `Draw/UseHTTPCommandSource` 在该固件（<90102）被静默忽略；多屏交错逐帧推送会损坏播放器状态
  （唯一解法 SysReboot）；自制 GIF 必须全画布帧（设备不解码差分帧）；
- **RGB 灯效 HTTP 直控**（`Channel/SetRGBInfo`），无需蓝牙；
- **状态查询走云端**：`https://app.divoom-gz.com/Channel/Get5LcdInfoV2`（DeviceId + DeviceType:"LCD"）
  返回五块屏完整配置；
- 文档里很多命令标注必填 `LocalToken`，实测固件不校验；
- 固件有文档没写的参数边界：`Draw/SendHttpText` 的 `speed` 上限 100（实测 ≥110 被拒，报的还是那句
  误导性的 `Only accept JSON parameters`）；
- 注意：pixoo-rest（本方案的参考项目）走的是 400 代协议（80 端口 `/post`），对 Times Gate 完全不通，
  不要在它基础上改。

### 阶段二（中期）：API 服务器 🚧 本仓库的主体（v1 已实现，2026-09-18 定稿）

v1 先把 API 立起来，网页界面后置——它以后只是这个 API 的第一个消费者。

- **FastAPI + Swagger UI**：`uv sync` 后 `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`，
  浏览器开 `http://127.0.0.1:8000/docs` 即可调用全部端点；
- **动作式端点，同步返回**：`POST /screens/{i}/gif|image|text|clear-text|dial`、
  `POST /banner`（宽图跨多屏，`screens` 参数指定 2-5 块）、`POST /push-all`（按 content/ 约定）、
  `POST /quota`（GLM 额度屏，`lcd_index` 参数指定，默认第 5 块）、
  `GET /screens`（云端五屏配置）、`GET /health`（设备在线检查，只读）；
- **内容走 multipart 文件上传**（Swagger UI 自带文件按钮），文字/表盘参数走 JSON；
- **文字由服务端 PIL 渲染成图片再推**——`SendHttpText` 通道可用但字体走云端拉取，会间歇
  触发"Loading+沙漏"甚至把播放器搞成轮闪（2026-09-18 实测，详见 [FINDINGS.md](FINDINGS.md)），
  `/text` 零云端依赖、稳定；
- **设备写操作强制串行**（多屏交错逐帧推送会损坏播放器状态，硬约束）；
- **无认证、按需启动、单台设备**（IP/token 走 `.env`，从 timeGate 抄即可）；
- 代码自 timeGate 复制（`api_call`/渲染/推送/`gif_utils`，陷阱注释原样保留），timeGate 仓库不动；
- 测试：渲染与推送 payload 单测（设备 mock，`uv run pytest`），真机各端点用 Swagger UI 冒烟。

v2+（后置，顺序不承诺）：网页配置界面、base64 输入、内容库管理、NetData 数据挂件（断电续显）、
常驻运行、多设备、认证（家庭/开源场景）。

### 阶段三（长期）：进官方生态

两条正路，可并行：

1. **官方 DIY 机制本身就是口子**：「DIY Net Data Clock」（docs/00-common/diy-net-data-clock.md）是
   Divoom 官方设计的自定义数据表盘机制。把我们的数据源做成通用规则，"官方 App 不支持的内容"
   就升级成"官方 App 支持的自定义内容"；云端表盘生态（`Channel/GetDialList`）说明表盘是可提交的资产。
2. **直接联系官方**：官方文档联系页明确邀请第三方开发者——developer@divoom.com。
   想进官方 App，走"表盘/数据源创作者"这条门。

## 目录结构

```
app/         API 服务（main.py 端点、divoom.py 设备客户端、render.py 渲染、gif_utils.py）
tests/       单元测试（渲染、推送 payload；设备调用 mock）
docs/        Divoom 官方 API 文档 Times Gate 相关内容的本地镜像（42 页，docs/zh/ 为中文
             翻译）。官方内容不入库（避版权嫌），克隆后重跑 scripts/ 可再生成
scripts/     维护脚本（scrape_divoom_docs.py：文档更新后重跑即可同步）
content/     推屏素材（push-all 按约定读取；个人资产不入库，从 timeGate 拷贝）
FINDINGS.md  全部实测发现的正式记录（协议/硬件/同步/固件坑/运维，持续更新）
```

## 实测备忘（持续更新；完整汇总见 [FINDINGS.md](FINDINGS.md)）

- **办公网络实测（2026-09-18）**：设备可反向访问电脑的文件服务，
  PlayGifLCDs 全流程直接可用；设备换网后 IP 变化，恢复流程见 timeGate README；
- **本机开发陷阱**：裸 `python` 是 Windows 商店占位符（MSIX 虚拟化写入，"成功但没生效"），
  一律 `uv run python`；Git Bash 后台起文件服务用
  `cd content && uv run python -m http.server 8765 --bind 0.0.0.0`（run_in_background），
  重启前先清 8765 端口僵尸进程；
- **GIF 全画布帧**：设备不解码差分帧（PIL 默认省空间写法），自制 GIF 必须用
  timeGate 仓库 `gif_utils.py` 的 `save_gif_fullframes()`（角落点技巧强制整帧，
  白色内容不能用通道偏移法——255+1 模 256 绕回 0 会轮变色）；
- **PlayGifLCDs 的 LCD4 会被后续 quota 推送覆盖**：五屏命令之后执行 `tg.py quota`
  才能让第 5 块屏显示真实额度。

## 关联仓库

- `timeGate` —— 短期推送工具（curl 级别的封装，已能推屏）
- `pixoo-rest`（fork）—— Pixoo 协议参考实现，保留作对照，不用于 Times Gate

## 参考链接

- 官方文档原站：http://docin.divoom-gz.com/web/#/5
- Divoom 云端 API：https://app.divoom-gz.com
- 我们的实测记录：pixoo-rest 仓库内《使用手册.md》第 2 章
