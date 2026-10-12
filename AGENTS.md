# AGENTS.md

Divoom Times Gate（五块 128×128 LCD 屏的桌面时钟）的第三方 API 服务器：FastAPI + Swagger UI，
动作式端点、同步返回、局域网无认证、按需启动、单台设备。定位与路线图见 [README.md](README.md)。

## 动手前先读

- [FINDINGS.md](FINDINGS.md) —— 全部实测结论（协议、屏幕硬件、同步播放的坑），改推送逻辑前必读。
- README.md「实测备忘」章节 —— 本机开发陷阱（python 占位符、端口僵尸进程等）。
- docs/ —— Divoom 官方 API 文档的本地镜像（42 页，中文版在 docs/zh/；**不入库**，
  克隆后重跑 scripts/ 可再生成）；协议字段以它和实测为准。
- 关联仓库 `D:\Codes\timeGate` —— 阶段一 CLI 工具，代码来源；设备恢复流程见其 README。

## 目录与命令

```
app/main.py    FastAPI 端点（全部 10 个）+ 错误翻译
app/divoom.py  设备客户端（HTTP 封装、串行锁、推送函数；.env 在这里读）
app/render.py  纯 PIL 逻辑：文字渲染、帧提取、横幅裁条（可单测）
app/gif_utils.py  全画布帧 GIF 保存（设备不解码差分帧）
tests/         单测（设备调用 mock；改纯逻辑必须带测试）
content/       推屏素材，push-all 按约定读取（不入库，从 timeGate 拷贝）
```

```bash
uv sync                                                    # 装依赖
uv run pytest                                              # 全部单测
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000     # 起服务，/docs 是 Swagger UI
```

- 一律 `uv run python`：裸 `python` 是 Windows 商店占位符（MSIX 虚拟化，「成功但没生效」）。
- Shell 是 Git Bash（win32）。Python ≥3.12。

## 架构规则（改代码时别破坏）

- **设备写操作必须走 `app/divoom.py` 的 `_device_lock` 串行**：多屏交错逐帧推送会永久损坏
  播放器状态，唯一恢复是断电级 SysReboot。这是硬约束，不是优化。锁是 RLock（push 函数会嵌套）。
- **文字一律服务端 PIL 渲染再走图片通道**：SendHttpText 通道本身可用（早先「固件失效」
  是误判，2026-09-18 重测），但字体由设备从云端拉取，会触发"Loading+沙漏"轮闪、
  需 SysReboot 才能恢复。不要「顺手」改回设备字体方案——服务端渲染是稳定性选择。
- 端点风格是动作式（`POST /screens/{i}/gif`），同步返回；不要引入任务队列、状态存储或资源式 REST。
- 错误翻译集中在 `main.py` 的 `_call_device`：设备错误/连不上 → 502 + 人话提示（IP 会变）。
- HTTP 客户端用 `requests`（同步端点跑 FastAPI 线程池），不要换 httpx/async。
- 新的纯逻辑放 `render.py` 并配单测；涉及设备 payload 的测试用 monkeypatch 替换 `divoom.api_call`。

## 已知边界（写代码前对一眼 FINDINGS.md，这里是高频项）

- 单次动画最多 60 帧；`PicID` 必须进程内唯一递增（时间戳取整会重复 → 设备疯狂 Loading）。
- 连续推送动画之间留 ~2 秒间隔（温和推送，压垮固件会出怪状态）。
- 动画大面积像素必须保持不变（LCD 无 vsync，整帧变化必撕裂）。
- `SendHttpText` 的 `speed` 固件上限 100，超限报误导性的「Only accept JSON parameters」。
- 屏幕编号 0-4 从左到右；banner 的 `screens` 参数与 quota 的 `lcd_index` 都可指定屏幕，
  默认值保持当前物理布局（banner=1,2,3，quota=第 5 块）。
- 设备 IP 在 `.env`（不入库），换网会变；连不上先怀疑 IP，别怀疑代码。

## 约定

- 注释、文档、API 描述全用中文；timeGate 搬来的陷阱注释原样保留。
- 不动 `D:\Codes\timeGate` 仓库；本仓库代码是复制不是引用。
- git 提交由用户确认后进行（实测真机验证过了才提交）。`.env`、`content/` 不入库。
