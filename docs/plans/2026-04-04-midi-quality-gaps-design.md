# MIDI 质量差距分析与改进设计

日期：2026-04-04
来源：对比生成的 MIDI（DungeonExploration_final.mid、英雄觉醒 Boss Battle_final.mid）与参考曲（BossBattle.mid、HesaPirate.mid、Titantic.mid）的结构分析。

## 对比数据摘要

| 指标 | 我们（平均） | 参考曲（平均） | 差距 |
|------|-------------|---------------|------|
| 总音符数 | 133-761 | 1,255-11,656 | 5-15x |
| 轨道数 | 5 | 3-19 | 结构固定 |
| Velocity 均值 | 99-108 | 82-110 | 偏高 |
| Velocity 标准差 | 11-13 | 0-12 | 动态不足 |
| Velocity 范围 | [80,127] | [50,110] | 下限太高 |
| 平均时值(ticks) | 353-834 | 120 | 3-7x 偏长 |
| 音域跨度(半音) | 45-47 | 58-85 | 偏窄 |
| 独立音高数 | 23-30 | 35-66 | 材料单一 |

## 改进分层

### 第一层：纯 Prompt 修改（零代码改动）

#### 1.1 力度动态 — Composer/Harmonist/Rhythmist prompt

**问题**：三个创作 Agent 对 velocity 零提及，力度只在 Orchestrator 阶段通过 CC7 处理。ABC 支持 `!pp!` `!p!` `!mp!` `!mf!` `!f!` `!ff!` 标记，可被 abc_to_midi.py 转为 MIDI velocity。

**改动**：

- **Composer** — 约束部分追加：
  > - **动态标记**：每个段落至少使用 2 种力度级别（如 `!mf!` 段落主体 + `!ff!` 高潮点）。力度变化配合乐句起伏：乐句上行渐强(`!mf!`→`!f!`→`!ff!`)，乐句下行渐弱。段落开头默认 `!mf!`，避免全曲维持同一力度。至少出现一次 `!p!` 或 `!pp!` 的弱奏段落作为对比。

- **Harmonist** — 追加简化版：
  > - **动态标记**：使用 `!mp!`-`!mf!` 范围，力度低于旋律声部。段落之间可有力度对比但幅度小于旋律。

- **Rhythmist** — 追加简化版：
  > - **动态标记**：低音使用 `!mf!`-`!f!`，鼓组不加力度标记（由 Orchestrator CC7 控制）。

**目标**：velocity 均值 80-90，标准差 20+，范围 [50,127]。

#### 1.2 节奏丰富度 — Composer prompt

**问题**：已有"至少使用 3 种不同时值"但太机械，且没有关注整体效果。

**改动**：将现有约束替换为：

> - **节奏多样性**：节奏服务于乐句表达——乐句开头用短促音型建立动机，发展段用级进+节奏加密制造推进感，高潮前用加速（缩短时值）积累张力，段落结尾用长音或休止释放。段落之间必须有可感知的节奏对比（A 段疏 vs B 段密，或反过来）。避免全曲维持在相同的"音符密度感"。

**目标**：平均时值降至 200 ticks 以下，段落间有明显节奏对比。

---

### 第二层：Prompt + Plan.json 设计修改

#### 2.1 音高范围 — plan.json 默认值 + Composer 约束

**问题**：Composer 写死"控制在 1.5 个八度内"，plan.json 示例 melody register 只有 1 八度。

**改动**：

- **Plan 层**：plan.json 示例和 Step 0 引导中，默认 register 范围放宽至 1.5-2 八度。Step 0 生成 plan.json 时加说明：register 不应过于收窄，给旋律足够的展开空间。
- **Prompt 层**：Composer 的"1.5 个八度"改为：
  > - 音域：控制在 plan.json register 范围内（通常 1.5-2 个八度）。段落过渡处可做八度跳转（B 段开头跳高/跳低八度），但需立即级进收回。

**目标**：独立音高数 35+，音域跨度 55+ 半音。

#### 2.2 音符密度 — Plan 参数 + Prompt 引导

**问题**：DungeonExp 整首 133 音符（~4 notes/bar），参考曲旋律轨 17 notes/bar。

**改动**：

- **Plan 层**：plan.json sections 新增可选字段 `density_hint`：
  ```json
  {"id": "B", "name": "高潮", "measures": 8, "energy_level": 5, "density_hint": "high"}
  ```
  值：`"sparse"` / `"normal"` / `"high"` / `"dense"`，默认 `"normal"`。

- **Prompt 层**：Composer 约束追加：
  > - **音符密度**：参考 plan.json 各段的 `energy_level` 和 `density_hint`。sparse 段可留白呼吸（2-4 notes/bar），normal 段保持流畅（6-10 notes/bar），high/dense 段用经过音、装饰音、分解和弦填充（12-16+ notes/bar）。避免全曲统一密度。

**目标**：总音符数 1000+，段落间有疏密对比。

---

### 第三层：工作流级别 — 引入编曲（Arrangement）环节

#### 3.0 问题诊断

真实音乐制作流程：
```
作曲（旋律+和弦骨架）→ 编曲（Arrangement）→ 演奏表现力
```

当前系统跳过了编曲环节。Orchestrator 只做 CC/expression，不做编曲决策（如旋律 doubling、对位、内声部填充、配器层次）。

#### 3.1 方案：Step 2.5 编曲扩展（当前采用）

在 Step 2a（骨架创作）之后、Step 3（Orchestrator）之前，新增 **Step 2.5 编曲扩展**：

1. SKILL.md 主流程根据 plan.json 的 orchestration 和各段 energy_level，决定需要添加哪些编曲层
2. **复用现有 Composer/Harmonist Agent**，但派发时指定不同的目标声部号（V:5、V:6...）和编曲指令
3. merge_abc.py / abc_to_midi.py / validate_abc.py 通用化以支持 V:N（不硬编码 V:1-V:4）

**编曲层决策规则**（由 SKILL.md 主流程执行）：

| energy_level | 编曲动作 |
|-------------|---------|
| 1-2 | 仅骨架（4 轨），不加层 |
| 3 | 可选加 1 层（arpeggio pad 或 counter-melody） |
| 4-5 | 加 2+ 层（string doubling + counter-melody + arpeggio） |

**需要改动的文件**：
- `SKILL.md` — 新增 Step 2.5 流程
- `abc_to_midi.py` — 通用化 V:N 解析（如尚未支持）
- `merge_abc.py` — 支持合并 5+ 声部
- `validate_abc.py` — 对 V:5+ 做宽松验证
- `inject_expression.py` — 对新通道应用 CC 策略
- `plan.json schema` — orchestration 新增可选 layers 定义

#### 3.2 远期方案：独立 Arranger Agent（记录备选）

新增 `clef-arranger` Agent，专门负责编曲决策和生成。与当前方案的区别：

- 编曲决策由 Agent 自主判断，而非 SKILL.md 主流程硬编码
- Agent 有自己的 prompt，包含编曲技法（doubling、counter-melody、voicing spread 等）
- 更灵活但维护成本更高（多一个 agent prompt）

当方案 2.5 效果不足时再考虑升级到此方案。

---

### 第四层：旋律发展策略（Prompt + Plan）

#### 4.0 问题诊断

对现有 5 首输出曲目的听众体验诊断发现两个全局问题：
- **重复（ALL SEVERE）**：前后半段音高重叠 78%-93%
- **记不住（2 SEVERE, 3 WARN）**：Top3 音高占比 40%-87%

根源：段落间旋律缺乏变化和发展。Composer 只被告知"写旋律"，不知道每段应该与前后段是什么关系。

#### 4.1 方案：plan.json melody_strategy + Composer 技法约束

**Plan 层**：plan.json sections 新增 `melody_strategy` 字段，Step 1a 根据歌曲形式自动分配：

| 歌曲形式 | A 段 | B 段 | C 段 | 尾声 |
|---------|------|------|------|------|
| ABA | `new` | `development` | `recap` | — |
| ABCB | `new` | `variation` | `sequence` | `recap` |

可选值：`"new"` / `"variation"` / `"sequence"` / `"development"` / `"recap"` / `"climax"`

**Prompt 层**：Composer 的旧"动机发展"约束（"2种手法"）替换为硬约束，每条 strategy 有具体执行方法：
- `variation`：变节奏/变音区/加装饰音
- `sequence`：音阶级进上移/下移 2-3 次
- `development`：动机碎片化 + 不同音区交替 + 逐步加长
- `recap`：原样/轻微加花重现 A 段动机
- `climax`：组合之前动机片段在最高点汇合
- 禁止在非 `new` 段原样重复上一段旋律

---

## 实施优先级

| 优先级 | 改动 | 层级 | 改动文件 |
|--------|------|------|---------|
| P0 | 力度动态 | Prompt | clef-composer.md, clef-harmonist.md, clef-rhythmist.md |
| P0 | 节奏丰富度 | Prompt | clef-composer.md |
| P1 | 音高范围 | Prompt+Plan | clef-composer.md, SKILL.md（plan 示例） |
| P1 | 音符密度 | Prompt+Plan | clef-composer.md, SKILL.md（plan schema） |
| P1 | 旋律发展策略 | Prompt+Plan | clef-composer.md, SKILL.md（plan schema + 分配规则） |
| P2 | 编曲扩展 Step 2.5 | 工作流 | SKILL.md, abc_to_midi.py, merge_abc.py, validate_abc.py |
| P3 | 独立 Arranger Agent | 工作流 | 新增 clef-arranger.md（备选） |
