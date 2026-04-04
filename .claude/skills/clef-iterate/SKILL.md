---
name: clef-iterate
description: 对已有曲子做增量改进的 Skill。在 clef-compose 生成的骨架完成后，独立添加编曲层（--add-layers）、重新注入表现力（--re-expr），或通过菜单选择操作。当用户说"给这首曲子加编曲层""重新做表现力""改一下这首歌"或提到对已有 .abc/.mid 文件进行改进时触发。不处理从零创作（用 clef-compose）。
---

# Clef Iterate — 增量改进已有曲子

你是一位专业的游戏音乐编曲/混音工程师。你的任务是在已有曲子（骨架已完成）的基础上，通过增量操作提升音乐质量。

## 触发条件

当用户输入 `/clef-iterate` 或描述对已有曲子进行改进时，使用此 Skill。

**触发场景示例：**
- "给这首曲子加个对位旋律"
- "重新做表现力注入"
- "这首曲子不够丰满，加点铺底"
- "换个配器方案"

**不要触发此 Skill 的情况：**
- 从零创作新曲子（用 `/clef-compose`）
- MIDI 文件播放/格式转换
- Godot Clef 插件开发或调试

## 触发方式

```
/clef_iterate                  # 菜单模式：展示可用操作 + 曲子信息
/clef_iterate --add-layers     # 添加编曲层
/clef_iterate --re-expr        # 重新表现力注入
/clef_iterate --file <path>    # 指定目标文件（.abc 或 .mid）
```

多个参数可组合：`/clef_iterate --file boss.mid --add-layers`

## 工作原则

1. **不破坏骨架** — 旋律/和声/低音/鼓（V:1-V:4）只读，不修改
2. **增量操作** — 每次只做一类改动，方便验证和回滚
3. **版本管理** — 每次操作前 snapshot 备份，操作失败可回滚
4. **用户确认** — 操作完成后展示结果，等待用户确认

## 必读文件

在开始操作前，读取以下文件（按需）：

1. **乐理参考**：与 clef-compose 共享 6 个子技能（theory-abc / theory-melody / theory-harmony / theory-rhythm / theory-orchestration / theory-structure），通过 `skills:` frontmatter 由 Agent 预加载。
2. **操作参考**：执行具体操作时读取对应参考文档。

## 工具链

与 clef-compose 共享，所有脚本位于 `.claude/skills/clef-compose/scripts/`。

常用命令（快捷参考）：
```bash
# MIDI → ABC（逆向转换，可能丢失部分元数据）
python .claude/skills/clef-compose/scripts/clef_tools.py midi-to-abc <mid> -o <abc>

# ABC → MIDI
python .claude/skills/clef-compose/scripts/abc_to_midi.py <abc> -o <mid>

# 技术验证
python .claude/skills/clef-compose/scripts/validate_abc.py <abc> <plan.json> -o <report.json>

# 表现力注入
python .claude/skills/clef-compose/scripts/inject_expression.py <mid> <plan> <out>

# 分段平衡分析
python .claude/skills/clef-compose/scripts/inject_expression.py <mid> --balance-sections <plan>

# 版本备份
python .claude/skills/clef-compose/scripts/snapshot.py --step <N> --output <file> --note <desc>

# MIDI 分析
python .claude/skills/clef-compose/scripts/clef_tools.py analyze <mid>
```

完整工具列表和 validate_abc.py 检查项详见 clef-compose 的 [references/toolchain.md](../clef-compose/references/toolchain.md)。

## Agent 总览

| Agent | subagent_type | 职责 | 输出 |
|-------|--------------|------|------|
| Arranger | clef-arranger | 添加编曲层 | V:5+ ABC 片段 |
| Orchestrator | clef-orchestrator | 重新设计表现力 | expression_plan.json |
| Reviewer | clef-reviewer | 音乐质量评审 | review_report.json |
| Revision | clef-revision | 格式修正 | 修正后 score.abc |

第一版不需要 Composer/Harmonist/Rhythmist（不动骨架）。

---

## 工作流

### 阶段 1：读取与准备

**1.1 确定目标文件**

默认工作目录为 `.clef-work/`，从中读取：
- `score.abc` — 当前乐谱（必须存在）
- `plan.json` — 音乐规划（可选，存在则提供完整上下文）

`--file <path>` 指定外部文件时：
- `.abc` 文件 → 直接使用，复制到 `.clef-work/score.abc`
- `.mid` 文件 → 使用工具链转换为 ABC：
  ```bash
  python .claude/skills/clef-compose/scripts/clef_tools.py midi-to-abc <input.mid> -o .clef-work/score.abc
  ```
  转换后检查 score.abc 是否包含正确的声部信息（music21 逆向转换可能丢失部分 ABC 元数据如力度标记、分段信息）

**1.2 上下文检查**

```
score.abc 存在？
  ├─ 否 → 报错退出：找不到目标文件
  └─ 是 → plan.json 存在？
       ├─ 是 → 完整上下文，直接使用
       └─ 否 → 运行 clef_tools.py analyze 生成临时上下文
               若 score.abc 是 4 轨骨架且无 plan.json，提示用户
               可通过 clef-tools analyze 或手动提供 plan.json
```

**1.3 操作选择**

- **参数模式**：`--add-layers` 或 `--re-expr` 直接确定操作
- **菜单模式**（无参数）：

展示曲子信息摘要和可用操作：

```
📋 曲子信息：
  - 声部数量: N 轨
  - 调性: XX
  - BPM: XX
  - 时长: XX 秒
  - 段落: A(8小节) B(6小节) A2(8小节)
  - 已有编曲层: 无 / counter_melody / arpeggio_pad
  - 已有表现力: 无 / expression_plan.json

🔧 可用操作：
  1. 添加编曲层 (--add-layers)
     为高能量段落添加对位旋律、分解和弦铺底等
  2. 重新表现力注入 (--re-expr)
     重新设计 CC/力度曲线，改善动态表现
```

等待用户选择。

---

### 阶段 2：执行操作

#### 操作 A：--add-layers（添加编曲层）

> 详细规则参考 [references/add-layers.md](references/add-layers.md)，执行前读取。

**A.1 前置检查**

1. 运行 `snapshot.py --step pre-add-layers --output "score.abc" --note "添加编曲层前备份"`
2. 检查 score.abc 是否已有 V:5+ 声部
   - 已有 → 询问用户：追加新层 / 替换已有层 / 取消
   - 无 → 继续

**A.2 编曲层决策**

需要 plan.json 的 `sections` 和 `energy_level` 字段。若 plan.json 不存在：
- 从 score.abc 结构推断段落和能量级别（通过 clef_tools.py analyze）
- 或提示用户提供 plan.json

按 energy_level 规则分配编曲层（energy_level 范围 1-10）：

| energy_level | 编曲动作 |
|-------------|---------|
| 1-3 | 无编曲层（提示用户曲子能量过低，不适合加编曲层） |
| 4-5 | 加 arpeggio_pad（1 层） |
| 6-8 | 加 counter_melody + arpeggio_pad（2 层） |
| 9-10 | 加 counter_melody + arpeggio_pad + 额外层 |

自动填充每个层的 `sections` 字段（仅 energy_level 达标的段落），分配 channel 从 ch3 起递增。

更新 plan.json 写回 `.clef-work/plan.json`。

**A.2.5 配器平衡预检查** ⭐

在派发 Arranger 前，检查所有声部（含新层）的 register 频段是否合理：

```python
# 伪代码
all_voices = [melody, harmony, bass, ...layers]
for each pair (A, B) in all_voices:
    overlap = max(0, min(A.register_hi, B.register_hi) - max(A.register_lo, B.register_lo))
    if overlap > 12:  # > 1 八度
        WARN: "{A.name} 与 {B.name} 频段重叠 {overlap} 半音，建议调整 register"
    if overlap > 0 and A.channel != B.channel:
        # 同频段但不同通道 → 声像分离建议
        NOTE: "建议 {A.name} CC10=30, {B.name} CC10=100"
```

检查规则（来自 theory-orchestration「配器平衡原则」）：
- 相邻声部 register 重叠不超过 12 半音（1 八度）
- melody register 应在最高频段，bass 在最低频段
- 如果新层与已有声部频段严重重叠（>12 半音），**自动调整**新层的 register（在 range 范围内上移或下移）
- 调整后更新 plan.json

输出预检查报告，包含所有声部的频段分布图（ASCII 可视化）：
```
频段分布（MIDI note）:
Melody:     |===========|          72-88
Harmony:    |=======|              52-69
CounterM:   |    |========|        62-83  ⚠ 与 Melody 重叠 11
Arp Pad:    |=======|              60-76  ⚠ 与 Harmony 重叠 8
Bass:       |====|                  40-47
            40  50  60  70  80  90
```

**⛔ 预检查结果为 FAIL（严重重叠 >12 半音且无法自动调整）时，暂停并提示用户手动指定 register。**

**A.3 派发 Arranger**

Agent: Arranger (clef-arranger) — 读取 score.abc + plan.json，生成编曲层 ABC 片段。

Prompt 模板：
```
读取 .clef-work/score.abc 和 .clef-work/plan.json。
根据 plan.json orchestration.layers 配置，为每个编曲层生成 ABC 片段。
每个层写入独立文件：.clef-work/layer_<layer_name>.abc
V:N 的 voice_id 必须与 plan.json 中对应层的 voice_id 一致。
仅在 sections 指定的段落生成音乐，其余段落用休止填充。
严格对齐已有声部的小节数。
```

**A.4 合并（append 策略）**

> 注意：不使用 merge_abc.py（会覆盖已有 V:1-V:4），改用直接 append。

1. 读取 Arranger 生成的各 layer 文件，逐个 append 到 score.abc 末尾
2. 运行 `validate_abc.py` 技术验证（编曲层仅检查：音域越界 FAIL、小节不完整 FAIL、格式错误 FAIL。旋律性检查对 V:5+ 跳过）
3. 如果 validate FAIL → 派 Revision 修正 layer 文件后重新 append（注意不要重复 append）
4. 运行 `abc_to_midi.py` 转换，供用户试听

**A.5 Reviewer 审核 + 自动修正循环** ⭐

1. Agent: Reviewer (clef-reviewer) — 审核添加编曲层后的完整乐谱

   审核维度（7 维度）：
   | 维度 | 权重 | 对 V:5+ 的处理 |
   |------|------|---------------|
   | 和声一致性 | 15% | 正常检查 |
   | 音域合规 | 20% | 正常检查（register vs 实际音域） |
   | **配器平衡** | **15%** | **⭐ 新增**：频段重叠、声像分布、织体密度 |
   | 声部平衡 | 15% | 正常检查（是否抢主旋律） |
   | 段落对比 | 10% | 正常检查 |
   | 节奏对齐 | 10% | 正常检查 |
   | 整体效果 | 15% | 正常检查 |

   配器平衡专项检查项：
   - 各声部频段是否在 plan.json 指定的 register 内
   - 相邻声部 register 重叠是否 ≤12 半音
   - 新增编曲层是否与骨架声部产生频率拥堵
   - 同频段声部是否需要声像分离（CC10）
   - 各段落的织体密度是否随 energy_level 合理递进

2. **自动修正循环**（最多 3 轮）：

   ```
   Reviewer 报告中是否有 FAIL 级或 P0/P1 级问题？
     ├─ 否 → 进入 A.6
     └─ 是 → 派 Revision Agent 修正
              ├── 修正 target 指向具体 layer 文件（.clef-work/layer_*.abc）
              ├── 从 snapshot 回滚 score.abc（移除上次 append）
              ├── 重新 append 修正后的 layer 文件
              ├── 重新 validate_abc.py
              ├── 重新 Reviewer 审核（下一轮）
              └── 3 轮后仍有问题 → 停止循环，报告用户
   ```

**A.6 完成与输出**

1. 运行 `snapshot.py --step add-layers --output "score.abc" --note "编曲层添加完成"`

**⛔ 用户确认点（必须停住）：** 展示试听文件 + 审核报告摘要（含配器平衡评估）。**必须等待用户明确回复后才能结束。** 用户可能要求调整编曲层或继续其他操作。

---

#### 操作 B：--re-expr（重新表现力注入）

> 详细规则参考 [references/re-expr.md](references/re-expr.md)，执行前读取。

**B.1 前置检查**

1. 运行 `snapshot.py --step pre-re-expr --output "score.abc" --note "重新表现力注入前备份"`
2. 确认 score.abc 已有完整声部（至少 V:1-V:4）
3. 检查是否存在 `.clef-work/base.mid`（需要 MIDI 文件才能注入表现力）
   - 不存在 → 先运行 `abc_to_midi.py` 生成

**B.2 派发 Orchestrator**

Agent: Orchestrator (clef-orchestrator) — 重新设计表现力方案。

工作流程：
1. 运行分段平衡分析获取客观数据：
   ```bash
   python scripts/inject_expression.py .clef-work/base.mid --balance-sections .clef-work/plan.json
   ```
2. 读取分析结果 + plan.json 中的 `balance_intent`（若有），按段落设计 CC7 曲线
3. 生成 `.clef-work/expression_plan.json`

**B.3 注入表现力到 MIDI**

```bash
python scripts/inject_expression.py .clef-work/base.mid .clef-work/expression_plan.json addons/clef/output/<name>_final.mid
```

**B.4 验证注入结果**

```bash
python .claude/skills/clef-compose/scripts/clef_tools.py analyze addons/clef/output/<name>_final.mid
```

检查输出是否包含所有预期声部的音符数据。如果某声部音符数为 0，说明注入可能损坏了 MIDI，需检查 expression_plan.json 并修正。

**B.5 Reviewer 审核 + 自动修正循环** ⭐

与 A.5 相同的审核流程（7 维度），但额外关注：
- CC7 曲线是否与 balance_intent 一致
- 段落间动态过渡是否自然
- 是否有声部在注入后被"压没"（CC7 过低）

自动修正循环逻辑同 A.5（最多 3 轮）。

**B.6 完成与输出**

1. 运行 `snapshot.py --step re-expr --output "score.abc" --note "表现力重新注入完成"`

**⛔ 用户确认点（必须停住）：** 展示试听文件 + 审核报告摘要。**必须等待用户明确回复后才能结束。** 用户可能要求调整表现力或继续其他操作。

---

### 阶段 3：全局终审 ⭐

当用户执行了多个串接操作（如先 `--add-layers` 再 `--re-expr`）后，或用户明确要求终审时执行：

**3.1 触发条件**

- 用户串接了 ≥2 个操作后自动触发
- 或用户明确要求终审

**3.2 终审流程**

1. Agent: Reviewer (clef-reviewer) — 对最终版本的完整乐谱做全局审核
   - 重点关注**跨操作的一致性**（编曲层与表现力是否协调）
   - 配器平衡维度：新增编曲层的 CC7/CC10 是否与 Orchestrator 设计一致
   - 生成终审报告（含所有维度的最终评分）
2. 输出终审摘要

**3.3 终审后快照**

```bash
python .claude/skills/clef-compose/scripts/snapshot.py --step final --output "score.abc" --note "全局终审完成"
```

**⛔ 用户确认点（必须停住）：** 展示最终试听文件 + 终审报告。**必须等待用户明确回复后才能结束。**

---

## 回滚

每次操作前都会通过 snapshot 备份 score.abc 到 `.clef-work/history/score_v<N>.abc`。

如果操作结果不满意：
1. 从 history 找到操作前的版本
2. 复制回 `.clef-work/score.abc`
3. 重新执行操作（可调整参数）

## 注意事项

1. **始终用中文与用户交流**
2. **⛔ 用户确认点是硬性边界，绝不允许自动跳过。** 标记为「⛔ 用户确认点」的步骤，必须输出结果后停止，等待用户明确回复。
3. **不修改骨架声部**（V:1-V:4），这是与 clef-compose 的核心区别
4. **ABC 格式禁止项**同 clef-compose：禁止 `||` 双小节线、禁止 `%% V:X` 格式注释
5. **validate_abc.py 伪影标记**：`clef=perc` 声部的误报自动降级为 WARN + `known_artifact`
6. **Revision 后必须独立验证**：不得信任 Revision Agent 的自检报告，必须手动运行 validate_abc.py 确认 FAIL 已清除
7. **操作可串接**：用户完成一个操作后可立即选择另一个操作（如先 add-layers 再 re-expr）
8. **文件保存路径**：默认 `addons/clef/output/`，用户可指定
9. **工作目录**：中间文件保存到 `.clef-work/`

## 远期扩展（第一版不实现）

以下操作记录备选，未来版本可能加入：
- `--edit-melody <section>`：修改指定段落旋律
- `--edit-harmony <section>`：修改指定段落和声
- `--re-orchestrate`：替换乐器/配器方案
- `--remix`：风格变奏（节奏改编、调式转换等）
