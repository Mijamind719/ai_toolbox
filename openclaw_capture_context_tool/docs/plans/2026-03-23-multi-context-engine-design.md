# 多 Context Engine 观测重构设计

日期：2026-03-23

## 背景

当前 `openclaw_capture_context_tool` 对 `lossless-claw` 做了较深的定制，主要体现在以下几点：

- 后端直接读取 `lcm-diagnostics.jsonl`
- API 暴露了 `GET /api/lcm-diagnostics`
- 前端在浏览器里自行将 LCM 诊断和 trace 轮次做时间窗匹配
- 详情页和样式大量绑定 `LCM` 概念

这套实现对 `lossless-claw` 好用，但一旦切换到 `OpenViking` 这样的另一种 context engine，就只能看到部分 HTTP / cache-trace，而无法看到 recall、inject、capture 等 engine 专属链路。

## 目标

- 在不改变现有抓包方式的前提下，同时支持 `lossless-claw` 和 `OpenViking`
- 保留 `lossless-claw` 当前的深度诊断能力
- 为 `OpenViking` 提供深度诊断面板，而不只是“能抓到请求”
- 将轮次归因和 engine 识别收回服务端，减少前端硬编码
- 为后续第三种 context engine 预留清晰扩展点

## 非目标

- 不尝试做一个面向任意未知插件的通用插件框架
- 不改动现有 `mitmdump`、gateway 启停、offline export 的基本机制
- 不要求不同 engine 的诊断明细完全同构

## 方案选择

### 方案 1：Engine Adapter 架构

共享主链路观测，按 engine 加适配器输出专属诊断面板。

优点：

- 能同时深度支持 `lossless-claw` 与 `OpenViking`
- 公共层和专属层边界清晰
- 第三种 engine 后续可按相同模式接入

代价：

- 需要调整 API 和前端状态模型
- 需要把轮次关联逻辑从前端迁回后端

### 方案 2：超通用事件总线

把所有 engine 信息先压成完全统一的事件协议。

优点：

- 理论上结构最整齐

缺点：

- 过早抽象
- 容易丢失 `lossless-claw` 和 `OpenViking` 的阶段语义和深度信息

### 方案 3：继续按 Engine 分叉写逻辑

在现有 `lossless-claw` 代码上继续为 `OpenViking` 增加条件分支。

优点：

- 实现快

缺点：

- API、前端、解析逻辑继续耦合
- 后续再支持第三种 engine 时基本需要重构重来

结论：采用方案 1。

## 总体架构

系统拆为三层：

### 1. 共享捕获层

继续保留现有文件作为原始信号源：

- `raw.jsonl`
- `cache-trace.jsonl`
- `gateway.log.jsonl`

这层不感知具体 context engine。

### 2. 共享观测层

负责把原始信号转换成任何 engine 都适用的轮次和时间线：

- HTTP 请求与响应
- cache trace 事件
- gateway / tool 日志
- trace 起止时间、输入预览、token 统计

共享观测层负责：

- 生成 trace 列表
- 识别轮次主窗口
- 为 engine 适配器提供时间窗、session、agent 等上下文

### 3. Engine 适配层

每个 engine 通过适配器输出专属诊断结构：

- `lossless-claw adapter`
- `openviking adapter`
- `unknown adapter` 作为兜底

适配器负责：

- 识别该轮是否属于对应 engine
- 从原始日志或抓包中提取专属信号
- 组装为前端可渲染的 section 列表

## 数据模型

详情页后端统一返回 `RoundBundle`：

```text
RoundBundle
- trace
- common
  - http_blocks
  - cache_events
  - gateway_events
- engine
  - id
  - summary
  - sections
```

其中：

- `trace` 是当前轮的基础信息
- `common` 是通用链路
- `engine` 是本轮识别出的 context engine 以及其专属诊断

### Engine Section 结构

```text
EngineSection
- kind
- title
- started_at
- ended_at
- stats
- items
- raw_refs
```

约定的 `kind` 包括：

- `recall`
- `assemble`
- `capture`
- `ingest`
- `summary`
- `warning`

这个结构允许前端用统一卡片容器渲染不同 engine 的深度信息。

## API 设计

### `GET /api/timeline`

返回轮次摘要列表，仅包含：

- trace 基础信息
- engine id
- 是否存在 engine 专属诊断
- 事件计数和预览文案

### `GET /api/trace/{trace_id}`

返回完整 `RoundBundle`，包含：

- 通用时间线
- engine 专属诊断 sections

前端点击一轮后，只需要请求这一个接口即可拿到详情。

### `POST /api/clear-capture`

沿用现有实现，不受本次重构影响。

### 兼容策略

- 短期保留 `GET /api/lcm-diagnostics` 作为 legacy 接口
- 新前端只依赖 `GET /api/timeline` 与 `GET /api/trace/{trace_id}`
- 待新 UI 稳定后移除旧接口和旧客户端归因逻辑

## Engine 识别与轮次归因

轮次归因改为服务端负责，原则如下：

- 以 trace 的起止时间为主窗口
- 对有明确钩子阶段的 engine，优先使用阶段锚点收紧窗口
- 若多轮时间接近，再结合 `sessionId`、`agentId`、用户输入预览等信号缩小歧义

这样可以替代当前前端基于时间差的硬匹配逻辑。

## Lossless-Claw 适配器

`lossless-claw adapter` 继续基于 `lcm-diagnostics.jsonl` 输出：

- recall / assemble 阶段
- ingest 阶段
- afterTurn 阶段
- 召回命中、压缩摘要、消息片段、节省 token 等专属字段

现有 LCM 深度能力应该被保留，但其数据拼接和归因迁移到服务端完成。

## OpenViking 适配器

`OpenViking` 没有 `lcm-diagnostics.jsonl`，因此通过两路信号恢复诊断：

### 1. Gateway 日志

重点关注以下日志：

- `openviking: switched to agentId=... for before_prompt_build`
- `openviking: injecting N memories into context`
- `openviking: inject-detail {...}`
- `openviking: capture-check ...`
- `openviking: capture-detail {...}`
- `openviking: auto-captured ...`
- `openviking: auto-capture failed: ...`

### 2. OpenViking HTTP 报文

重点关注以下请求：

- `/api/v1/search/find`
- `/api/v1/sessions`
- `/api/v1/sessions/{id}/messages`
- extract 相关请求

### OpenViking 诊断分段

输出以下 sections：

- `Recall`
  - query
  - target URI
  - score / limit
  - 命中记忆摘要
- `Inject`
  - 注入条数
  - 注入记忆预览
  - 对应 gateway 日志引用
- `Capture Decision`
  - `shouldCapture`
  - reason
  - new message count
  - 文本预览
- `Capture Execution`
  - session 创建
  - 写入的消息预览
  - extract 结果
  - 错误原因
- `Warnings`
  - HTTP 失败
  - embedding / extract 失败
  - JSON 片段解析失败等

### OpenViking 轮次归因

优先使用以下锚点：

- `before_prompt_build`
- `afterTurn`

并将其附近的 OpenViking HTTP 请求纳入同一轮。若窗口重叠，则结合 `agentId`、session 信号进一步收紧归因。

## 前端设计

页面结构调整为：

- 左侧会话列表
  - 增加 engine badge：`lossless-claw`、`openviking`、`unknown`
- 右侧详情面板
  - 上半部分：通用链路
  - 下半部分：engine 专属诊断

前端原则：

- 详情页优先渲染通用时间线
- 若存在 `engine.sections`，则追加渲染 engine 专属卡片
- 若识别到 engine 但没有专属明细，则显示降级提示，而不是空白

这意味着前端不再直接拉取 `lcm-diagnostics` 并自行做轮次匹配。

## 错误处理

- 适配器失败不能拖垮整个 trace 页面
- 任何 engine 专属解析失败时，仅在对应 section 输出 warning
- 对日志里的 JSON 片段若解析失败，保留原始文本引用
- 若环境中没有某个 engine 的信号源，则退化为只展示通用链路

## 测试策略

### 单元测试

- `lossless-claw` 诊断样例 -> 正确 sections
- `OpenViking` 日志 + HTTP 样例 -> 正确 sections
- unknown engine -> 仅 common 视图

### API 集成测试

验证：

- `/api/timeline` 返回的 engine 摘要
- `/api/trace/{id}` 返回的 `RoundBundle`
- `engine.id` 与 `engine.sections` schema

### 手工验收

分别抓取一轮：

- `lossless-claw`
- `OpenViking`

检查：

- 左侧 badge 正确
- 右侧能显示不同 engine 的专属面板
- clear / offline export 等现有功能没有回归

## 实施顺序

1. 抽出共享 trace / round 聚合层
2. 引入 engine adapter 接口和 `unknown` 兜底实现
3. 迁移 `lossless-claw` 逻辑到 adapter
4. 新增 `OpenViking` adapter
5. 改造 `/api/timeline` 和 `/api/trace/{trace_id}`
6. 前端改为基于 `RoundBundle` 渲染
7. 保留 legacy 接口兜底，待稳定后删除

## 风险

- OpenViking 诊断依赖日志文案和 HTTP 形状，插件变更后可能需要同步适配
- 多轮并发时，OpenViking 轮次归因比 `lossless-claw` 更依赖时间窗和 session 信号
- 前端从“客户端归因”迁到“服务端归因”后，需要谨慎验证现有 LCM 时间线顺序

## 成功标准

- 同一个抓包 UI 能正确展示 `lossless-claw` 与 `OpenViking`
- 详情页可见通用链路和 engine 专属深度信息
- 不再要求前端自行拼接 `lcm-diagnostics`
- 对未知 engine 至少可以稳定展示通用链路
