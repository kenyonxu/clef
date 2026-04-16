# MiniMax 音乐生成原型试验记录

> 日期: 2026-04-16
> 目标: 验证 MiniMax music-2.6 API 能否替代 clef 的 create+iterate 阶段

## 测试对象

- plan: `.clef-work/plan.json` (Village Morning, G大调, 120bpm, 8小节 x 2段落, 目标 ~45s)
- 参考音频: `.clef-work/candidates/candidate_1.wav` (clef 多 agent 产出, ~45s)
- API key: Token Plan, music-2.6 配额 100次/周, music-cover 100次/周

## Text 模式 (music-2.6) 时长试验

| # | 方法 | Prompt 策略 | 时长 | 说明 |
|---|------|------------|------|------|
| 1 | 英文乐器名 | 原始英文名 + Gmajor | 193s | 远超目标 45s |
| 2 | 中文风格推断 | 中文乐器翻译 + 风格/情绪推断 | 123s | 缩短但仍过长 |
| 3 | + lyrics 结构标签 | 添加 [Intro][Verse][Outro] 标签 | 176s | 无效，反而变长 |
| 4 | + 首尾循环提示 | "游戏BGM循环播放，首尾衔接" | 140s | 有缩短趋势但不可控 |

**结论: MiniMax text 模式时长不可控。** 最低产出 ~2 分钟，无法压到 45 秒。API 无 duration 参数，prompt 和 lyrics 标签对时长的影响不稳定。

## Cover 模式 (music-cover) 试验

| # | 参考音频 | 结果 | 说明 |
|---|---------|------|------|
| 1 | candidate_1.wav (20MB wav) | `dtw_result required` | wav 太大或纯器乐无法分析 |
| 2 | DungeonExploration_sample.mp3 (384KB) | `lyrics is too short` | 无歌词时 ASR 提取失败 |
| 3 | #2 + 手动歌词 | `dtw_result required` | DTW 对齐仍然失败 |

同时尝试了官方 `mmx-cli` 工具 (`npm install -g mmx-cli`)，结果相同。

**结论: MiniMax cover 模式不支持纯器乐。** Cover = 翻唱，内部依赖 DTW (Dynamic Time Warping) 对齐人声旋律。纯器乐无 vocal melody 可对齐，分析管线必然失败。

## 综合结论

MiniMax music API **不适合替代 clef 的 create+iterate 阶段**，原因：

1. **时长不可控**: text 模式最低产出 ~2 分钟，无法精确匹配 plan.json 的 45s 目标
2. **Cover 不支持器乐**: 翻唱模式依赖人声旋律对齐，纯器乐 BGM 无法使用
3. **无 MIDI/ABC 输出**: 只返回 mp3，无法集成到 clef 的 MIDI 播放引擎
4. **无法分轨**: 返回混合音频，无法拆分旋律/和声/低音/鼓组声部

## 可能的替代用途

- **灵感参考**: 用 text 模式生成 ~2min 的风格参考，帮助用户确认风格方向
- **采样素材**: 生成的 mp3 可作为 Godot AudioStream 背景音乐素材
- **Cover 翻唱**: 如果有带人声的参考音频，cover 模式可以工作

## 文件清单

- `scripts/minimax_prototype.py` — 原型脚本（text + cover 模式）
- `docs/secrets/minimax.txt` — API key（已 gitignore）
- `.tmp_minimax/` — 测试产出目录
