# OpenClaw Context-Engine 鍙娴嬪伐鍏?
瀵?OpenClaw 鐨?context-engine 鎻掍欢锛堝綋鍓嶄负 lossless-claw锛夎繘琛屽叏閾捐矾瑙傛祴锛屽寘鎷?HTTP 娴侀噺鎶撳寘銆丩CM 璇婃柇鍒嗘瀽銆乄eb UI 鍙鍖栥€?
## 鐩綍缁撴瀯瑕佹眰

鏈伐鍏烽渶瑕佸拰 `lossless-claw` 浠撳簱浣滀负鍏勫紵鐩綍鏀剧疆锛?
```
parent_dir/
  ai_toolbox/                    <- 鏈粨搴?    openclaw_capture_context_tool/
      deploy_test_env.sh
      openclaw_capture_toolkit.sh
      浣跨敤鎸囧崡.md
      ...
  lossless-claw/                 <- lossless-claw 浠撳簱
    src/
    package.json
    ...
```

## 鍓嶇疆鏉′欢

| 渚濊禆 | 鐗堟湰 | 璇存槑 |
|------|------|------|
| Linux/WSL2 | - | 涓嶆敮鎸?Windows 鍘熺敓 |
| Node.js | 18+ | OpenClaw 杩愯鏃?|
| Python | 3.10+ | Capture API |
| OpenClaw | 宸插畨瑁?| openclaw configure 宸插畬鎴?|
| 妯″瀷 API Key | 宸查厤缃?| 鍦?OpenClaw 涓厤缃ソ provider 鍑嵁 |

## 蹇€熷紑濮?
### 鏂瑰紡涓€锛氶殧绂绘祴璇曢儴缃诧紙鎺ㄨ崘鏂扮敤鎴凤級

```bash
# 1. 鍏嬮殕涓や釜浠撳簱鍒板悓涓€鐖剁洰褰?mkdir my-openclaw-tools && cd my-openclaw-tools
git clone <ai_toolbox_repo> ai_toolbox
git clone <lossless-claw_repo> lossless-claw

# 2. 涓€閿儴缃叉祴璇曠幆澧?cd ai_toolbox/openclaw_capture_context_tool
bash deploy_test_env.sh

# 3. 鎸夎緭鍑烘彁绀哄惎鍔紙涓や釜缁堢锛?# 缁堢1: cd ~/openclaw-test-deploy/ai_toolbox && ./openclaw_capture_toolkit.sh start
# 缁堢2:
LCM_DIAGNOSTICS_PATH=~/.openclaw-test/lcm-diagnostics.jsonl \
HTTP_PROXY=http://127.0.0.1:28080 \
HTTPS_PROXY=http://127.0.0.1:28080 \
NODE_TLS_REJECT_UNAUTHORIZED=0 \
openclaw --profile test gateway run --port 28789

# 4. 鍙戦€佹祴璇曡姹?LCM_DIAGNOSTICS_PATH=~/.openclaw-test/lcm-diagnostics.jsonl \
HTTP_PROXY=http://127.0.0.1:28080 \
HTTPS_PROXY=http://127.0.0.1:28080 \
NODE_TLS_REJECT_UNAUTHORIZED=0 \
openclaw --profile test agent -m "hello" --session-id "test"

# 5. 鎵撳紑 Web UI: http://127.0.0.1:9001/
```

deploy_test_env.sh 鑷姩澶勭悊: npm install銆丳ython venv銆?env 鐢熸垚銆乸rofile 鍒涘缓銆乸lugin 閰嶇疆銆乤uth 澶嶅埗銆?
### 鏂瑰紡浜岋細鐩存帴浣跨敤锛堝凡鏈夌幆澧冿級

```bash
cd ai_toolbox/openclaw_capture_context_tool
./openclaw_capture_toolkit.sh setup    # 妫€娴嬬幆澧冦€佸畨瑁呬緷璧?cp env.example .env                    # 缂栬緫閰嶇疆
./openclaw_capture_toolkit.sh up       # 鍚姩鍏ㄦ爤
```

## 涓昏鍔熻兘

- **Web UI**锛氬璇濊建杩规椂闂寸嚎 + LCM 璇婃柇闈㈡澘 + Assemble 涓婁笅鏂囩粍瑁呭彲瑙嗗寲
- **鍛戒护琛岃瘖鏂?*锛歚./openclaw_capture_toolkit.sh diag --round 2 --stage compaction_evaluate`
- **API 杩囨护**锛歚/api/lcm-diagnostics?session_id=X&stage=Y&after_ts=Z`
- **娴嬭瘯鏁版嵁澶嶇幇**锛歚test-fixtures/` 鍖呭惈鍙噸鏀剧殑璇婃柇鏁版嵁

## lossless-claw 鏂板鐜鍙橀噺

| 鍙橀噺 | 榛樿 | 璇存槑 |
|------|------|------|
| LCM_DIAGNOSTICS_ENABLED | true | 璁句负 false 鍏抽棴璇婃柇鍐欏叆 |
| LCM_DIAGNOSTICS_PATH | ~/.openclaw/lcm-diagnostics.jsonl | 鑷畾涔夎瘖鏂枃浠惰矾寰?|

## 璇︾粏鏂囨。

- [浣跨敤鎸囧崡.md](浣跨敤鎸囧崡.md) - 瀹屾暣鍔熻兘璇存槑銆丩CM 闃舵閫熸煡琛ㄣ€佺幆澧冨彉閲忓弬鑰冦€佹晠闅滄帓闄?- [test-fixtures/README.md](test-fixtures/README.md) - 娴嬭瘯鏁版嵁璇存槑鍜屽鐜版楠?