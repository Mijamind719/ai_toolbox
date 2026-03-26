# OpenClaw Context-Engine 可观测工具
对 OpenClaw 的 context-engine 插件（当前为 lossless-claw）进行全链路观测，包括 HTTP 流量抓包、LCM 诊断分析、Web UI 可视化。
## 目录结构要求

本工具需要和 `lossless-claw` 仓库作为兄弟目录放置：
```
parent_dir/
  ai_toolbox/                    <- 本仓库
    openclaw_capture_context_tool/
      deploy_test_env.sh
      openclaw_capture_toolkit.sh
      使用指南.md
      ...
  lossless-claw/                 <- lossless-claw 仓库
    src/
    package.json
    ...
```

## 前置条件

| 依赖 | 版本 | 说明 |
|------|------|------|
| Linux/WSL2 | - | 不支持 Windows 原生 |
| Node.js | 18+ | OpenClaw 运行时 |
| Python | 3.10+ | Capture API |
| OpenClaw | 已安装 | openclaw configure 已完成 |
| 模型 API Key | 已配置 | 在 OpenClaw 中配置好 provider 凭据 |

## 快速开始
### 方式一：隔离测试部署（推荐新用户）

```bash
# 1. 克隆两个仓库到同一父目录
mkdir my-openclaw-tools && cd my-openclaw-tools
git clone <ai_toolbox_repo> ai_toolbox
git clone <lossless-claw_repo> lossless-claw

# 2. 一键部署测试环境
cd ai_toolbox/openclaw_capture_context_tool
bash deploy_test_env.sh

# 3. 按输出提示启动（两个终端）
# 终端1:
cd ~/openclaw-test-deploy/ai_toolbox && ./openclaw_capture_toolkit.sh start
# 终端2:
LCM_DIAGNOSTICS_PATH=~/.openclaw-test/lcm-diagnostics.jsonl \
HTTP_PROXY=http://127.0.0.1:28080 \
HTTPS_PROXY=http://127.0.0.1:28080 \
NODE_TLS_REJECT_UNAUTHORIZED=0 \
openclaw --profile test gateway run --port 28789

# 4. 发送测试请求
LCM_DIAGNOSTICS_PATH=~/.openclaw-test/lcm-diagnostics.jsonl \
HTTP_PROXY=http://127.0.0.1:28080 \
HTTPS_PROXY=http://127.0.0.1:28080 \
NODE_TLS_REJECT_UNAUTHORIZED=0 \
openclaw --profile test agent -m "hello" --session-id "test"

# 5. 打开 Web UI: http://127.0.0.1:9001/
```

deploy_test_env.sh 自动处理: npm install、Python venv、.env 生成、profile 创建、plugin 配置、auth 复制。
### 方式二：直接使用（已有环境）

```bash
cd ai_toolbox/openclaw_capture_context_tool
./openclaw_capture_toolkit.sh setup    # 检测环境、安装依赖
cp env.example .env                    # 编辑配置
./openclaw_capture_toolkit.sh up       # 启动全栈
```

## 主要功能

- **Web UI**：会话轨迹时间线 + LCM 诊断面板 + Assemble 上下文组装可视化
- **命令行诊断**：`./openclaw_capture_toolkit.sh diag --round 2 --stage compaction_evaluate`
- **API 过滤**：`/api/lcm-diagnostics?session_id=X&stage=Y&after_ts=Z`
- **测试数据复现**：`test-fixtures/` 包含可重放的诊断数据

## lossless-claw 新增环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| LCM_DIAGNOSTICS_ENABLED | true | 设为 false 关闭诊断写入 |
| LCM_DIAGNOSTICS_PATH | ~/.openclaw/lcm-diagnostics.jsonl | 自定义诊断文件路径 |

## 方式三：OpenViking Context Engine 抓包分析

当 OpenClaw 使用 OpenViking 作为 context-engine 插件时，可抓取 assemble（上下文组装）和 afterTurn（消息存储/归档）的完整诊断数据。

### 前置条件

| 依赖 | 说明 |
|------|------|
| OpenClaw Gateway | 已安装并配置好 provider 和 token |
| OpenViking 插件 | 已部署到 `$OPENCLAW_HOME/.openclaw/extensions/openviking/` |
| Python 3.10+ | 用于 ai_toolbox API 服务 |

> **注意**：Python 3.14 + volcengine SDK 存在兼容性问题（pydantic V1 段错误），建议使用 Python 3.13 或更低版本。

### 步骤 1：安装 ai_toolbox

```bash
cd ai_toolbox/openclaw_capture_context_tool
python -m venv venv
venv/Scripts/activate    # Windows; Linux/Mac 用 source venv/bin/activate
pip install -r requirements.txt
```

### 步骤 2：创建数据目录

```bash
mkdir -p data/context_capture_live    # 抓包数据存放目录
```

### 步骤 3：启动 Gateway（带 Cache Trace）

Gateway 启动时需设置以下环境变量，开启 cache-trace 输出：

```powershell
# PowerShell (Windows)
$env:OPENCLAW_CACHE_TRACE = "1"
$env:OPENCLAW_CACHE_TRACE_FILE = "<data_dir>/cache-trace.jsonl"
$env:OPENCLAW_CACHE_TRACE_MESSAGES = "1"
$env:OPENCLAW_CACHE_TRACE_PROMPT = "1"
$env:OPENCLAW_CACHE_TRACE_SYSTEM = "1"
openclaw gateway run --port 18789 --token <your-token> --bind loopback
```

```bash
# Bash (Linux/Mac)
export OPENCLAW_CACHE_TRACE=1
export OPENCLAW_CACHE_TRACE_FILE="<data_dir>/cache-trace.jsonl"
export OPENCLAW_CACHE_TRACE_MESSAGES=1
export OPENCLAW_CACHE_TRACE_PROMPT=1
export OPENCLAW_CACHE_TRACE_SYSTEM=1
openclaw gateway run --port 18789 --token <your-token> --bind loopback
```

`<data_dir>` 替换为步骤 2 的实际路径。

### 步骤 4：启动 Gateway 日志转发

Gateway 的结构化日志需要转发到 ai_toolbox 数据目录。日志文件位于：
- Windows: `%LOCALAPPDATA%\Temp\openclaw\openclaw-YYYY-MM-DD.log`
- Linux/Mac: `/tmp/openclaw/openclaw-YYYY-MM-DD.log`

创建一个 tail 脚本，增量读取 JSON 行并追加到 `<data_dir>/gateway.log.jsonl`。

示例（PowerShell）：

```powershell
$gatewayLog = "$env:LOCALAPPDATA\Temp\openclaw\openclaw-$(Get-Date -Format 'yyyy-MM-dd').log"
$outputFile = "<data_dir>/gateway.log.jsonl"
$lastPos = 0
if (Test-Path $gatewayLog) { $lastPos = (Get-Item $gatewayLog).Length }
while ($true) {
    Start-Sleep -Milliseconds 500
    $size = (Get-Item $gatewayLog -ErrorAction SilentlyContinue).Length
    if ($size -le $lastPos) { continue }
    $stream = [IO.FileStream]::new($gatewayLog, 'Open', 'Read', 'ReadWrite')
    $stream.Seek($lastPos, 'Begin') | Out-Null
    $reader = [IO.StreamReader]::new($stream)
    while (($line = $reader.ReadLine()) -ne $null) {
        if ($line.Trim().StartsWith("{")) { $line | Out-File $outputFile -Append -Encoding utf8 }
    }
    $lastPos = $stream.Position
    $reader.Close(); $stream.Close()
}
```

### 步骤 5：启动 ai_toolbox Web UI

```bash
cd ai_toolbox/openclaw_capture_context_tool/capture_tool
python -c "
import sys; sys.path.insert(0, '.')
import uvicorn
from tools.context_capture.api import create_app
from pathlib import Path
app = create_app(data_dir=Path('<data_dir>'))
uvicorn.run(app, host='127.0.0.1', port=9001)
"
```

打开 http://127.0.0.1:9001/ 即可查看抓包数据。

### 步骤 6：发送测试请求

使用 `x-openclaw-session-key` header 保持多轮对话的 session 连续性：

```bash
curl http://127.0.0.1:18789/v1/chat/completions \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -H "x-openclaw-session-key: my-test-session" \
  -d '{"model":"your-model","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

### Web UI 展示内容

- **Context Assemble 卡片**：Session ID、Token 预算、原始/组装消息列表（可滚动查看全文）、passthrough 原因
- **Context afterTurn 卡片**：Session ID、压缩阈值、新增消息/tokens、累积 tokens、是否触发压缩、addMessage 列表

### OpenViking 插件 diag 阶段说明

| 阶段 | 时机 | 关键字段 |
|------|------|---------|
| `assemble_input` | assemble 入口 | messagesCount, inputTokenEstimate, tokenBudget, messages |
| `context_assemble` | 组装完成 | archiveCount, activeCount, passthrough, reason |
| `assemble_output` | 输出 | outputMessagesCount, estimatedTokens, tokensSaved |
| `afterTurn_entry` | afterTurn 入口 | newMessageCount, newTurnTokens, messages |
| `capture_store` | 消息存储 | stored, chars |
| `capture_skip` | 跳过压缩 | pendingTokens, commitTokenThreshold, deficit |
| `capture_commit` | 触发压缩 | status, archived, taskId |

## 详细文档

- [使用指南.md](使用指南.md) - 完整功能说明、LCM 阶段速查表、环境变量参考、故障排除
- [test-fixtures/README.md](test-fixtures/README.md) - 测试数据说明和复现步骤
