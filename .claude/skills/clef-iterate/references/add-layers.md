# 添加编曲层（--add-layers）操作参考

## 概述

在已有 4 轨骨架（V:1 旋律、V:2 和声、V:3 低音、V:4 鼓）基础上，根据段落能量级别添加编曲层，丰富音乐织体。

## 前置条件

- `.clef-work/score.abc` 存在且包含至少 V:1-V:4
- `plan.json` 存在（至少包含 `sections` 数组，每项有 `energy_level`）
  - 若 plan.json 不存在，需从 score.abc 推断段落结构或提示用户

## energy_level 编曲层分配规则

与 clef-compose Step 2.5 完全一致（energy_level 范围 1-10）：

| energy_level | 编曲动作 | 说明 |
|-------------|---------|------|
| 1-3 | 无编曲层 | 织体应保持单薄透明 |
| 4-5 | arpeggio_pad | 添加 1 层分解和弦铺底 |
| 6-8 | counter_melody + arpeggio_pad | 添加 2 层，织体最丰满 |
| 9-10 | counter_melody + arpeggio_pad + 额外层 | 可添加 string_pad 等第三层 |

## 配器平衡预检查 ⭐

在生成编曲层前，必须检查所有声部（含新增层）的 register 是否存在频段重叠。

### 检查规则

```python
def check_register_overlap(voices):
    """
    voices: list of {"name", "register": "Lo-Hi", "channel": int}
    Returns: list of {"pair", "overlap_semitones", "severity", "suggestion"}
    """
    issues = []
    for i, a in enumerate(voices):
        for b in voices[i+1:]:
            a_lo, a_hi = parse_register(a["register"])
            b_lo, b_hi = parse_register(b["register"])
            overlap = max(0, min(a_hi, b_hi) - max(a_lo, b_lo))
            if overlap > 12:
                issues.append({
                    "pair": f"{a['name']} vs {b['name']}",
                    "overlap_semitones": overlap,
                    "severity": "FAIL",
                    "suggestion": f"调整 {a['name']} register 以减少重叠"
                })
            elif overlap > 6:
                issues.append({
                    "pair": f"{a['name']} vs {b['name']}",
                    "overlap_semitones": overlap,
                    "severity": "WARN",
                    "suggestion": f"建议声像分离: {a['name']} CC10=30, {b['name']} CC10=100"
                })
    return issues
```

### 自动调整策略

当检测到严重重叠（>12 半音）时：
1. 优先移动**新增层**的 register（不修改骨架声部）
2. 在该层乐器 `range` 范围内选择不重叠的频段
3. 若无法调整（range 太窄）→ 报告 FAIL，暂停等待用户指定 register
4. 调整后更新 plan.json

### 频段可视化输出

```
频段分布（MIDI note）:
Melody:       |==========|           72-88
CounterMelo:  |      |=====|         79-95  ⚠ 与 Melody 重叠 9
Harmony:      |========|              52-69
Arp Pad:      |=========|             60-76  ⚠ 与 Harmony 重叠 8
Bass:         |====|                  40-47
              40  50  60  70  80  90
```

## sections 字段自动填充逻辑

```python
for section in plan.sections:
    if section.energy_level >= 6:
        counter_melody.sections.append(section.id)
    if section.energy_level >= 4:
        arpeggio_pad.sections.append(section.id)

# 移除 sections 为空的层
for layer in layers:
    if not layer.sections:
        remove(layer)
```

## channel 分配

基础 4 轨已占用 ch0（旋律）、ch1（和声）、ch2（低音）、ch9（鼓）。编曲层从 ch3 起递增：

| 层 | 默认 channel | voice_id |
|----|-------------|----------|
| counter_melody | 3 | 5 |
| arpeggio_pad | 4 | 6 |

如果用户自定义了 channel，以 plan.json 为准。

## plan.json layers 格式

更新后的 `orchestration.layers` 应包含：

```json
{
  "counter_melody": {
    "name": "Oboe",
    "channel": 3,
    "voice_id": 5,
    "instrument": 68,
    "range": "A4-G6",
    "register": "D5-B5",
    "sections": ["B"]
  },
  "arpeggio_pad": {
    "name": "Harp",
    "channel": 4,
    "voice_id": 6,
    "instrument": 46,
    "range": "C3-C6",
    "register": "C4-E5",
    "sections": ["A", "B"]
  }
}
```

若 plan.json 原始版本已有 layers 配置（如来自 clef-compose Step 1a），优先使用已有配置，仅自动填充 `sections` 和 `channel`。

## append 合并注意事项

1. **不要使用 merge_abc.py** — 它会从零创建完整 score，覆盖 V:1-V:4
2. 正确做法是 `cat .clef-work/layer_*.abc >> .clef-work/score.abc`
3. append 前确认 score.abc 末尾有换行符
4. 如果 validate FAIL 需要修正 layer 文件并重新 append，**必须先移除上次 append 的内容**（回滚到 snapshot 备份版本）

## 自动修正循环 ⭐

Reviewer 审核后如果发现 FAIL 或 P0/P1 级问题，进入自动修正循环：

```
for round in range(3):
    review_report = Reviewer(score.abc, plan.json)
    critical_issues = [issue for issue in review_report if issue.severity in ("FAIL", "P0", "P1")]
    if not critical_issues:
        break
    
    # 回滚 score.abc 到 append 前的版本
    restore_snapshot("pre-add-layers")
    
    # 派 Revision 修正 layer 文件
    for issue in critical_issues:
        if issue.target_file:  # e.g. "layer_counter_melody.abc"
            Revision.fix(issue.target_file, issue.suggestion)
    
    # 重新 append
    append_layers_to_score()
    
    # 重新 validate
    validate_report = validate_abc.py(score.abc, plan.json)
    if validate_report.has_fail:
        continue  # 下一轮
    
    # 重新 Reviewer
    review_report = Reviewer(score.abc, plan.json)

# 3 轮后仍有问题 → 报告用户
```

关键规则：
- 每轮修正后**必须重新 validate_abc.py**（不信任 Revision 自检）
- 每轮修正后**必须重新 Reviewer 审核**（验证修正是否引入新问题）
- 3 轮上限防止无限循环
- 修正范围仅限 layer 文件，**绝不修改 V:1-V:4 骨架**

## validate_abc.py 对编曲层的检查范围

| 检查项 | 对 V:5+ 的处理 |
|--------|---------------|
| 音域越界 | 正常检查 FAIL |
| 小节不完整 | 正常检查 FAIL |
| 格式错误 | 正常检查 FAIL |
| 旋律性检查（M1-M5） | 跳过 |

## 常见问题

**Q: 所有段落 energy_level < 4，无法添加编曲层？**
A: 提示用户曲子整体能量偏低，不适合添加编曲层。建议先通过 clef-compose 的 `--re-expr` 或手动调整段落能量后再尝试。

**Q: score.abc 已有 V:5+ 声部？**
A: 询问用户是追加新层还是替换已有层。追加时 voice_id 从已有最大值 +1 开始。

**Q: plan.json 中没有 orchestration.layers 字段？**
A: 使用默认编曲层配置（counter_melody = Oboe ch3 voice_id 5, arpeggio_pad = Harp ch4 voice_id 6），根据 energy_level 填充 sections。

**Q: 预检查发现频段严重重叠且无法自动调整？**
A: 报告 FAIL 并暂停，提示用户手动指定 register 范围或更换乐器。
