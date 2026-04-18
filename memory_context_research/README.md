# memory_context_research

用于持续研究上下文 / 记忆相关代码仓的独立工具。

当前目标：

- 每天分析目标代码仓的增量变化
- 识别有意义的新功能，而不是简单罗列 commit
- 评估这些变化对 OpenViking 是否有帮助
- 输出精简 Markdown 日报

## 目录结构

```text
memory_context_research/
  config/
    repos.yaml
    state.json
  docs/
    plans/
  research/
    artifacts/
    daily/
  src/
    memory_context_research/
  tests/
  requirements.txt
```

## 快速开始

推荐使用 `uv` 直接运行，不要求你先手工装全局依赖。

```bash
cd ai_toolbox/memory_context_research

# 查看 CLI 帮助
uv run --with pyyaml python src/memory_context_research/main.py --help

# 跑一次测试
uv run --with pyyaml --with pytest pytest -q tests/test_memory_context_research.py

# 生成某天的日报
uv run --with pyyaml python src/memory_context_research/main.py \
  --config config/repos.yaml \
  --state config/state.json \
  --date 2026-04-18
```

## 当前跟踪仓库

- `qmd`
- `claude-mem`

后续可以直接继续往 `config/repos.yaml` 里追加仓库。
