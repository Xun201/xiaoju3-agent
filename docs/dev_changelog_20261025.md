# 开发者日志 2026-10-25

> 【补写时间：2026-10-31】漏写补档（对账补齐）。
> 【真实发生时间：2026-10-25】依据 git 提交重建。当日主题=**天气截胡案收官+UI 一期输入扩展栏+白屏双方案**。

- **f012cfd 天气定位截胡案**：geocoding 中文"长沙"全等命中重庆长沙镇 300km 外（湖南条目英文 Changsha 不同名，pop 过滤结构性挡不住）——三点实测定性后修四件：user_location 经纬度直用/兜底坐标表前置/表外 CN+全等+pop/显示带区县；测试 10 枚全 mock。**教训：同名行政区截胡是 geocoding 结构性风险，坐标表前置是唯一可靠解。**
- **121f4bb 白屏终极方案 A+B**：A=WS_EX_COMPOSITED 原生双缓冲注入；B=resize 视觉遮罩防抖（正交双保险）。
- **9d5a046/8ccbe72 测试与 launcher 修复**：open_meteo mock 链随语义；_print 无 flush 形参齐炸修。
- **964fc27 launcher hwnd 修 FindWindowW**：window.native.Handle 跨线程隐性失败实锤→FindWindow 零依赖+竞态重试。
- **39765f3 UI 一期输入扩展栏**：＋轻量菜单三入口/⚡技能🧩插件双浮层（新端点 /api/plugins）/上下文标签条；端点三层降级绝不 500；锚 4 枚。
