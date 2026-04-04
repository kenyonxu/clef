# Step 2b 并行执行协议

进入 Step 2b 时必须读取此文件。

## 任务分批

解析 tasks.json，将任务分为两批：
- **独立任务批**：`depends_on` 为 null 的任务
- **依赖任务批**：`depends_on` 不为 null 的任务

## 独立任务批并行执行（2+ 个任务时）

1. `TeamCreate(team_name="clef-iter-{round}", description="第{round}轮迭代")`
2. 在**一条消息中同时**派发所有独立任务（每个任务一个 Agent 调用，携带 `team_name` 和 `name` 参数）：
   ```
   Agent(subagent_type=task.agent, team_name="clef-iter-{round}", name="{agent}-{index}", prompt=定向修改指令)
   ```
   > **⚠ 并行 Agent 禁止直接编辑 score.abc**。每个 Agent 将输出写入独立文件：
   > `.clef-work/parallel_<agent>_<index>.abc`
   > 在 prompt 中明确告知 Agent 写入路径。
3. 等待所有 teammate 返回结果，收集 ABC 片段
4. 向所有 teammate 发送 `shutdown_request`，等待确认后 `TeamDelete`
5. 使用 `merge_abc.py` 合并所有并行任务输出到 score.abc（按 generation_order 排列）
6. `abc_to_midi.py` → `clef_tools.py analyze` → `validate_abc.py`
   > 注：写入 score.abc 后 Leader 必须手动运行 validate_abc.py 生成验证报告。
7. 如果 validate 报告 FAIL → 派 Revision Agent 修正

## 0-1 个独立任务时

按原有串行方式逐个派发。

## 依赖任务批（串行）

按 `depends_on` 顺序串行执行：
- 每个依赖任务完成后：merge → abc_to_midi → analyze → validate
- 如果 validate FAIL → 派 Revision Agent 修正

## 全部完成后

派 Reviewer → Leader → 判断是否继续迭代

## V:5+ 编曲层保护

当 score.abc 包含 V:5+ 编曲层时，Step 2b 迭代中的 `merge_abc.py` 会从零创建完整 score，**导致编曲层丢失**。

**解决方案**：迭代开始前保存 layer 文件，merge 后重新 append。

```
# 迭代前备份
cp .clef-work/layer_*.abc .clef-work/history/

# merge_abc.py 完成后（score.abc 仅含 V:1-V:4）
# 重新 append 编曲层
for f in .clef-work/history/layer_*.abc; do
    cat "$f" >> .clef-work/score.abc
done
```

**前提条件**：仅当 `.clef-work/layer_*.abc` 文件存在时执行此保护逻辑（即 Step 2.5 已完成）。

## 依赖任务中间同步

tasks.json 中存在 `depends_on` 时，每个依赖任务完成后必须 merge → abc_to_midi → analyze → validate 确认通过后，再派发下一个依赖 Agent。详见 clef-leader.md「3.1 依赖任务状态传递」。
