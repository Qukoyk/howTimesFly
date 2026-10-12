# howTimesFly

> 把 Divoom Times Gate 变成一个「显示官方 App 不支持的任意内容」的通用工具。
>
> 名字来源：Times Gate 是一台时钟（Time Flies），而我们让它显示任何会随时间变化的东西（How Times Fly）。

## 为什么做这个

Times Gate 是五块 128×128 LCD 小屏组成的桌面时钟设备（原生分辨率实测：1px 棋盘格细节可辨；
16/32/64 的画面会被缩放铺满）。官方 App 提供的表盘（天气、股价、社媒数据）有限，
但设备本身留了完整的局域网 HTTP API——**Divoom 官方在 ShowDoc 上维护着「第三方接口文档」**，


本项目想解决一件事：**让每块屏显示我们想让它显示的东西**，并且让不懂 API 的人也能用。


## 目录结构

```
app/         API 服务（main.py 端点、divoom.py 设备客户端、render.py 渲染、gif_utils.py）
tests/       单元测试（渲染、推送 payload；设备调用 mock）

scripts/     维护脚本（scrape_divoom_docs.py：文档更新后重跑即可同步）
content/     推屏素材（push-all 按约定读取；个人资产不入库，从 timeGate 拷贝）
```


## 关联仓库

- `timeGate` —— 短期推送工具（curl 级别的封装，已能推屏）
- `pixoo-rest`（fork）—— Pixoo 协议参考实现，保留作对照，不用于 Times Gate

## 参考链接

- 官方文档原站：http://docin.divoom-gz.com/web/#/5
- Divoom 云端 API：https://app.divoom-gz.com
