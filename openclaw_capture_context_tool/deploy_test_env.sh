#!/usr/bin/env bash
set -euo pipefail

# Isolated test environment deployment for OpenClaw LCM observability tool.
# Creates a separate --profile with different ports to avoid conflicts
# with production instance.

PROFILE="${1:-test}"
GATEWAY_PORT="${2:-28789}"
MITM_PORT="${3:-28080}"
API_PORT="${4:-9001}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_BASE="$HOME/openclaw-${PROFILE}-deploy"
OPENCLAW_HOME="$HOME/.openclaw-${PROFILE}"

echo "================================================================"
echo "  OpenClaw Isolated Test Environment"
echo "  Profile:       $PROFILE"
echo "  Gateway port:  $GATEWAY_PORT"
echo "  mitmproxy:     $MITM_PORT"
echo "  Capture API:   $API_PORT"
echo "  Deploy dir:    $DEPLOY_BASE"
echo "  Config dir:    $OPENCLAW_HOME"
echo "================================================================"

# Step 1: Copy lossless-claw (without node_modules)
echo ""
echo "[1/5] Deploying lossless-claw ..."
LOSSLESS_DIR="$DEPLOY_BASE/lossless-claw"
if [ -d "$LOSSLESS_DIR" ]; then
  echo "  Updating src/ ..."
  cp -r "$SCRIPT_DIR/../lossless-claw/src/" "$LOSSLESS_DIR/src/"
  cp "$SCRIPT_DIR/../lossless-claw/index.ts" "$LOSSLESS_DIR/"
  cp "$SCRIPT_DIR/../lossless-claw/package.json" "$LOSSLESS_DIR/"
  cp "$SCRIPT_DIR/../lossless-claw/openclaw.plugin.json" "$LOSSLESS_DIR/"
else
  mkdir -p "$DEPLOY_BASE"
  cd "$SCRIPT_DIR/../lossless-claw"
  tar cf - --exclude='node_modules' --exclude='.git' . | (mkdir -p "$LOSSLESS_DIR" && cd "$LOSSLESS_DIR" && tar xf -)
fi
if [ ! -d "$LOSSLESS_DIR/node_modules" ]; then
  echo "  Installing dependencies ..."
  cd "$LOSSLESS_DIR" && npm install --production 2>&1 | tail -3
fi
chmod -R 755 "$LOSSLESS_DIR"
find "$LOSSLESS_DIR/src" -name '*.ts' -exec chmod 644 {} +
echo "  [OK] $LOSSLESS_DIR"

# Step 2: Copy ai_toolbox
echo ""
echo "[2/5] Deploying ai_toolbox ..."
TOOLKIT_DIR="$DEPLOY_BASE/ai_toolbox"
CAPTURE_SRC="$SCRIPT_DIR"
if [ -d "$TOOLKIT_DIR" ]; then
  cp -r "$CAPTURE_SRC/capture_tool/" "$TOOLKIT_DIR/capture_tool/"
  cp "$CAPTURE_SRC/openclaw_capture_toolkit.sh" "$TOOLKIT_DIR/"
  cp "$CAPTURE_SRC/requirements.txt" "$TOOLKIT_DIR/"
  cp "$CAPTURE_SRC/env.example" "$TOOLKIT_DIR/"
  [ -f "$CAPTURE_SRC/export_session_capture_html.py" ] && cp "$CAPTURE_SRC/export_session_capture_html.py" "$TOOLKIT_DIR/"
else
  cd "$CAPTURE_SRC"
  tar cf - --exclude='node_modules' --exclude='.venv' --exclude='data' --exclude='.state' --exclude='.env' --exclude='.git' . | (mkdir -p "$TOOLKIT_DIR" && cd "$TOOLKIT_DIR" && tar xf -)
fi
mkdir -p "$TOOLKIT_DIR/data/context_capture_live"
chmod +x "$TOOLKIT_DIR/openclaw_capture_toolkit.sh"
echo "  [OK] $TOOLKIT_DIR"

# Step 3: Generate .env
echo ""
echo "[3/5] Generating .env ..."
cat > "$TOOLKIT_DIR/.env" << ENVEOF
STATE_DIR=./.state
CAPTURE_DATA_DIR=./data/context_capture_live
MITM_HOST=127.0.0.1
MITM_PORT=$MITM_PORT
CAPTURE_API_HOST=0.0.0.0
CAPTURE_API_PORT=$API_PORT
CAPTURE_PROXY_URL=http://127.0.0.1:$MITM_PORT
CAPTURE_API_URL=http://127.0.0.1:$API_PORT
GATEWAY_BASE_URL=http://127.0.0.1:$GATEWAY_PORT
OPENCLAW_CONFIG=$OPENCLAW_HOME/openclaw.json
LCM_DIAGNOSTICS_PATH=$OPENCLAW_HOME/lcm-diagnostics.jsonl
GATEWAY_LOG=./.state/openclaw_gateway_capture.log
MITMDUMP_BIN=
CAPTURE_API_PYTHON=
CONTEXT_CAPTURE_HTTP_URL_PREFIX=
REQUEST_MODEL=gpt-4.1-mini
REQUEST_PROMPT='OK'
REQUEST_USER=capture-tool-test
REQUEST_USE_PROXY=1
REQUEST_TIMEOUT=120
ENVEOF
echo "  [OK]"

# Step 4: Setup Python venv
echo ""
echo "[4/5] Setting up Python venv ..."
cd "$TOOLKIT_DIR"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
echo "  [OK]"

# Step 5: Configure test profile
echo ""
echo "[5/5] Configuring --profile $PROFILE ..."
mkdir -p "$OPENCLAW_HOME"
if [ -f "$HOME/.openclaw/openclaw.json" ] && [ ! -f "$OPENCLAW_HOME/openclaw.json" ]; then
  cp "$HOME/.openclaw/openclaw.json" "$OPENCLAW_HOME/openclaw.json"
fi
[ -d "$HOME/.openclaw/credentials" ] && [ ! -d "$OPENCLAW_HOME/credentials" ] && cp -r "$HOME/.openclaw/credentials" "$OPENCLAW_HOME/"
[ -d "$HOME/.openclaw/identity" ] && [ ! -d "$OPENCLAW_HOME/identity" ] && cp -r "$HOME/.openclaw/identity" "$OPENCLAW_HOME/"

# Find agent auth-profiles
PROD_AUTH=$(find "$HOME/.openclaw/agents" -name "auth-profiles.json" 2>/dev/null | head -1)
TEST_AGENT_DIR="$OPENCLAW_HOME/agents/main/agent"
if [ -n "$PROD_AUTH" ] && [ ! -f "$TEST_AGENT_DIR/auth-profiles.json" ]; then
  mkdir -p "$TEST_AGENT_DIR"
  cp "$PROD_AUTH" "$TEST_AGENT_DIR/"
fi

python3 << PYEOF
import json, os
config_path = "$OPENCLAW_HOME/openclaw.json"
lossless_path = "$LOSSLESS_DIR"
if not os.path.exists(config_path):
    print("  [SKIP] No base config to update")
    exit(0)
with open(config_path) as f:
    config = json.load(f)
plugins = config.setdefault("plugins", {})
plugins["load"] = {"paths": [lossless_path]}
plugins["slots"] = {"contextEngine": "lossless-claw"}
plugins.setdefault("entries", {})["lossless-claw"] = {
    "enabled": True,
    "config": {"contextThreshold": 0.006, "freshTailCount": 1, "leafMinFanout": 2, "condensedMinFanout": 2}
}
plugins.setdefault("installs", {})["lossless-claw"] = {
    "source": "path", "sourcePath": lossless_path, "installPath": lossless_path,
    "version": "0.4.0-refactored"
}
config.setdefault("gateway", {})["port"] = $GATEWAY_PORT
config["gateway"]["mode"] = "local"
with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
print("  [OK] Plugin config updated")
PYEOF

echo ""
echo "================================================================"
echo "  Deployment complete!"
echo ""
echo "  Start capture:"
echo "    cd $TOOLKIT_DIR && ./openclaw_capture_toolkit.sh start"
echo ""
echo "  Start gateway (separate terminal):"
echo "    LCM_DIAGNOSTICS_PATH=$OPENCLAW_HOME/lcm-diagnostics.jsonl \\"
echo "    HTTP_PROXY=http://127.0.0.1:$MITM_PORT \\"
echo "    HTTPS_PROXY=http://127.0.0.1:$MITM_PORT \\"
echo "    NODE_TLS_REJECT_UNAUTHORIZED=0 \\"
echo "    LCM_LEAF_CHUNK_TOKENS=200 \\"
echo "    openclaw --profile $PROFILE gateway run --port $GATEWAY_PORT"
echo ""
echo "  Web UI: http://127.0.0.1:$API_PORT/"
echo "  Diagnostics: ./openclaw_capture_toolkit.sh diag"
echo "================================================================"