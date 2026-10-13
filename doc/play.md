# 对弈说明：人机对打与随机对打（接入 P2）

本文说明如何用已导出的证明 DAG / merge+Σ 证书做 **P1=证书** 的对弈，以及如何把任意 **P2 策略**接入同一接口。

相关实现：`scripts/play_game.py`、`scripts/d11_play.sh`、`scripts/d11_interact.sh`、`scripts/auto_play.py`（本仓库为阶段一开源包）。  
证书产物与检阅约定见 `artifacts/VERIFY.md`；\(n\ge18\) 的 Σ 读法见 `doc/sigma_spec.md`。

---

## 1. 前置条件

```bash
cd centre_embedding_sag_player   # repo root
# 阶段一仅附带预编译 d11py（Linux x86_64；Python 3.11 或 3.13）
ls build/d11py.cpython-*-x86_64-linux-gnu.so

cd scripts
./d11_play.sh --list    # 列出可用有限 n 与 merge 证书
```

| 盘面 | P1 证书来源 |
|------|-------------|
| \(6\le n<18\) | `artifacts/finite/nXX/proof.dag`（`DagPlayer`） |
| \(n\ge18\) | `artifacts/embed/merge/proof.dag` + 在线 Σ（`EmbedPlayer`） |

本仓库已附带有限 \(n=6..17\) 与 merge 证书；布局见 `artifacts/VERIFY.md`。

工作目录建议：

```bash
cd scripts
# 或保证 PYTHONPATH 含 build/ 与 scripts/（wrapper 已设置）
```

---

## 2. 统一接口

双方都实现同一协议：给定只读 `GameView`，返回合法格子下标（row-major，`cell = r*n + c`）。

```python
# scripts/play_game.py（摘要）
class Player(Protocol):
    def choose(self, view: GameView) -> int: ...

@dataclass
class GameView:  # 只读
    n: int
    to_move: int          # 0=P1, 1=P2
    board: Sequence[int]  # 0 空, 1=P1, 2=P2
    legal: Sequence[int]
    history: Sequence[int]
```

CLI 用 `--p1` / `--p2` 指定策略字符串；批跑与人机共用同一套解析。

### 2.1 内置策略一览

| 规格 | 角色 | 行为 |
|------|------|------|
| `cert` | P1（默认） | 自动选有限 DAG 或 merge+Σ |
| `dag:PATH` | P1 | 指定有限盘 `proof.dag` |
| `embed:PATH` | P1 | 指定 merge DAG（要求 \(n\ge18\)） |
| `pruned-random` | P2（批跑默认） | 在 **sound-prune 后** 的应手里均匀随机（易留在证明树上） |
| `random` | P2 | 合法着均匀随机（**可能偏出**证明树） |
| `human` | 任一方 | 终端交互输入 |
| `script:PATH.py` | 任一方（常作 P2） | 加载模块中的 `choose(view) -> int` |

---

## 3. 人机对打（交互）

ASCII 棋盘，默认 **你 = P2（O）**，**证书 = P1（X）**。

```bash
cd scripts

./d11_interact.sh --n 6          # 有限证书
./d11_interact.sh --n 18         # merge+Σ（任意 n≥18 均可，如 19、25）
./d11_interact.sh --n 25

# 等价：
./d11_play.sh --n 6 --interactive
./d11_play.sh --n 18 -i
```

可选：

```bash
./d11_interact.sh --n 6 --side p1   # 你下 P1；P2 默认 pruned-random（非证书）
./d11_play.sh --n 6 -i --p1 cert --p2 human   # 显式指定
./d11_play.sh --n 6 -i --json                 # 终局再打一行 JSON
```

### 3.1 输入约定

提示符 `move>`：

| 输入 | 含义 |
|------|------|
| `行 列` | 如 `2 3` |
| `cell` | 扁平下标 `0 … n²-1` |
| `rXcY` | 如 `r2c3` |
| `legal` | 列出合法着 |
| `hist` | 着法历史 |
| `quit` | 退出 |

图例：`X`=P1，`O`=P2，`.`=空，`[ ]`=上一手。

\(n\ge18\) 时 P1 被限制在中心 \(6\times6\) 块 \(C\)；P2 可下全盘。

### 3.2 人机时的注意点

- **有限 \(n\)**：人若走出 DAG 未覆盖的剪枝外应手，`DagPlayer` 会 **fail-loud**（RuntimeError），这是检阅设计，不是棋规判负。
- **\(n\ge18\)**：实盘经 Σ 映成 merge 视图再查表；窗外子在未唯一钉死 Case-2 方之前走 default（→ token `z`）。偏树时可能回退 TW/default 读法，**该步不再保证「证书路径可检阅」**，但定理本身不变（见下节）。

---

## 4. 随机 / 批跑对打

### 4.1 单局（JSON 结果）

```bash
# 默认：P1=cert，P2=pruned-random
./d11_play.sh --n 6
./d11_play.sh --n 18 --seed 1

# 自由随机 P2（可能偏树）
./d11_play.sh --n 6 --p2 random --seed 2
./d11_play.sh --n 25 --p2 random
```

输出示例：

```json
{"n": 6, "p1": "cert", "p2": "pruned-random", "winner": 1, "reason": "square", "plies": 9, "history": [...]}
```

`winner`：`1`=P1，`2`=P2，`null`=未成方结束（如满盘 / max-plies）。

### 4.2 批量 auto-play

对所有已导出有限 \(n\)，以及 merge 代表盘 \(n=18\)（覆盖 \(n\ge18\) 读法）：

```bash
./run_auto_play.sh
./run_auto_play.sh --sizes 6,7,8 --games 5 --seed 1
./run_auto_play.sh --p2 random          # 压力：自由 P2
./run_auto_play.sh --skip-merge
```

摘要默认写到 `artifacts/auto_play_summary.json`。

**推荐检阅配置**：`--p2 pruned-random`，使 P2 应手落在 dump 时同一套 sound-prune 集合内，尽量不偏出证明树。

---

## 5. 接入自定义 P2 策略

### 5.1 脚本插件（最快）

写一个模块，导出：

```python
# my_p2.py
def choose(view) -> int:
    """view: GameView — 返回 view.legal 中的一个 cell。"""
    # 例：吃中心附近空点，否则任意合法
    n = view.n
    mid = n // 2
    scored = sorted(
        view.legal,
        key=lambda c: abs(c // n - mid) + abs(c % n - mid),
    )
    return scored[0]
```

接入：

```bash
./d11_play.sh --n 10 --p1 cert --p2 script:./my_p2.py
./d11_interact.sh --n 18   # 人机仍用 human；脚本用于批跑/单局
./d11_play.sh --n 18 --p2 script:/abs/path/my_p2.py --seed 0
```

人机 + 自定义 P2 不可同时占 P2 席；若要「人看脚本下」请自行在脚本里 `input`，或改 `--p2 human`。

### 5.2 进程内 Python API

```python
import sys
sys.path[:0] = ["../build", "."]

from play_game import (
    play, parse_player, EmbedPlayer, GameView, Player, CallablePlayer
)

class MyP2:
    def choose(self, view: GameView) -> int:
        return list(view.legal)[0]

n = 18
p1 = parse_player("cert", n, seed=0)          # EmbedPlayer
p2 = MyP2()
# 或: p2 = CallablePlayer(lambda v: list(v.legal)[0])

res = play(n, p1, p2, center_only_p1=isinstance(p1, EmbedPlayer))
print(res.winner, res.reason, res.history)
```

### 5.3 设计约束

1. **只通过 `Player.choose`**：不要改证书、不要在对弈路径里偷偷 `ProveP1`。
2. **必须返回当前 `view.legal` 中的格子**；非法着由 `play()` 判为对方胜（`illegal_move_by_*`）。
3. **\(n\ge18\)**：P1 只会在中心 \(C\) 落子；P2 策略可利用窗外着法（Σ 负责映到 merge 视图）。
4. **偏树行为**：自由策略（`random` / 强力启发式 / 人类乱下）可能使 DAG hash 未命中 → 异常退出。这表示「离开可检阅证书路径」，不自动改写为「P2 棋规胜利」。

---

## 6. 完备性与检阅（简要）

| 层面 | 含义 |
|------|------|
| **定理（\(n\ge18\)）** | merge 证书 + 正确 Σ ⇒ P1 必胜；最优下 P2 不能靠平局或取胜推翻定理 |
| **有限 \(n\) 证书** | 导出 DAG 上的 P1 策略对 **prune 后的 P2 应手** 完备；剪枝外着法可不在树上 |
| **推荐对打** | `p1=cert` + `p2=pruned-random`：尽量留在树上，适合复现与 CI |
| **人机 / `random` / 自定义** | 用于探索；偏树时 fail-loud 或（仅 Embed）TW/default 回退，回退步 **不再声称证书路径覆盖** |

人机与随机对打用于体验与路径校验；证书布局见 `artifacts/VERIFY.md`。完整证明导出流水线将在后续开源阶段放出。

---

## 7. 常用命令速查

```bash
cd scripts

# 有哪些证书
./d11_play.sh --list

# 人机（你是 P2）
./d11_interact.sh --n 6
./d11_interact.sh --n 25

# 单局随机（检阅向）
./d11_play.sh --n 6 --p2 pruned-random --seed 0

# 单局自由随机
./d11_play.sh --n 18 --p2 random --seed 1

# 自定义 P2
./d11_play.sh --n 10 --p2 script:./my_p2.py

# 批量
./run_auto_play.sh --games 3 --p2 pruned-random
```

---

## 8. 相关文件

| 路径 | 内容 |
|------|------|
| `scripts/play_game.py` | `Player` / `DagPlayer` / `EmbedPlayer` / CLI |
| `scripts/d11_play.sh` | 批跑 / 通用 wrapper |
| `scripts/d11_interact.sh` | `--interactive` 快捷入口 |
| `scripts/auto_play.py` | 多盘多局汇总 |
| `scripts/sigma.py` | \(n\ge18\) 在线 Σ |
| `doc/sigma_spec.md` | Σ 规则优先级 |
| `artifacts/VERIFY.md` | 第三方复现清单 |
