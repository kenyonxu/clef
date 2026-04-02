# Clef-Compose Agent 最佳实践优化 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 基于 claude-code-best-practice 仓库的最佳实践，优化 clef-compose 的 7 个 Agent 的 frontmatter 配置、theory.md 知识加载效率、自动验证和工作流数据契约。

**Architecture:** 分 4 个 Phase 执行：Phase 1 增强所有 agent 的 frontmatter（maxTurns + tools），Phase 2 将 theory.md 拆分为 6 个角色专用 sub-skill 并通过 `skills:` 预加载，Phase 3 添加 PostToolUse hook 实现写入 score.abc 后自动验证，Phase 4 添加 Agent memory 和数据契约。

**Tech Stack:** Claude Code Agent frontmatter, YAML, Python (validate_abc.py)

---

## Phase 1: Agent Frontmatter 增强

### Task 1.1: clef-composer 添加 maxTurns + Edit + Grep

**Files:**
- Modify: `.claude/agents/clef-composer.md:1-5`

**Step 1: 修改 frontmatter**

将第 5 行从：
```
tools: Read, Write, Glob
```
改为：
```yaml
tools: Read, Write, Edit, Glob, Grep
maxTurns: 8
```

**Step 2: 验证格式**

确认 frontmatter 仍然以 `---` 分隔，YAML 格式正确。

**Step 3: Commit**

```bash
git add .claude/agents/clef-composer.md
git commit -m "refactor(clef): add maxTurns, Edit, Grep to composer agent"
```

---

### Task 1.2: clef-harmonist 添加 maxTurns + Edit + Grep

**Files:**
- Modify: `.claude/agents/clef-harmonist.md:1-5`

**Step 1: 修改 frontmatter**

将第 5 行从：
```
tools: Read, Write, Glob
```
改为：
```yaml
tools: Read, Write, Edit, Glob, Grep
maxTurns: 6
```

**Step 2: Commit**

```bash
git add .claude/agents/clef-harmonist.md
git commit -m "refactor(clef): add maxTurns, Edit, Grep to harmonist agent"
```

---

### Task 1.3: clef-rhythmist 添加 maxTurns + Edit + Grep

**Files:**
- Modify: `.claude/agents/clef-rhythmist.md:1-5`

**Step 1: 修改 frontmatter**

将第 5 行从：
```
tools: Read, Write, Glob
```
改为：
```yaml
tools: Read, Write, Edit, Glob, Grep
maxTurns: 6
```

**Step 2: Commit**

```bash
git add .claude/agents/clef-rhythmist.md
git commit -m "refactor(clef): add maxTurns, Edit, Grep to rhythmist agent"
```

---

### Task 1.4: clef-orchestrator 添加 maxTurns + Edit

**Files:**
- Modify: `.claude/agents/clef-orchestrator.md:1-5`

**Step 1: 修改 frontmatter**

将第 5 行从：
```
tools: Read, Write, Glob, Bash
```
改为：
```yaml
tools: Read, Write, Edit, Glob, Bash
maxTurns: 5
```

**Step 2: Commit**

```bash
git add .claude/agents/clef-orchestrator.md
git commit -m "refactor(clef): add maxTurns, Edit to orchestrator agent"
```

---

### Task 1.5: clef-reviewer 添加 maxTurns + Grep

**Files:**
- Modify: `.claude/agents/clef-reviewer.md:1-5`

**Step 1: 修改 frontmatter**

将第 5 行从：
```
tools: Read, Write, Glob
```
改为：
```yaml
tools: Read, Write, Glob, Grep
maxTurns: 5
```

**Step 2: Commit**

```bash
git add .claude/agents/clef-reviewer.md
git commit -m "refactor(clef): add maxTurns, Grep to reviewer agent"
```

---

### Task 1.6: clef-revision 添加 maxTurns + Edit

**Files:**
- Modify: `.claude/agents/clef-revision.md:1-5`

**Step 1: 修改 frontmatter**

将第 5 行从：
```
tools: Read, Write, Glob
```
改为：
```yaml
tools: Read, Write, Edit, Glob
maxTurns: 3
```

**Step 2: Commit**

```bash
git add .claude/agents/clef-revision.md
git commit -m "refactor(clef): add maxTurns, Edit to revision agent"
```

---

### Task 1.7: clef-leader 添加 maxTurns + Grep

**Files:**
- Modify: `.claude/agents/clef-leader.md:1-5`

**Step 1: 修改 frontmatter**

将第 5 行从：
```
tools: Read, Write, Glob
```
改为：
```yaml
tools: Read, Write, Glob, Grep
maxTurns: 10
```

**Step 2: Commit**

```bash
git add .claude/agents/clef-leader.md
git commit -m "refactor(clef): add maxTurns, Grep to leader agent"
```

---

## Phase 2: theory.md 拆分为预加载 Sub-Skill

### Task 2.1: 创建 theory-abc sub-skill（所有 agent 共用）

**Files:**
- Create: `.claude/skills/theory-abc/SKILL.md`

**Step 1: 创建 SKILL.md**

从 theory.md 的 `## ABC 记谱法参考` 部分（L8-165）提取内容，包装为 sub-skill。

```markdown
---
name: theory-abc
description: ABC 记谱法语法参考。包含头部字段、音符语法、和弦记谱、多声部、MIDI 指令、力度标记、GM 鼓组映射。供所有 clef agent 共用。
user-invocable: false
---

> 此内容从 theory.md 的 ABC 记谱法参考章节提取，供 agent 通过 skills: 预加载。

[此处粘贴 theory.md L8-165 的完整内容]
```

**Step 2: 验证**

确认文件内容完整，与 theory.md 对应章节一致。

**Step 3: Commit**

```bash
git add .claude/skills/theory-abc/
git commit -m "feat(clef): create theory-abc sub-skill for ABC notation reference"
```

---

### Task 2.2: 创建 theory-melody sub-skill（Composer 专用）

**Files:**
- Create: `.claude/skills/theory-melody/SKILL.md`

**Step 1: 创建 SKILL.md**

从 theory.md 提取旋律相关章节，并附加 Composer 也需要参考的"乐器演奏约束"：

```markdown
---
name: theory-melody
description: 旋律创作乐理参考。包含音阶定义、旋律音程指南、旋律写作技法（动机发展/乐句构建/旋律建筑）。供 clef-composer agent 使用。
user-invocable: false
---

> 此内容从 theory.md 提取，供 clef-composer 通过 skills: 预加载。

[包含以下章节的完整内容:]
- ## 音阶定义 (L166-193)
- ## 旋律音程指南 (L402-471)
- ## 旋律写作技法 (L472-561)
```

**Step 2: Commit**

```bash
git add .claude/skills/theory-melody/
git commit -m "feat(clef): create theory-melody sub-skill for composer agent"
```

---

### Task 2.3: 创建 theory-harmony sub-skill（Harmonist 专用）

**Files:**
- Create: `.claude/skills/theory-harmony/SKILL.md`

**Step 1: 创建 SKILL.md**

```markdown
---
name: theory-harmony
description: 和声编配音理参考。包含和弦构建、排列法、声部进行、和弦外音、和弦进行库。供 clef-harmonist agent 使用。
user-invocable: false
---

> 此内容从 theory.md 提取，供 clef-harmonist 通过 skills: 预加载。

[包含以下章节的完整内容:]
- ## 和弦构建参考 (L194-225)
- ## 和弦排列法 (L226-277)
- ## 声部进行规则 (L278-290)
- ## 和弦外音 (L291-309)
- ## 和弦进行库 (L310-401)
```

**Step 2: Commit**

```bash
git add .claude/skills/theory-harmony/
git commit -m "feat(clef): create theory-harmony sub-skill for harmonist agent"
```

---

### Task 2.4: 创建 theory-rhythm sub-skill（Rhythmist 专用）

**Files:**
- Create: `.claude/skills/theory-rhythm/SKILL.md`

**Step 1: 创建 SKILL.md**

```markdown
---
name: theory-rhythm
description: 节奏声部乐理参考。包含鼓组节奏模式库、低音线节奏模式、低音线音高选择规则、GM 鼓组映射。供 clef-rhythmist agent 使用。
user-invocable: false
---

> 此内容从 theory.md 提取，供 clef-rhythmist 通过 skills: 预加载。

[包含以下章节的完整内容:]
- ## 节奏声部 (L562-639)
```

注意：GM 鼓组映射已在 theory-abc 中包含（ABC 记谱法参考 → GM 鼓组映射），不需要重复。

**Step 2: Commit**

```bash
git add .claude/skills/theory-rhythm/
git commit -m "feat(clef): create theory-rhythm sub-skill for rhythmist agent"
```

---

### Task 2.5: 创建 theory-orchestration sub-skill（Orchestrator 专用）

**Files:**
- Create: `.claude/skills/theory-orchestration/SKILL.md`

**Step 1: 创建 SKILL.md**

```markdown
---
name: theory-orchestration
description: 管弦乐编配乐理参考。包含 GM 乐器参考、乐器演奏约束、配器方案、配器平衡原则、弯音、表现力注入（CC 策略）。供 clef-orchestrator agent 使用。
user-invocable: false
---

> 此内容从 theory.md 提取，供 clef-orchestrator 通过 skills: 预加载。

[包含以下章节的完整内容:]
- ## GM 乐器参考 (L640-707)
- ## 乐器演奏约束 (L708-773)
- ## 配器方案 (L774-816)
- ## 配器平衡原则 (L817-984)
- ## 弯音（Pitch Bend） (L985-1010)
- ## 表现力注入参考（Orchestrator Agent 专用） (L1011-1054)
```

**Step 2: Commit**

```bash
git add .claude/skills/theory-orchestration/
git commit -m "feat(clef): create theory-orchestration sub-skill for orchestrator agent"
```

---

### Task 2.6: 创建 theory-structure sub-skill（Reviewer + Leader 共用）

**Files:**
- Create: `.claude/skills/theory-structure/SKILL.md`

**Step 1: 创建 SKILL.md**

```markdown
---
name: theory-structure
description: 音乐结构与评审乐理参考。包含歌曲形式、乐句结构、段落对比、循环衔接、术语表、输出格式约束。供 clef-reviewer 和 clef-leader agent 使用。
user-invocable: false
---

> 此内容从 theory.md 提取，供 clef-reviewer 和 clef-leader 通过 skills: 预加载。

[包含以下章节的完整内容:]
- ## 歌曲形式参考 (L1055-1175)
- ## 术语表 (L1176-1193)
- ## 输出格式约束（供 Agent 参考） (L1194-1205)
```

**Step 2: Commit**

```bash
git add .claude/skills/theory-structure/
git commit -m "feat(clef): create theory-structure sub-skill for reviewer and leader agents"
```

---

### Task 2.7: 为 Composer 添加 skills: 预加载

**Files:**
- Modify: `.claude/agents/clef-composer.md:1-6`

**Step 1: 修改 frontmatter**

在 `maxTurns: 8` 之后添加 skills 字段：
```yaml
skills:
  - theory-melody
  - theory-abc
```

**Step 2: 从"必读文件"中移除 theory.md**

将：
```
- `.claude/skills/clef-compose/theory.md` — 乐理知识和 ABC 格式规范
```
改为：
```
- 乐理知识已通过 skills 预加载（theory-melody + theory-abc），无需手动读取
```

**Step 3: Commit**

```bash
git add .claude/agents/clef-composer.md
git commit -m "refactor(clef): preload theory-melody and theory-abc skills in composer"
```

---

### Task 2.8: 为 Harmonist 添加 skills: 预加载

**Files:**
- Modify: `.claude/agents/clef-harmonist.md:1-6`

**Step 1: 修改 frontmatter**

```yaml
skills:
  - theory-harmony
  - theory-abc
```

**Step 2: 从"必读文件"中移除 theory.md**

同 Task 2.7 模式，改为：`乐理知识已通过 skills 预加载（theory-harmony + theory-abc）`

**Step 3: Commit**

```bash
git add .claude/agents/clef-harmonist.md
git commit -m "refactor(clef): preload theory-harmony and theory-abc skills in harmonist"
```

---

### Task 2.9: 为 Rhythmist 添加 skills: 预加载

**Files:**
- Modify: `.claude/agents/clef-rhythmist.md:1-6`

**Step 1: 修改 frontmatter**

```yaml
skills:
  - theory-rhythm
  - theory-abc
```

**Step 2: 从"必读文件"中移除 theory.md**

`乐理知识已通过 skills 预加载（theory-rhythm + theory-abc）`

**Step 3: Commit**

```bash
git add .claude/agents/clef-rhythmist.md
git commit -m "refactor(clef): preload theory-rhythm and theory-abc skills in rhythmist"
```

---

### Task 2.10: 为 Revision 添加 skills: 预加载

**Files:**
- Modify: `.claude/agents/clef-revision.md:1-6`

**Step 1: 修改 frontmatter**

```yaml
skills:
  - theory-abc
```

Revision 只需要 ABC 格式规范来修正格式错误，不需要其他乐理知识。

**Step 2: 从"必读文件"中移除 theory.md**

`ABC 格式规范已通过 skills 预加载（theory-abc）`

**Step 3: Commit**

```bash
git add .claude/agents/clef-revision.md
git commit -m "refactor(clef): preload theory-abc skill in revision agent"
```

---

### Task 2.11: 为 Orchestrator 添加 skills: 预加载

**Files:**
- Modify: `.claude/agents/clef-orchestrator.md:1-6`

**注意**: Orchestrator 当前的"必读文件"中**没有** theory.md，但在 agent body 中引用了 theory.md 的内容。添加 skills 预加载可以让它更高效地获取配器知识。

**Step 1: 修改 frontmatter**

```yaml
skills:
  - theory-orchestration
  - theory-abc
```

**Step 2: 在 agent body 中添加说明**

在"必读文件"之后添加一行：
```
乐理知识已通过 skills 预加载（theory-orchestration + theory-abc）
```

**Step 3: Commit**

```bash
git add .claude/agents/clef-orchestrator.md
git commit -m "refactor(clef): preload theory-orchestration and theory-abc skills in orchestrator"
```

---

### Task 2.12: 为 Reviewer 和 Leader 添加 skills: 预加载

**Files:**
- Modify: `.claude/agents/clef-reviewer.md:1-5`
- Modify: `.claude/agents/clef-leader.md:1-5`

**Step 1: Reviewer frontmatter 添加**

```yaml
skills:
  - theory-structure
  - theory-abc
```

在 agent body 中添加说明：`乐理知识已通过 skills 预加载（theory-structure + theory-abc）`

**Step 2: Leader frontmatter 添加**

```yaml
skills:
  - theory-structure
```

Leader 不需要 ABC 格式细节，但需要歌曲结构和术语表来做调度决策。

**Step 3: Commit**

```bash
git add .claude/agents/clef-reviewer.md .claude/agents/clef-leader.md
git commit -m "refactor(clef): preload theory-structure skills in reviewer and leader"
```

---

## Phase 3: 自动验证 Hook

### Task 3.1: 在 SKILL.md 中添加 PostToolUse hook

**Files:**
- Modify: `.claude/skills/clef-compose/SKILL.md:1-6` (frontmatter area)

**Step 1: 在 SKILL.md frontmatter 中添加 hooks**

在现有 frontmatter 的 `description:` 之后添加：

```yaml
hooks:
  PostToolUse:
    - matcher: "Write.*score\\.abc"
      hooks:
        - type: command
          command: python .claude/skills/clef-compose/scripts/validate_abc.py .clef-work/score.abc .clef-work/plan.json -o .clef-work/validation_report.json
          timeout: 30000
```

**Step 2: 更新工作流说明**

在 SKILL.md 的 Step 2a 和 Step 2b 中，将手动调用 validate_abc.py 的步骤标注为"由 hook 自动执行（写入 score.abc 后自动触发），Leader 读取 .clef-work/validation_report.json 即可"。

**Step 3: 验证 hook 触发**

手动测试：触发一次 composer 修改 score.abc，观察是否自动生成 validation_report.json。

```bash
# 创建测试用 score.abc 和 plan.json
# 然后通过 agent 触发 Write score.abc
# 检查 .clef-work/validation_report.json 是否自动生成
```

**Step 4: Commit**

```bash
git add .claude/skills/clef-compose/SKILL.md
git commit -m "feat(clef): add auto-validation hook on score.abc write"
```

---

## Phase 4: 进阶优化

### Task 4.1: 为 Reviewer 添加 Agent Memory

**Files:**
- Modify: `.claude/agents/clef-reviewer.md:1-6`

**Step 1: 添加 memory frontmatter**

在 `skills:` 之后添加：
```yaml
memory: project
```

**Step 2: 在 agent body 中添加 Memory 使用指引**

```markdown
## Memory 使用

你可以将跨会话积累的音乐质量洞察保存到 agent memory 中：
- 常见音乐质量问题模式（如"低音区过密导致浑浊"）
- 用户风格偏好
- 评审标准微调

每次评审完成后，如果有新的发现，更新 memory。
```

**Step 3: Commit**

```bash
git add .claude/agents/clef-reviewer.md
git commit -m "feat(clef): add project memory to reviewer agent for cross-session learning"
```

---

### Task 4.2: 为 Composer 添加 Agent Memory

**Files:**
- Modify: `.claude/agents/clef-composer.md:1-6`

**Step 1: 添加 memory frontmatter**

```yaml
memory: project
```

**Step 2: 在 agent body 中添加 Memory 使用指引**

```markdown
## Memory 使用

你可以将跨会话积累的旋律创作洞察保存到 agent memory 中：
- 用户的旋律偏好（如偏好大跳还是级进、喜欢什么动机发展方式）
- 特定风格的旋律模式库
- 反复被 Reviewer 标记的问题和修正策略

每次创作完成后，如果有新发现，更新 memory。
```

**Step 3: Commit**

```bash
git add .claude/agents/clef-composer.md
git commit -m "feat(clef): add project memory to composer agent for style preference learning"
```

---

### Task 4.3: 在 SKILL.md 中添加 Agent 数据契约

**Files:**
- Modify: `.claude/skills/clef-compose/SKILL.md` (在"Agent 总览"之后添加)

**Step 1: 添加数据契约表**

```markdown
### Agent 数据契约

| Agent | 输入（读取） | 输出（写入） | 调用者 |
|-------|------------|------------|--------|
| clef-composer | plan.json, score.abc | score.abc（V:1 声部） | SKILL.md / Leader |
| clef-harmonist | plan.json, score.abc | score.abc（V:2 声部） | SKILL.md / Leader |
| clef-rhythmist | plan.json, score.abc | score.abc（V:3+V:4 声部） | SKILL.md / Leader |
| clef-orchestrator | score.abc, plan.json | expression_plan.json | SKILL.md |
| clef-reviewer | score.abc, plan.json, validation_report.json, analysis_report.txt | review_report.json | SKILL.md / Leader |
| clef-revision | score.abc, validation_report.json | score.abc（格式修正） | Leader |
| clef-leader | review_report.json, validation_report.json, user_feedback.json, plan.json | tasks.json | SKILL.md |
| validate_abc.py | score.abc, plan.json | validation_report.json | SKILL.md / Hook |
| merge_abc.py | 多个 ABC 片段 | score.abc（合并后） | SKILL.md |
| abc_to_midi.py | score.abc | *.mid | SKILL.md |
```

**Step 2: Commit**

```bash
git add .claude/skills/clef-compose/SKILL.md
git commit -m "docs(clef): add agent data contract table to SKILL.md"
```

---

### Task 4.4: 保留 theory.md 原文件

**Files:**
- No changes needed

**Step 1: 确认 theory.md 保留**

theory.md 原文件不删除，继续作为完整乐理参考存在。SKILL.md 的"必读文件"中仍引用完整 theory.md（供主会话使用），agent 通过 sub-skill 预加载获取子集。

---

## 验证方案

### Phase 1 验证
1. 逐个检查 7 个 agent 文件的 frontmatter，确认 YAML 格式正确
2. 验证 `maxTurns` 值合理（正常流程不应触及上限）

### Phase 2 验证
1. 检查 6 个 sub-skill 文件内容完整性（与 theory.md 对应章节逐行比对）
2. 验证 sub-skill 的 `user-invocable: false` 设置正确
3. 触发一次完整 `/clef-compose` 流程，对比拆分前后输出质量

### Phase 3 验证
1. 在 `.clef-work/` 下创建测试用 score.abc + plan.json
2. 手动 Write score.abc，确认 hook 自动触发 validate_abc.py
3. 检查 `.claude/settings.json` 中现有 hook 不冲突

### Phase 4 验证
1. 验证 agent memory 字段被正确识别
2. 检查数据契约表与实际文件路径一致
