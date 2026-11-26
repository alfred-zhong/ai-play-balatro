# ai-play-balatro

让 AI 自己玩 Balatro（小丑牌）。

设计核心：**机械层负责算，AI 负责决策。**

- mod 把游戏自己的计分函数暴露成 API → 分数是精确的，不是估的
- AI 每一步读局面、自己判断打什么/弃什么/买什么
- 脚本里**没有任何策略规则**，避免手写规则带来的静默 bug

## 实测成绩

| 版本 | 最好成绩 |
|---|---|
| 手写规则机器人 | 底注 3 Boss |
| AI 全程决策 | **底注 4** |

标准模式共 8 个底注。瓶颈是商店抽不到 ×倍率小丑牌，详见 [docs/lessons.md](docs/lessons.md)。

## 它长什么样

AI 每步调用一条命令拿到完整局面 + 精确组合排名：

```
$ python3 tools/mech.py look
state=SELECTING_HAND ante=3 money=$16 chips=0 hands=3 discards=2
blind[boss]=The Wheel need=4000 effect=抽到的牌会是背面朝上
jokers 5/6: j_sock_and_buskin:重新触发所有打出的人头牌 | j_hiker:... | ...
hand: [0]AD [1]TS [2]9S [3]7S [4]7D [5]6S [6]5H [7]4S
leveled hands: Flush=Lv3(65x8) Straight=Lv2(60x7)
----- BEST COMBOS (exact, game scorer) -----
    2840  Flush            65x8.0 cards=[1, 2, 3, 5, 7]
    1260  Straight         60x7.0 cards=[1, 2, 3, 5, 7]
in_top_combos: {1: 12, 2: 11, 3: 10, 5: 9, 7: 8, ...}
```

AI 看到这些，自己决定出哪手、要不要先弃牌。

## 目录

```
tools/
  mech.py        机械工具箱：取状态、精确算分、执行动作。零策略
  restart.sh     可靠重启游戏（处理端口 TIME_WAIT 抢占）
  extract-source.sh  按需解包游戏 Lua 源码（读计分逻辑用，不入库）
mods/
  simulate.lua   自建端点：用游戏原生计分器穷举所有 5 张组合
  probe.lua      自建端点：调试用，返回 GAMESPEED/状态等内部值
docs/
  install.md     从零配置：Lovely + Steamodded + balatrobot + mod
  strategy.md    Balatro 攻略：×倍率、牌型专精、经济、Boss 应对
  lessons.md     迭代经验总结：踩过的坑与关键结论
archive/         早期三版规则机器人，仅作历史参考，不维护
```

## 快速开始

```bash
# 1. 装好 mod（详见 docs/install.md）

# 2. 启动游戏（会同时起 API）
bash tools/restart.sh

# 3. 开一局
python3 tools/mech.py start BLACK WHITE

# 4. 看局面
python3 tools/mech.py look
```

然后就可以让 AI 接管了。

## 给 AI 的提示词

```
你要亲自打完局 Balatro，目标是尽可能通关（8 个底注）。

先读 docs/strategy.md。

工具箱在 tools/mech.py，用 python3 tools/mech.py <命令>：
- look [n]                  完整局面 + 精确组合排名（每步都用这个）
- play 0,1,2,3,4            打出这些 0 基索引
- discard 0,1,2             弃掉这些索引
- select / skip             选盲注 / 跳过盲注
- buy N / buy pack N        买商店卡 / 买礼包
- pack N / pack skip        取礼包第 N 张 / 跳过礼包
- use N [targets]           用消耗品
- sell N                    卖小丑
- rearrange 1,0,2,3         重排小丑顺序（+倍率左，×倍率右）
- reroll / next / cashout
- start BLACK WHITE         开新局

脚本里没有任何策略，所有决策都是你的。

每步 look → 判断 → 执行一条命令 → 再 look 确认。不要批量执行。

死掉就 start BLACK WHITE 重开。禁止用存档读档改变已发生的失败。
```

更完整的版本见 [docs/playing.md](docs/playing.md)。

## 注意

- 只在 macOS + Apple Silicon + Steam 版实测过
- 用 mod 玩游戏，**Steam 成就可能受影响**（实际上 Steamodded 一般会禁用成就，介意的话别用主账号）
- 这是个人研究项目，不是完整的 Balatro AI 框架
