# 重新表现力注入（--re-expr）操作参考

## 概述

重新设计 MIDI 的表现力方案（CC7 音量、CC10 声像、CC91 混响、弯音、力度曲线），替换或优化之前的表现力注入结果。

## 前置条件

- `.clef-work/score.abc` 存在且包含完整声部（至少 V:1-V:4）
- `.clef-work/base.mid` 存在（若不存在，先从 score.abc 转换）
- `plan.json` 存在（至少包含 `sections` 数组）
  - 若 plan.json 不存在，表现力注入仍可执行，但段落级别的 CC 调整需要手动推断

## Orchestrator 工作流

### 步骤 1：分段平衡分析

获取客观数据作为 CC 设计依据：

```bash
python .claude/skills/clef-compose/scripts/inject_expression.py \
  .clef-work/base.mid --balance-sections .clef-work/plan.json
```

输出包含每段的音符密度、频率分布、能量概况等，Orchestrator 据此设计差异化的 CC 曲线。

### 步骤 2：读取已有 expression_plan.json（如存在）

如果 `.clef-work/expression_plan.json` 已存在，Orchestrator 应：
1. 读取当前方案
2. 对照平衡分析报告，识别问题段落（如某段 CC7 过高/过低导致声部不平衡）
3. 基于问题有针对性地调整，而非完全重写

### 步骤 3：生成新 expression_plan.json

Orchestrator 输出 `.clef-work/expression_plan.json`，格式参考 clef-orchestrator Agent 定义。

关键设计原则：
- **balance_intent 标签**（若有）：按 plan.json 段落的 balance_intent 设计 CC7 策略
- **段落差异化**：不同 energy_level 的段落应有明显不同的 CC7/力度水平
- **声部平衡**：主旋律段旋律 CC7 最高；全员推进段整体提升
- **渐变过渡**：段落之间 CC 值应有平滑过渡，避免突变

### 步骤 4：注入表现力

```bash
python .claude/skills/clef-compose/scripts/inject_expression.py \
  .clef-work/base.mid \
  .clef-work/expression_plan.json \
  addons/clef/output/<name>_final.mid
```

### 步骤 5：验证注入结果

```bash
python .claude/skills/clef-compose/scripts/clef_tools.py analyze \
  addons/clef/output/<name>_final.mid
```

检查项：
- 所有预期声部均有音符数据（音符数 > 0）
- 总时长与 base.mid 一致
- 无异常的 velocity/CC 值（如全 0 或全 127）

## 表现力参数说明

| 参数 | CC 编号 | 效果 | 典型范围 |
|------|---------|------|---------|
| 音量 | CC7 | 声部音量平衡 | 40-100 |
| 声像 | CC10 | 立体声位置 | 0-127（64=居中） |
| 混响 | CC91 | 混响深度 | 0-127 |
| 弯音 | Pitch Bend | 音高微调（颤音/滑音） | -8192~8191 |
| 力度 | Velocity | 单音符力度 | 1-127 |

## balance_intent 策略参考

| 标签 | CC7 策略 |
|------|---------|
| melody_forward | 旋律 CC7 最高（90+），伴奏退后（50-70） |
| epic_tutti | 所有声部 CC7 提升（80+），低频加厚 |
| intimate | 伴奏层大幅降低（30-50），声部间距拉大 |
| rhythmic_drive | 低音+鼓突出（80+），旋律适中（60-80） |

## 常见问题

**Q: base.mid 不存在？**
A: 先从 score.abc 生成：`python scripts/abc_to_midi.py .clef-work/score.abc -o .clef-work/base.mid`

**Q: 没有 plan.json 也能做表现力注入吗？**
A: 可以，但失去段落级差异化能力。Orchestrator 将基于全局平衡分析设计统一的 CC 方案。

**Q: 用户说"表现力太夸张/太弱"？**
A: 让 Orchestrator 在新方案中整体降低/提高 CC7 幅度（如 ±15），重新注入。

**Q: 注入后某声部音符数为 0？**
A: 说明 expression_plan.json 中该声部的 channel 映射有误。检查 plan.json 的 orchestration 配置，确认 channel 与 base.mid 声部对应关系。
