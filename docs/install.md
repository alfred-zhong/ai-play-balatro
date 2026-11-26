# 安装配置

从零搭起这套环境。实测于 macOS + Apple Silicon + Steam 版 Balatro 1.0.1o-FULL。

---

## 0. 前置检查

```bash
# 确认 Balatro 是 Steam 版且路径存在
ls "$HOME/Library/Application Support/Steam/steamapps/common/Balatro/"
```

同时确认有 python3：

```bash
which python3   # 本机用的是 /opt/homebrew/bin/python3
```

---

## 1. Lovely Injector（mod 加载器）

Steamodded 和 balatrobot 都依赖 Lovely 做 dylib 注入。

### 1.1 为什么需要它

Balatro 是 LÖVE 打包的，Lua 代码编译进 `Balatro.love`。Lovely 通过 `DYLD_INSERT_LIBRARIES`
在启动时劫持 LÖVE 的文件加载，让你能覆盖/追加 Lua 代码。

### 1.2 装法

从 <https://github.com/ethangreen-dev/lovely-injector/releases> 下载 macOS arm64 版本，
解压后：

```bash
B="$HOME/Library/Application Support/Steam/steamapps/common/Balatro"

# 把 dylib 放到游戏目录
cp liblovely.dylib "$B/"

# 建启动脚本
cat > "$B/run_lovely_macos.sh" <<'EOF'
#!/bin/bash
cd "$(dirname "$0")"
export DYLD_INSERT_LIBRARIES=liblovely.dylib
exec ./Balatro.app/Contents/MacOS/love "$@"
EOF
chmod +x "$B/run_lovely_macos.sh"
```

### 1.3 验证

```bash
cd "$B" && ./run_lovely_macos.sh
```

日志里应该出现 `[♥] Lovely 0.10.0`。如果没注入成功，检查：

- 二进制是否有 hardened runtime（`codesign -dv Balatro.app` 看 `flags=`）
  - 本机版本是 adhoc/linker-signed、**无 hardened runtime**，所以能注入
  - 如果有 hardened runtime，需要先 `codesign --remove-signature` 或用其他手段

---

## 2. Steamodded（mod 框架）

```bash
MODS="$HOME/Library/Application Support/Balatro/Mods"
mkdir -p "$MODS"

# 从 https://github.com/Steamodded/smods/releases 下载最新版
# 解压后整个目录重命名为 smods
```

验证：启动后日志出现 `Steamodded v26.1002.0`（或更新版本）。

---

## 3. balatrobot（HTTP API mod）

这是关键组件，把游戏操作暴露成 JSON-RPC。

```bash
cd "$MODS"
git clone https://github.com/coder/balatrobot.git
```

验证：启动后日志出现

```
BB.SERVER :: HTTP server listening on http://127.0.0.1:12346
```

### 3.1 启动环境变量

| 变量 | 建议值 | 说明 |
|---|---|---|
| `BALATROBOT_FAST` | **0** | ⚠️ 设 1 会崩，见下 |
| `BALATROBOT_GAMESPEED` | 4 | 动画速度，4 已足够快 |
| `BALATROBOT_AUDIO` | 0 | 静音 |

**`BALATROBOT_FAST=1` 会导致崩溃**：

```
game.lua:2610: attempt to perform arithmetic on field 'GAMESPEED' (a nil value)
```

FAST 把 GAMESPEED 强推 10，与其他时序冲突，第一次出牌进结算动画就崩。用 `FAST=0 GAMESPEED=4`。

### 3.2 启动

```bash
B="$HOME/Library/Application Support/Steam/steamapps/common/Balatro"
cd "$B" && BALATROBOT_FAST=0 BALATROBOT_GAMESPEED=4 BALATROBOT_AUDIO=0 ./run_lovely_macos.sh
```

约 14-20 秒后才可用。用 `tools/restart.sh` 更省心（处理端口抢占）。

---

## 4. 自建端点（本仓库的 mods/）

`balatrobot` 自带的端点只能「操作」，不能「预算分数」。本仓库补了两个：

### 4.1 安装

```bash
MODS="$HOME/Library/Application Support/Balatro/Mods"
cp mods/simulate.lua "$MODS/balatrobot/src/lua/endpoints/"
cp mods/probe.lua    "$MODS/balatrobot/src/lua/endpoints/"

# 注册到端点列表
# 编辑 $MODS/balatrobot/balatrobot.lua，在 BB_ENDPOINTS 里加两行：
#   "src/lua/endpoints/probe.lua",
#   "src/lua/endpoints/simulate.lua",
```

### 4.2 验证

```bash
curl -s -X POST http://127.0.0.1:12346 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"probe","id":1}'
```

应返回 `gamespeed` / `speedfactor` / `state` 等。

`simulate` 需要在 `SELECTING_HAND` 状态下调用，否则报状态错误。

---

## 5. 验证整套链路

```bash
# 启动
bash tools/restart.sh

# 看状态
python3 tools/mech.py status
# 期望: state=MENU

# 开局
python3 tools/mech.py start BLACK WHITE
python3 tools/mech.py select

# 精确算分（核心功能）
python3 tools/mech.py look
```

`look` 能输出组合排名就说明全部就绪。

---

## 6. 常见问题

### `Failed to bind to port 12346: address already in use`

端口 TIME_WAIT 残留。用 `tools/restart.sh`，它会等到端口真正干净。

手动的话：

```bash
pkill -9 -f "Balatro.app/Contents/MacOS/love"
# 等到这两个都空
lsof -nP -iTCP:12346
netstat -an -p tcp | grep 127.0.0.1.12346
```

### `Method 'start' requires one of these states: MENU`

`tools/mech.py start` 已自动处理（检测到不在 MENU 会先调 `menu` 再开局）。
如果手动调用其它客户端，需要先：

```bash
python3 tools/mech.py menu
```

### `simulate` 返回的分数明显偏低 / 都是整齐的整数

怀疑 `cardarea` 没传。见 [lessons.md 的坑 1](lessons.md#坑-1eval_card-的-cardarea-身份比较)。

验证方法：打一手有 Odd Todd / Scholar / Photograph 这类逐张计分小丑的牌，
比对 `simulate` 预测分与实际结算分。偏差应在 0-5%（随机类小丑除外）。

### 礼包打不开 / `buy` 买礼包失败

`buy` 有三个独立参数：`card` / `voucher` / `pack`。买礼包要用 `buy pack N`。

### 礼包内容的 state 名不对

打开礼包时 state 是 `SMODS_BOOSTER_OPENED`，不是 `BUFFOON_PACK` 之类。
`mech.py` 已兼容（匹配 `"BOOSTER_OPENED" in state`）。
