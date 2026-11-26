# 让 AI 打牌：操作手册

这份文档是给 AI（或你自己）用的操作说明。策略部分见 [strategy.md](strategy.md)。

---

## 工作方式

**每步：`look` → 判断 → 执行一条命令 → 再 `look` 确认。**

不要连续执行多条命令再看结果。游戏状态在动画中会变化，盲操作容易打空。

---

## 命令速查

所有命令都在项目根目录执行：

```bash
python3 tools/mech.py <命令>
```

### 观察

| 命令 | 说明 |
|---|---|
| `look [n]` | **最常用**。完整局面 + 精确组合排名（默认前 8） |
| `status` | 只看局面，不算分 |
| `sim [n]` | 只看组合排名 |
| `raw` | 完整原始 JSON（需要看细节字段时用） |
| `wait STATE...` | 阻塞等到指定状态 |

`look` 的输出包含：

```
state=SELECTING_HAND ante=3 money=$16 chips=0 hands=3 discards=2
blind[boss]=The Wheel need=4000 effect=抽到的牌会是背面朝上
jokers 5/6: j_sock_and_buskin:重新触发... | j_hiker:... 
consumables 1/2: [0]c_mercury
hand: [0]AD [1]TS [2]9S [3]7S [4]7D [5]6S [6]5H [7]4S
leveled hands: Flush=Lv3(65x8) Straight=Lv2(60x7)
----- BEST COMBOS (exact, game scorer) -----
    2840  Flush            65x8.0 cards=[1, 2, 3, 5, 7]
in_top_combos: {1: 12, 2: 11, ...}
```

关键字段：

- `chips` / `hands` / `discards` — 当前分 / 剩余出牌次数 / 剩余弃牌次数
- `blind[...] need=N effect=...` — 本盲注门槛和特效，**Boss 特效必须读**
- `jokers` — 小丑牌及其中文效果，**注意「当前为+X」这类成长累积值**
- `hand` — 手牌及索引，`play`/`discard` 用的就是这个索引
- `leveled hands` — 已升级的牌型（Lv1 的不显示）
- `BEST COMBOS` — **精确分数**，由游戏自己的计分函数算出，直接信
- `in_top_combos` — 每张手牌在前 N 名组合中出现的次数，用来判断哪张牌值得留

### 出牌 / 弃牌

| 命令 | 说明 |
|---|---|
| `play 0,1,2,3,4` | 打出这些 0 基索引 |
| `discard 0,1,2` | 弃掉这些索引 |

索引是 `hand:` 那一行里的方括号数字，**出牌/弃牌后索引会全部重排**，所以要重新 `look`。

### 盲注

| 命令 | 说明 |
|---|---|
| `select` | 选中当前盲注，进入出牌阶段 |
| `skip` | 跳过盲注，换取跳过标签（会失去本盲注奖励，慎重） |

### 商店

| 命令 | 说明 |
|---|---|
| `buy N` | 买商店第 N 张卡 |
| `buy pack N` | 买第 N 个礼包 |
| `buy voucher N` | 买第 N 个优惠券 |
| `pack N` | 从已打开的礼包中取第 N 张 |
| `pack skip` | 跳过礼包 |
| `reroll` | 重掷商店（花费递增） |
| `next` | 离开商店，进入下一盲注 |

**注意 `buy` 的三个参数是分开的**，买礼包必须用 `buy pack N`，用 `buy N` 只会买商店卡。

### 小丑 / 消耗品

| 命令 | 说明 |
|---|---|
| `sell N` | 卖掉第 N 张小丑 |
| `rearrange 1,0,2,3` | 重排小丑顺序（**+倍率放左，×倍率放右**） |
| `use N` | 使用第 N 张消耗品 |
| `use N 0,1,2` | 使用消耗品并指定目标手牌 |

星球牌（`c_pluto` / `c_mercury` / ...）**见到就用**，升级牌型永久生效。

### 流程

| 命令 | 说明 |
|---|---|
| `cashout` | 收取回合奖励 |
| `next` | 离开商店 |
| `menu` | 回主菜单 |
| `start DECK [STAKE]` | 开新局（自动处理回主菜单） |

牌组：`RED` `BLUE` `YELLOW` `GREEN` `BLACK` `MAGIC` `NEBULA` `GHOST`
`ABANDONED` `CHECKERED` `ZODIAC` `PAINTED` `ANAGLYPH` `PLASMA` `ERRATIC`

难度：`WHITE` `RED` `GREEN` `BLACK` `BLUE` `PURPLE` `ORANGE` `GOLD`

---

## 状态机

```
MENU
 └─ start → BLIND_SELECT
      └─ select ─┐
                 ├→ SELECTING_HAND ─(play/discard)→ SELECTING_HAND
                 │        └─(分数达标或手数用尽)→ ROUND_EVAL
                 └→ ROUND_EVAL
                      └─ cashout → SHOP
                           ├─ buy / reroll
                           └─ next → BLIND_SELECT（下一个盲注或下一底注）
                                └─(三个盲注打完)→ 底注 +1，回到 BLIND_SELECT
                                
SELECTING_HAND 中买礼包 → SMODS_BOOSTER_OPENED → pack N / pack skip → 回到原状态
任一盲注失败 → GAME_OVER → menu → start 重开
```

`GAME_OVER` 时脚本不会自动重开，需要显式 `start`。

---

## 决策要点（速查）

完整版见 [strategy.md](strategy.md)。

### 该不该弃牌

```
if 当前最高分 × 剩余手数 < 还差分:
    弃牌
else:
    直接打
```

还差分 = `need - chips`。

### 弃哪几张

- 保留 `in_top_combos` 里出现次数高的牌
- 丢掉孤张（除非是 High Card 流派）
- **弃满上限**（通常 5 张），弃 2 张是浪费

### 小丑牌优先级

**×倍率 > +倍率 > 加筹码**。底注 4 之后没有 ×倍率必死。

见到优先买：Blueprint、Brainstorm、Cavendish、Triboulet、Photograph、
Hologram、Constellation、Baron、The Duo/Trio/Family/Order/Tribe、
Bloodstone、Campfire、Obelisk、Sock and Buskin、Hanging Chad。

### 经济

$25 吃满利息（每 $1 利息，上限 $5）。但看到 ×倍率牌要舍得花光。

---

## 禁忌

1. **不要用存档读档改变已发生的失败。** `save` / `load` 只用于「让代码修改生效」，
   生效后必须从当前进度继续，不能回到更早的存档点。
2. **不要批量执行命令。** 每步 `look` 确认。
3. **不要凭记忆算分。** 用 `look` 的精确结果。
4. **不要忽略 Boss 特效。** `blind[boss] effect` 字段必读。

---

## 出问题时

| 现象 | 检查 |
|---|---|
| 命令全部 `Connection refused` | 游戏没起，或端口被占。`bash tools/restart.sh` |
| `simulate` 分数都是整齐整数 | 怀疑 `cardarea` 没传，见 [lessons.md](lessons.md) 坑 1 |
| `buy pack` 买不了 | 确认用的是 `buy pack N` 而不是 `buy N` |
| 礼包看不到内容 | 状态名应为 `SMODS_BOOSTER_OPENED`，`mech.py` 已兼容 |
| `start` 报状态错误 | `mech.py start` 会自动先 `menu`；手动调 API 时要自己先 `menu` |
