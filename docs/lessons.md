# 迭代经验总结

日期：2026-11-26
范围：Balatro 1.0.1o（Steam / Apple Silicon / macOS）+ Steamodded + balatrobot + LLM 决策

---

## 一、结论先行

| 问题 | 答案 |
|---|---|
| AI 能不能玩 Balatro？ | 能，实测稳定打到**底注 4**，能通过底注 3 的 Boss |
| 最快的接入方式？ | **mod + HTTP API**（`balatrobot`），毫秒级响应 |
| 截图 + 点击可行吗？ | **不可行**，见下方「坑 1」 |
| 最大瓶颈？ | 不是决策能力，是**商店抽不到 ×倍率小丑牌** |
| 最关键的工程问题？ | 手写计分估值必然失真，必须**调用游戏自己的计分函数** |

---

## 二、三次方案演进

### 方案 A：截图 + 像素点击 —— 失败，已废弃

Balatro 是 LÖVE/SDL 自绘，**没有可用的无障碍（AX）树**：整窗只有 14 个节点，卡牌和按钮全在纹理里。

结果：13 次点击只有 1 次生效，且坐标会随窗口位置/缩放在每一帧的动画里漂移。

**教训：对自绘游戏不要浪费时间在截图识图 + 坐标点击上。** 先查有没有 mod / 内存读取 / 官方 API 的路子。

### 方案 B：手写规则机器人 —— 部分成功（底注 3-4）

思路：Python 脚本读 gamestate，自己实现牌型判定 + 小丑牌估值，枚举 5 张组合取最高分。

三个实测出来的致命问题：

1. **小丑牌估值必然失真**
   - 手写「Spare Trousers 给 +2 倍率」这种规则，漏掉成长累积值（实际已 +12）
   - 实测预测 705 分，实际 1692 分，**偏差 2.4 倍**
   - 后果：判断「够分了」而不弃牌 → 该赌的时候不赌

2. **组合枚举写错了**（`rec(1, k)` 应为 `rec(1, 1)`）
   - C(8,5) 本该 56 种，只返回 8 种残缺组合
   - 所有分数都是错的，但脚本不报错，静默地打了一整局

3. **弃牌逻辑的边界 bug**
   - `keep` 集合意外包含了全部手牌 → 一张都没弃
   - 3 手只打 276 分输掉，但日志看起来「正常」
   - 修法：`should_discard = best_score * hands_left < remaining`

**教训：自己实现游戏规则的地方，一定有 bug，而且静默。要么调游戏原生函数，要么用真实结算分反推校准。**

### 方案 C：mod 原生算分 + LLM 决策 —— 当前方案

两条腿：

- **机械层**（`tools/mech.py`）：取状态、精确算分、执行动作。**零策略**。
- **决策层**（LLM）：每一步自己判断打什么、弃什么、买什么。

关键突破是 `mods/simulate.lua`：把每个 5 张组合喂给游戏自己的计分管线，得到**精确分数**而非估算。

实测验证：算出「两对 Q+2 = 88 分」，与游戏实际结算完全一致。

---

## 三、踩过的坑（按痛苦程度排序）

### 坑 1：`eval_card` 的 `cardarea` 身份比较

这是最隐蔽的一个。Balatro 的 `eval_card` 内部：

```lua
if context.cardarea == G.play then   -- 身份比较，不是字符串比较
```

在 mod 里从外部构造 context 传进去，**这个比较恒为假**，于是：

- 牌面筹码（`get_chip_bonus`）不算
- 倍率、幸运牌、钢铁牌全部不算
- 结果恒等于「基础筹码 × 基础倍率」，看起来像正常的低分，**毫无报错**

表现：所有组合都是 15 分、20 分这种「干净」的数字。

**正确做法**：绕开 `eval_card`，直接调 `card:get_chip_bonus()` / `get_chip_mult()` / `card:calculate_joker(ctx)`，并**手动传入 `cardarea = G.play`**（`calculate_joker` 需要它来判断逐张计分效果）。

**残留风险**：LLM 在会话末尾发现了这个 bug 并修了（`simulate.lua` 已加 `cardarea`），但**修复后没有实战验证**。下次接手第一件事应该是验证这个修复。

验证方法：打一手有 Odd Todd / Scholar / Photograph 这类逐张计分小丑的牌，比对 `simulate` 预测分与实际结算分。偏差应在 0-5% 内（随机类小丑如 Bloodstone 除外）。

### 坑 2：`BALATROBOT_FAST=1` 导致崩溃

```
game.lua:2610: attempt to perform arithmetic on field 'GAMESPEED' (a nil value)
```

FAST 模式把 GAMESPEED 强推 10，与其他时序冲突，**第一次出牌进入结算动画就崩**。

**解**：`BALATROBOT_FAST=0 BALATROBOT_GAMESPEED=4`。稳定，速度也够用（一步约 0.5 秒）。

### 坑 3：重启游戏时端口抢占

`pkill` 之后立刻重启，`12346` 端口处于 `TIME_WAIT`，新实例 `Failed to bind`，但进程还活着、日志看起来正常。

**解**：`tools/restart.sh` 已处理：

1. `pkill -9`
2. 轮询等待 `lsof -iTCP:12346` **和** `netstat | grep 127.0.0.1.12346` 都干净
3. 启动后等日志出现 `HTTP server listening`
4. 再用 `health` 接口确认真能响应
5. 最多重试 3 次

### 坑 4：`buy` 端点的参数是分开的

`buy` 有三个独立参数：`card`（商店卡）/ `voucher`（优惠券）/ `pack`（礼包）。

只实现 `card` 就会导致「买礼包永远失败」，而 LLM 会自己写 Python 直接调 RPC 绕过——**能绕过，但暴露工具不完备**。

`mech.py` 已支持：`buy N` / `buy pack N` / `buy voucher N`。

### 坑 5：礼包打开的状态名

礼包打开时的 state 不是 `BUFFOON_PACK` / `TAROT_PACK` 等，而是 **`SMODS_BOOSTER_OPENED`**。

`mech.py` 已改为匹配 `"BOOSTER_OPENED" in state`，兼容 Steamodded 的写法。

### 坑 6：`start` 端点只能在 MENU 状态调用

游戏进行中调 `start` 会报 `requires one of these states: MENU`。

**解**：先 `call("menu")` 回到主菜单，再 `start`。`mech.py start` 目前没自动做这一步，需要手动先 `menu`。

### 坑 7：LLM 用存档/读档规避失败

实测中 LLM 为了「让修复生效」用了 `save` → 重启 → `load`。

**这是合理的工程操作**（不重启 mod 不会重载），但**会让成绩失去说服力**——它相当于无限重试权。

下次要明确约定：**禁止用存档读档改变已发生的失败**。重启只为让代码改动生效时，必须从当前进度继续，不能回到更早的存档点。

---

## 四、Balatro 本身的关键机制（决策层必须知道）

### 计分公式

```
最终分 = (基础筹码 + Σ卡牌筹码 + Σ +筹码小丑) × (基础倍率 + Σ +倍率 + Σ -倍率) × Π ×倍率
```

**+倍率是线性叠加，×倍率是乘法叠加。** 这是最核心的认知：

- 底注 1-3：纯 +倍率能过
- 底注 4-5：**必须有一张 ×倍率**
- 底注 6+：需要两三张 ×倍率 + 高等级牌型

实测四局，AI 一次都没买到真正的 ×倍率牌，天花板就是底注 4-5。

### 小丑牌结算顺序

**从左到右**。所以 `+倍率` 放左侧、`×倍率` 放右侧，数值更大。

用 `mech.py rearrange 1,0,2,3` 调整。

### 经济

每回合剩 $1 吃 $1 利息，上限 $5 → **$25 吃满利息**。

但不要为了利息错过 ×倍率牌。宁可 $0 有 ×3 倍率。

### Boss 盲注

门槛高、效果阴间，且**每个 Boss 效果不同**（削弱某花色、强制出 5 张、弃牌减半等）。

`mech.py look` 的 `blind[boss] effect` 字段会写中文效果，`simulate` 算出的分数**已包含 debuff 判定**。

---

## 五、当前架构

```
┌─────────────────────────────────────────┐
│  LLM（决策层）                          │
│  - 读 look 输出                         │
│  - 判断打什么/弃什么/买什么              │
│  - 只需要会调用 mech.py 的命令          │
└──────────────┬──────────────────────────┘
               │ bash / opt/homebrew/bin/python3 mech.py ...
┌──────────────▼──────────────────────────┐
│  mech.py（机械层，零策略）              │
│  look / sim / play / discard / buy ...  │
└──────────────┬──────────────────────────┘
               │ JSON-RPC over HTTP :12346
┌──────────────▼──────────────────────────┐
│  balatrobot mod（游戏内）               │
│  + simulate.lua（精确算分，自建）       │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  Balatro（LÖVE 2D）                     │
└─────────────────────────────────────────┘
```

**设计原则**：机械层不写任何策略。所有「该怎么打」的判断都在 LLM 里。

理由：手写规则的 bug 是静默的（见方案 B 的三条），而 LLM 的判断是显式的、可讨论的、可纠正的。

---

## 六、下次迭代的优先级

按性价比排序：

1. **验证 `simulate.lua` 的 `cardarea` 修复**（最高优先级）
   打一手带 Odd Todd / Scholar / Photograph 的牌，比对预测分与实际分。
   不验证的话，后面所有「够不够分」的判断都不可信。

2. **给 `mech.py` 加商店价值评估**
   现在 `look` 只列出商店内容，靠 LLM 自己认。
   可以加一个 `joker_rank` 映射（S/A/B 级），直接标注哪些是 ×倍率牌。
   这不违反「机械层零策略」——它是**信息增强**，不是决策。

3. ~~加 `menu` 命令到 `mech.py`~~ （已完成：`start` 会自动先回主菜单）

4. **解决 ×倍率牌获取问题**
   四局都没抽到，可能是：
   - 随机性（商店池子大）
   - LLM 买牌优先级偏保守（总在买 $4-6 的便宜牌，没攒钱买 $8-10 的关键牌）
   值得统计一下：每局在商店停留多久、reroll 几次、平均买牌价格。

5. **考虑其它牌组**
   黑色牌组（每回合 +1 弃牌？实际是别的效果）不一定是最优。检查牌组效果，选一个和 ×倍率流派配合更好的。

---

## 七、环境与版本（复现用）

| 组件 | 版本 |
|---|---|
| 系统 | macOS，Apple Silicon |
| Balatro | 1.0.1o-FULL（Steam） |
| Lovely Injector | 0.10.0（arm64） |
| Steamodded | 26.1002.0 |
| balatrobot | v1.5.2 |

### 关键路径

```
游戏目录   ~/Library/Application Support/Steam/steamapps/common/Balatro/
mod 目录   ~/Library/Application Support/Balatro/Mods/
  ├── smods/        Steamodded
  ├── balatrobot/   balatrobot + 自建 simulate.lua
  └── lovely/
注入库     <游戏目录>/liblovely.dylib
启动脚本   <游戏目录>/run_lovely_macos.sh
```

### 启动命令

```bash
B="$HOME/Library/Application Support/Steam/steamapps/common/Balatro"
cd "$B" && BALATROBOT_FAST=0 BALATROBOT_GAMESPEED=4 BALATROBOT_AUDIO=0 ./run_lovely_macos.sh
```

约 14-20 秒后 API 在 `http://127.0.0.1:12346` 可用（JSON-RPC 2.0，POST 到 `/`）。

用 `tools/restart.sh` 更可靠。

---

## 八、给未来的自己

- **不要重走截图路线。**
- **不要手写计分规则。** 让游戏自己算。
- **每一步都 look 一次再决策**，不要连续执行多步不看结果。
- **弃牌是最高频的失误来源**：弃满 5 张，别只弃 2 张。
- **看到 `0 分` 或「干净到可疑的整数分数」，立刻怀疑算分管线有问题**（参见坑 1）。
- **别让 LLM 用存档读档刷成绩。**
