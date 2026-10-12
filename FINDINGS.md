# 实测发现记录（FINDINGS）

> 本文档汇总对 Divoom Times Gate 的全部实测结论，按主题组织。每条标注验证日期；
> 与设备相关的操作细节和恢复流程见 timeGate 仓库 README。官方文档原文镜像见 [docs/](docs/)，
> 中文翻译见 [docs/zh/](docs/zh/)。

## 1. 协议基础

- **设备只开放 TCP 9000 一个端口**，API 入口 `POST http://<IP>:9000/divoom_api`，只接受
  JSON body；GET 或不存在的命令返回 `{"ReturnCode":1,"ReturnMessage":"Only accept JSON parameters"}`
  （2026-09-05 全端口扫描 + 探测）。
- **官方文档真实存在**：ShowDoc「第三方接口文档」`http://docin.divoom-gz.com/web/#/5`，
  域名与官网同一 ICP 主体，旧地址 doc.divoom-gz.com 已迁移（仅剩 developer@divoom.com 联系页）。
  文档明确：硬件版本 400 走 `http://IP:80/post`，402（Times Gate）走 `http://IP:9000/divoom_api`。
- 文档标注必填的 `LocalToken` 在实测固件上**不校验**（带假值或不带都放行）。
- 命令按白名单放行，名单外的命令与"参数错误"返回同一种报错，文案有误导性。

## 2. 屏幕硬件特性

- **每块屏原生 128x128 LCD**（2026-09-06 棋盘格实验：1px 细节可辨；16/32/64 的画面会被
  缩放铺满，`PicWidth` 支持 16/32/64/128）。
- **LCD 驱动无整帧同步刷新（无 vsync/双缓冲）**：每帧全画面变化的动画必然水平撕裂，
  与管线、帧率无关（350ms 仍撕）。设计规则：大面积像素保持不变，只让小范围元素运动。
- **设备不解码 GIF 差分帧**：PIL 默认只编码变化区域，设备渲染出灰色残块/卡顿。
  自制 GIF 必须全画布帧（timeGate 仓库 `gif_utils.py`，角落点技巧强制整帧）。
- **五屏是五个独立解码循环**：`PlayGifLCDs` 只保证同时起播，各屏偶发解码超时就永久
  跳一拍，几十分钟累积成可见漂移（2026-09-18）。缓解：`tg.py watch` 定期重对齐。

## 3. 同步与播放（核心发现）

- **跨屏同步各播各画的正解是 `Device/PlayGifLCDs`**（官方文档 page 130）：
  一条命令带 `LCD0GifFile`~`LCD4GifFile` 五个独立数组（每屏一个播放列表），设备一秒内
  拉取全部文件并同时开播。2026-09-06 实测，中间三屏目视同步。
- **`Device/PlayGif` 多文件 + LcdArray 是播放列表语义**：所有选中屏轮流播完全部文件，
  不是"第 i 个文件给第 i 块屏"（3 文件 3 屏、5 文件 5 屏两种形态都实测轮播）。
- **`Draw/CommandList` 与 `Draw/UseHTTPCommandSource` 在该固件上被静默忽略**
  （ReturnCode 0 但不执行，服务器访问日志实证；文档标注 90102 版固件才支持）。
- **多屏交错逐帧 `SendHttpGif` 会损坏播放器状态**：某屏陷入 Loading↔画面闪烁，
  切官方表盘也闪、软复位无效，唯一解法 `Device/SysReboot`。逐帧只做单屏顺序推送。
- **`PlayGifLCDs` 是追加队列而非清空队列**：App 推送留下的坏条目（症状：系统
  "Loading+旋转沙漏"与有效内容轮闪，叠加在画面中央）无法用 resync/软复位清除，
  唯一解法同样是 SysReboot 重建播放队列（2026-09-18 实测）。
- **竞态提醒**：PlayGifLCDs 异步应用各屏播放列表（拉文件约 1-2 秒），紧接着推的
  单屏内容会被随后落地的占位盖掉——`tg.py resync` 里已用 5 秒等待规避。

## 4. 固件行为坑

- **设备端文字渲染可用但有代价（2026-09-18 重测，修正早先结论）**：原记录"2026-09-05
  固件更新后 `SendHttpText` 静默失效"是误判——当天是临时卡死，不是固件坏了。重测
  （font 4、speed 100、单帧底图）文字正常出字；但滚动文字的字体由设备从云端拉取，
  重绘会间歇触发"Loading+沙漏"，并最终把该屏播放器搞成「文字 ↔ Loading ↔ 底图」
  三态轮闪，清文字（ClearHttpText）也回不去，SysReboot 才恢复。`SendHttpItemList`
  文字元素未重测，结论不明。对策不变：文字一律电脑端 PIL 渲染成图片走动画通道——
  这是稳定性选择，不是通道不可用。
- `Draw/SendHttpText` 的 `speed` 固件上限 **100**（≥110 被拒，报的还是那句误导文案）。
- `Draw/SendHttpItemList` 缺 `BackgroudGif` 或字体 id 无效时，设备卡"Loading+沙漏"
  ——背景图与字体都是设备从 Divoom 云端下载的资源。
- **不要在 ItemList 里用云端表盘字体**（如 Galmuri7 id=300）：会卡 Loading；连发三个
  后设备网络栈直接挂掉（ping 不通、9000 拒连），需断电重启 + App 重新配网（2026-09-05，
  这次事故烧掉了一晚上）。
- 播放器状态深度损坏时，软件手段（ResetHttpGifId/切表盘/重推）均无效，
  `Device/SysReboot` 实测可修复；**重启/断电后自定义内容全部丢失**，需重新推送。

## 5. 云端与数据

- **状态查询走云端**：`https://app.divoom-gz.com/Channel/Get5LcdInfoV2`
  （参数 `DeviceId` + `DeviceType:"LCD"`）返回五屏完整配置（模式、各屏表盘 id、独立布局）；
  设备 DeviceId 在任意 LAN 响应里自带。
- **自定义数据上屏是官方机制**：`Draw/SendHttpItemList` type 23 让设备定时轮询 URL 并显示
  返回 JSON 的 `DispData` 字段（解析规则见 docs/00-common/diy-net-data-clock.md）——
  中期免服务器方案的基础，密钥永远留在服务端（见 timeGate README 安全原则）。
- GLM Coding Plan 额度端点：`GET <base>/api/monitor/usage/quota/limit`
  （Authorization 放 Coding Plan token），来自智谱官方插件 zai-coding-plugins 源码；
  返回的 percentage 是已用百分比。

## 6. 运维与环境

- **换网络/搬家恢复流程**：改 `.env` 的 `DEVICE_IP` → 探测电脑新局域网 IP（URL 内嵌它）
  → 清 8765 端口僵尸进程、重起文件服务 → `tg.py resync`（含额度覆盖）。办公网络实测：
  设备可反向访问电脑（2026-09-18）。
- **本机开发陷阱**：裸 `python` 是 Windows 商店占位符——运行不报错、print 正常输出，
  但文件写入进 MSIX 虚拟化目录、真实磁盘不变（"成功但没生效"）。一律 `uv run python`。
- **固件更新有风险**："更新后文字渲染静默失效"后经重测证实是误判（临时卡死，见第 4 节），
  但"损坏状态需重启"是真实存在的问题；每次固件更新后仍应逐项回归测试（官方博客同样建议）。

## 7. 专题分析：1 屏（LcdIndex 0）"内容 ↔ Loading 沙漏"轮闪的根因（2026-09-18）

**症状**：同一张静态图从 App 推送到五块屏，2-5 屏全部正常，唯独 1 屏在图片与
"Loading+旋转沙漏"之间来回闪；健康动画再推送也无法根治；仅 SysReboot 后恢复正常。

**根因模型**（证据充分的机制推断）：

1. **每块屏有一个"订阅画廊"（Subscribe Gallery）轮播列表**——官方文档 page 138
   `Channel/SetSubscribeGalleryTime` 证实：轮播参数按 `LcdIndex`（0~4）+ `LcdIndependence`
   独立设置，`SingleGalleyTime` 是每个条目的播放时长。App 的"推送到某块屏"就是往
   目标屏的画廊列表**追加**一个条目。
2. **轮播到加载失败的条目时，设备显示 Loading+沙漏**——与 ItemList 缺资源卡 Loading
   是同一族指示器。坏条目会一直留在列表里轮转。
3. **`PlayGifLCDs`/`PlayGif`（play 频道指派）与画廊是两套并行机制**：前者覆盖当前显示
   但不清除画廊列表——所以 resync/重推都治不了轮闪（2026-09-18 两次实测失败），
   只有 SysReboot 重建运行时状态才生效（重启后恢复正常的两次实测）。
4. **为什么只有 1 屏坏**：第一次 App 推送（两帧动画：文字+空白）在 1 屏画廊里留下了一个
   资源加载失败的条目；2-5 屏从未收到过那次推送，画廊里只有有效条目。此后任何一次
   往 1 屏的 App 推送都会让画廊轮转恢复运行（或再次追加条目），坏条目重新开始轮转。

**缓解与规避**（按推荐排序）：

1. **在 Divoom App 里找到并删除 1 屏画廊里的坏条目**（App 内应有已推内容的管理/删除
   入口）——删除后画廊干净，App 推送可正常使用。这是唯一的根修复，待用户在 App 中确认；
2. 规避：不要从 App 往 1 屏推画廊内容；需要 1 屏显示特定内容时走我们自己的管线
   （`tg.py push-gif`，单屏顺序逐帧推送，安全）；
3. 闪烁发作时：`resync` 可压制 5 分钟（PlayGifLCDs 覆盖显示），根治需 SysReboot
   （重启后服务器 5 分钟内自动恢复全部内容）；
4. 长期：向 developer@divoom.com 报告该行为（App 推送产生不可加载的画廊条目且无清除 API）。

**遗留疑点**：为什么 1 屏的 App 推送会产生坏条目而 2-5 屏不会——最可能是 LcdIndex 0
在固件/App 中角色特殊（主屏），或首次坏条目一直在 1 屏列表里未被清除、后续推送只是
重新激活了轮转。App 内删除坏条目后若不再复发，则后者成立。

## 8. 待验证 / 长期跟踪

- 固件升级到 90102+ 后，重测 `Draw/CommandList` / `Draw/UseHTTPCommandSource`
  （批量命令若生效，可做更优雅的同步与编排）。
- 设备重启/断电后自定义内容是否可持久化（当前结论：不能，需重推）。
- 向 developer@divoom.com 提议"跨屏拼接播放/同步起播"命令（长期目标顺路）。
- `SendHttpText` 轮闪的诱因隔离（换 font id / TextWidth / dir 参数、非滚动模式、
  多帧底图）；找到稳定参数组合后可作为 API 传统文字端点的基础。
