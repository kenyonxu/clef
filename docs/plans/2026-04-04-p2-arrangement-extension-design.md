# P2 编曲扩展 Step 2.5 设计

日期：2026-04-04
状态：待实施

## 背景

当前 clef-compose 工作流跳过了真实音乐制作中的"编曲"环节：
```
作曲（旋律+和弦骨架）→ [缺失：编曲 Arrangement] → 演奏表现力
```

P0/P1 改进（力度/节奏/音域/密度/旋律策略）已在骨架层面提升质量，但始终只有 4 轨（旋律/和声/低音/鼓），对比参考曲的 3-19 轨差距明显。

## 关键决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 编曲层类型 | counter-melody + arpeggio_pad | 最常用、效果最明显，后续可扩展 |
| 添加粒度 | 按段落 energy_level 动态 | 接近真实编曲（情绪低时不加层） |
| 执行 Agent | 新建 clef-arranger | 分工明确，不污染 Composer/Harmonist prompt |
| 流程位置 | Step 2.5，在 Step 2b 之后、Step 3 之前 | 骨架打磨好再编曲，更接近真实流程 |

## 流程变更

```
旧：2a → 2b → 2c(确认) → 3
新：2a → 2b → 2c(确认) → 2.5 编曲扩展 → 2c.5(确认) → 3
```

Step 2.5 详细流程：
1. 读取 plan.json，检查所有 section energy_level，全部 < 3 则跳过
2. 按 energy_level 规则自动填充 `layers` 配置（channel、sections），写入 plan.json
3. 派发 Agent: Arranger（clef-arranger），传入 score.abc + plan.json
4. merge_abc.py 合并编曲层片段到 score.abc
5. snapshot（--step 2.5）
6. validate_abc.py 验证（编曲层宽松模式）
7. abc_to_midi.py 转换，供用户试听

用户确认点 3 顺移到 Step 2.5 之后。

## plan.json schema 变更

orchestration 新增可选 `layers` 字段：

```json
{
  "orchestration": {
    "melody": { "name": "Flute", "channel": 0, "instrument": 73, "range": "C4-C7", "register": "C5-G6" },
    "harmony": { "name": "Strings", "channel": 1, "instrument": 48, "range": "C3-C6", "register": "G3-E4" },
    "bass": { "name": "Bass", "channel": 2, "instrument": 32, "range": "E2-E4", "register": "E2-B2" },
    "drums": { "name": "Drums", "channel": 9, "instrument": 0, "range": "", "register": "" },
    "layers": {
      "counter_melody": {
        "name": "Oboe", "channel": 3, "instrument": 68,
        "range": "A4-G6", "register": "D5-B5",
        "sections": ["B"]
      },
      "arpeggio_pad": {
        "name": "Harp", "channel": 4, "instrument": 46,
        "range": "C3-C6", "register": "C4-E5",
        "sections": ["A", "B"]
      }
    }
  }
}
```

字段说明：
- `voice_id`：确定性声部编号（如 5, 6），不依赖 dict 迭代顺序，与 Arranger 输出的 V:N 一致
- `sections`：该层出现的段落 ID 列表，由主流程按 energy_level 自动决定
- `channel`：3-8 范围，由主流程自动分配
- `layers` 为空或不存在时跳过 Step 2.5

## 编曲层决策规则

| energy_level | 编曲动作 | 典型段落 |
|-------------|---------|---------|
| 1-2 | 无编曲层 | Intro、Outro |
| 3 | 加 arpeggio_pad（1 层） | A 段叙事 |
| 4-5 | 加 counter_melody + arpeggio_pad（2 层） | B 段高潮 |

通道分配：基础 4 轨占用 ch0/ch1/ch2/ch9，编曲层从 ch3 起递增。

## clef-arranger agent

文件：`.claude/agents/clef-arranger.md`

**输入**：score.abc（4 轨骨架）+ plan.json（含 layers 配置）
**输出**：每个编曲层的 ABC 片段

### counter_melody 指导
- 基于 V:1 写对位旋律，与主旋律形成对话/呼应
- 音区在主旋律下方 3-6 半音或上方 3 度，避免重叠
- 不需全小节覆盖，可在乐句间隙出现（"你唱我应"）
- 动态标记 !mp!-!mf!，不抢主角
- 仅在 sections 指定段落生成，其余段落休止

### arpeggio_pad 指导
- 基于 V:2 和弦进行写分解音型（根-五-八 / 根-三-五）
- 音区在 harmony register 附近或上方 1 八度
- 节奏均匀稳定（八分音符分解为主）
- 动态标记 !pp!-!mp!，背景铺底
- 仅在 sections 指定段落生成

### 硬约束
- 严格对齐已有声部小节数
- 使用 %%MIDI channel 和 %%MIDI program 指定通道和乐器
- 纯 ABC 片段输出，无头部字段
- 不得修改现有声部
- V:N 的 voice_id 必须与 plan.json 中对应层的 voice_id 一致
- 每个层写入独立文件（.clef-work/layer_<name>.abc）

## 脚本改动

| 脚本 | 改动 | 说明 |
|------|------|------|
| validate_abc.py | plan.json voice 映射动态化 | 从硬编码 4 轨改为读取 orchestration 所有 key |
| abc_to_midi.py | 无改动 | 已支持 V:N 动态解析 |
| merge_abc.py | 无改动 | fragments dict 已通用化 |
| inject_expression.py | 无改动 | 按通道寻轨已通用化 |

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | .claude/agents/clef-arranger.md | Arranger agent prompt |
| 修改 | .claude/skills/clef-compose/SKILL.md | 新增 Step 2.5 工作流 |
| 修改 | .claude/skills/clef-compose/scripts/validate_abc.py | voice 映射动态化 |

## 远期扩展

以下编曲层类型记录备选，第一版不实现：
- **string_doubling**：旋律同音/高/低三度加厚
- **inner_voice**：和声内声部装饰填充
- **ostinato**：固定音型循环
