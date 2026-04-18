# memory_context_research 实现计划

Date: 2026-04-18
Status: draft for implementation

## 目标

先落一个稳定可运行的 MVP，实现：

- 读取待分析代码仓配置
- 基于 git 增量提取变化
- 对上下文 / 记忆相关变化做启发式分析
- 生成每日 Markdown 日报
- 保存基础 state 与 artifacts

## 分阶段实现

### Phase 1: MVP 骨架

交付内容：

- `src/memory_context_research/`
- 配置与状态读写模块
- git 仓库更新与 diff 提取模块
- 启发式变更分析模块
- Markdown 日报输出模块
- 基础测试

### Phase 2: 语义增强

交付内容：

- 基于 PR / changelog / release note 的辅助归因
- 更细粒度的能力标签与 OV 影响判断
- 更稳健的噪音过滤规则

### Phase 3: 产物消费增强

交付内容：

- 周报聚合
- OpenViking 写回 sink
- skill 封装
- 消息推送

## MVP 模块拆分

### `config.py`

- 解析 `repos.yaml`
- 提供配置默认值
- 校验必要字段

### `state.py`

- 读写 `state.json`
- 管理每个仓库的增量游标与上次成功时间

### `git_tools.py`

- 定位或准备本地仓库
- 执行 `git fetch`
- 计算分析区间
- 提取 commit 列表与变更文件

### `analyzer.py`

- 过滤明显噪音
- 根据路径、提交标题、关键字做相关性判断
- 产出结构化结论

### `report.py`

- 生成日报 Markdown
- 生成 `raw.json` / `summary.json`

### `main.py`

- 串联整个流水线
- 提供 CLI 入口

## 测试策略

MVP 只做轻量但高价值的验证：

- 配置文件默认值和字段解析
- 状态文件 round-trip
- 基于临时 git 仓库的增量分析
- 日报是否包含预期结构和关键结论

## 完成标准

满足以下条件时，MVP 可视为完成：

- 可以通过命令行对配置中的代码仓执行一次分析
- 可以产出 `research/daily/YYYY-MM-DD.md`
- 可以产出对应 artifacts
- 可以正确记录并推进 `config/state.json`
- 相关测试通过
