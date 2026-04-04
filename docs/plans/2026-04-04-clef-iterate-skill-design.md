# clef_iterate Skill 设计

日期：2026-04-04
状态：待实施

## 背景

当前 `/clef-compose` 是从零开始的完整作曲流程（6 步，430+ 行 SKILL.md），缺乏对已有曲子做增量改进的能力。真实音乐制作中，编曲/混音/表现力调整往往是在骨架完成后的独立环节，不一定在同一个 session 中完成。

## 关键决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 定位 | 独立 skill | 工作流差异大，不臃肿主 skill |
| Agent 复用 | 共享 Arranger/Orchestrator/Reviewer/Revision | Agent 是共享资源 |
| 输入 | .clef-work/ 完整上下文 + --file 外部文件 | 灵活性 |
| 操作模式 | 参数式 + 无参菜单式 | CLI 习惯 + 易用性 |
| 第一版操作 | 添加编曲层 + 重新表现力 | 最独立、最易验证 |

## 触发方式

```
/clef_iterate                  # 菜单模式
/clef_iterate --add-layers     # 添加编曲层
/clef_iterate --re-expr        # 重新表现力注入
/clef_iterate --file <path>    # 指定目标文件
```

## 工作流

```
clef-compose:  Step 0 → 1a → 1b → 2a → 2b → 2.5 → 3
clef_iterate:   读取 → 操作选择 → 执行 → 验证 → 输出
```

### 阶段 1：读取与准备

1. 确定目标文件
   - 默认：`.clef-work/score.abc` + `.clef-work/plan.json`
   - `--file`：用户指定路径（.abc 直接用，.mid 先 midi-to-abc 转换）

2. 上下文检查
   - plan.json 存在 → 完整上下文，直接使用
   - plan.json 不存在 → `clef_tools.py analyze` 生成临时 plan.json
   - score.abc 不存在 → 报错退出

3. 操作选择
   - 参数模式：`--add-layers` 或 `--re-expr` 直接确定
   - 菜单模式：展示可用操作 + 曲子信息摘要，等待用户选择

### 阶段 2：执行操作

**--add-layers（添加编曲层）：**
1. 读取 plan.json sections 的 energy_level
2. 按 P2 energy_level 规则决策编曲层分配
3. 填充 orchestration.layers（voice_id、channel、sections）
4. 派发 Arranger → append 到 score.abc → validate → 转换 MIDI

**--re-expr（重新表现力注入）：**
1. 读取已有 expression_plan.json（如存在）
2. 派发 Orchestrator 重新设计 CC/力度曲线
3. 注入到 MIDI → 验证输出完整性

### 阶段 3：验证与输出

1. 派 Reviewer 审核改动后质量
2. 输出试听文件 + 审核报告
3. ⛔ 用户确认点：确认满意或继续调整

## Agent 调用

| Agent | 操作 | 用途 |
|-------|------|------|
| Arranger | --add-layers | 添加编曲层 |
| Orchestrator | --re-expr | 重新设计表现力 |
| Reviewer | 两者 | 质量审核 |
| Revision | 两者 | 格式修正 |

第一版不需要 Composer/Harmonist/Rhythmist（不动骨架）。

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | .claude/skills/clef-iterate/SKILL.md | Skill 定义 |
| 新建 | .claude/skills/clef-iterate/references/ | 操作参考文档 |

## 远期扩展

以下操作记录备选，第一版不实现：
- `--edit-melody <section>`：修改指定段落旋律
- `--edit-harmony <section>`：修改指定段落和声
- `--re-orchestrate`：替换乐器/配器方案
- `--remix`：风格变奏（节奏改编、调式转换等）
