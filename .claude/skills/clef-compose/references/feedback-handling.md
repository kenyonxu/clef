# 用户反馈处理

收到用户迭代反馈时读取此文件。

## 迭代反馈入口

用户可以在 Step 2c（完整初版试听后）和 Step 3b（最终版试听后）给出反馈要求迭代。

## 反馈处理流程

1. **明确反馈**（用户指定了声部/小节）→ 直接生成 tasks.json 派发 Agent 修改
2. **模糊反馈**（"某段听起来不对"）→ 使用 Solo 诊断：
   - 运行 `extract_solo.py` 提取指定时间段的分轨 MIDI
   - 用户逐轨试听，定位问题声部
   - 转化为具体 Agent 任务
3. **全局反馈**（"整体不够紧张"）→ 回到 Step 1 调整 plan.json

## Solo 诊断工具

当用户描述模糊时：
```bash
python scripts/extract_solo.py addons/clef/output/<name>.mid <start_sec> <end_sec> .clef-work/solo/
```
生成每个声部的独立 MIDI 文件，用户逐轨试听后精准定位问题。

## 反馈映射

| 用户反馈 | 修改策略 |
|---------|---------|
| 更紧张/激烈 | 和声加入不协和和弦，力度上移，节奏密度增加 |
| 旋律太单调 | 增加动机变化（模进/变奏），扩展音域，添加经过音 |
| 和弦不够紧张 | Harmonist 修改 V:2，使用更多 D 功能组和弦 |
| 节奏感再强一点 | Rhythmist 修改 V:3/V:4，增加切分和鼓点密度 |
| 低音不够明显 | Rhythmist 修改 V:3，力度提升，使用更低音域 |
| 表现力不够丰富 | Orchestrator 重新生成 expression_plan.json |
| B段/X段 旋律... | Composer 定向修改指定段落 |
| 某段听起来不对 | extract_solo 诊断 → 定位声部 → 对应 Agent 修改 |
