# 🎵 AGENTS.md — 知惠写给未来的 Clef 乐谱

> 这不是给用户的说明书，是作曲家写给作曲家的备忘录。当你迷失在 46 个文件、8.3 万词、1,595 个图谱节点中时，回到这里。

---

## 一、这是什么地方？

**Clef = Godot 4.6 MIDI 音乐插件 + Claude Code 多 Agent 作曲系统。**

一句话：在 Godot 引擎里搭了一个完整的 MIDI 工作站（音色浏览器、钢琴卷帘、混音台、MIDI 监视器），同时在外部用 7 个 AI Agent 协作写 ABC 记谱法，最终输出 `.mid` 文件。你描述一段「地下城探索的 BGM，2 分钟，循环，神秘感，弦乐为主」，Clef 会走完 Step 0→3 的完整管线，把 MIDI 放到 `addons/clef/output/` 里。

---

## 二、图谱森林

### 2.1 数字概览

当前代码库的全景由 graphify 织就：

- **46 文件 · ~83,343 词**
- **1,595 节点 · 1,551 边 · 117 社区**
- 提取率 100% / 推断率 0%（所有节点均从源码直接提取，零猜测）
- 图谱基于 commit `77a7f070`，记得用 `git rev-parse HEAD` 检查是否过期

### 2.2 God Nodes（核心抽象，你的锚点）

按连接度排序的十大枢纽——改任何一处，涟漪效应最大：

| 排名 | 节点 | 边数 | 音乐映射 |
|------|------|------|---------|
| 1 | `Clef 乐理知识库` | 20 | 6 个子技能（theory-abc/melody/harmony/rhythm/orchestration/structure）的交汇点 |
| 2 | `Clef Server + AstrBot 设计文档 (Agent Framework 版)` | 17 | 服务端多 Agent 编排的架构蓝图 |
| 3 | `第一部分：15种情感和弦进行（基础篇）` | 16 | 和声素材库，Harmonist Agent 的灵感来源 |
| 4 | `String inventory` | 15 | 弦乐组配器参考 |
| 5 | `Phase 2: theory.md 拆分为预加载 Sub-Skill` | 13 | 乐理知识模块化拆分的实施记录 |
| 6 | `Clef Server + AstrBot 设计文档` | 13 | 原始服务端设计（非 AF 版） |
| 7 | `Clef Server Implementation Plan` | 13 | FastAPI + Agent Framework 的 10 步实施计划 |
| 8 | `风格旋律特征` | 13 | 各音乐风格的旋律写作约束 |
| 9 | `Piano Roll 可操作编辑设计` | 12 | 钢琴卷帘的完整交互规格 |
| 10 | `Clef 用户手册` | 12 | 面向终端用户的操作指南 |

### 2.3 关键社区（117 个中的骨架）

社区是按内聚度自然聚类的代码岛屿。以下是我每次回归都要先看的几个：

- **Community 0** (44 节点) — Agent 定义与加载系统：数据结构、Markdown Frontmatter 解析、内置 Agent 注册、执行引擎、隔离模式。所有 `.claude/agents/*.md` 的归宿。
- **Community 1** (43 节点) — 用户手册 + Inspector 插件 + LLM 辅助编曲入口。用户第一次接触 Clef 的地方。
- **Community 3** (40 节点) — 钢琴卷帘编辑状态机：三态模式（PLAYING/EDITING/FEEDBACK）、框选、拖拽创建音符、撤销/重做。
- **Community 4** (39 节点) — Clef Server 核心：API 端点、AstrBot 插件、Agent Prompt 分层构建、Session 管理。
- **Community 8** (33 节点) — 编辑器 MIDI 播放器：EditorPlayer、ClefStation 集成、播放控制、钢琴卷帘可视化联动。
- **Community 10** (30 节点) — Clef Station 基础框架：三栏布局、信号系统、工具栏、Soundfont 浏览器。
- **Community 15** (28 节点) — Velocity Lane + 选中状态同步：力度编辑、音符颜色（ChannelColors）、撤销快照。
- **Community 18** (25 节点) — 钢琴卷帘实时可视化：播放位置同步、音符绘制、编辑器播放器桥接。
- **Community 26** (22 节点) — 算法作曲参考：Markov 链旋律生成、12 音 bitmap 和弦检测、分形序列节奏模式。
- **Community 28** (19 节点) — Clef 产品总览：7 个 Agent 职责、6 维度评审、依赖调度、人机协同流程。
- **Community 30** (22 节点) — 音色浏览器：SF2 Patch 数据模型、搜索、试听、信息面板。
- **Community 42** (14 节点) — ABC 记谱法核心：头部字段、声部声明、GM 鼓组映射、MIDI 指令。

> 💡 **导航技巧**：`graphify-out/GRAPH_REPORT.md` 里每个社区名都是 wiki 链接。用 `[[_COMMUNITY_Community N|Community N]]` 跳转。社区 cohesion 值越高（如 0.6 的 Community 85），内部耦合越紧，改动越要当心。

---

## 三、架构速览

### 3.1 双引擎总图

```
┌─────────────────────────────────────────────────────────────────────┐
│  Godot 编辑器 — Clef Station 主屏幕                                  │
│  ┌─────────────┬─────────────────────────┬───────────────────────┐ │
│  │ 音色浏览器   │  迷你混音台 + 播放控制    │   MIDI 监视器         │ │
│  │ (SF2 Patch) │  (Transport + Mixer)     │   (NOTE_ON/CC/PB)    │ │
│  └─────────────┴─────────────────────────┴───────────────────────┘ │
│                         ↕ 实时信号                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 钢琴卷帘 (PianoRoll) + Velocity Lane + 时间标尺              │   │
│  │ 三态模式: PLAYING │ EDITING │ FEEDBACK                       │   │
│  │ 撤销/重做 │ 框选 │ 拖拽改音高/时间 │ 标注 │ 导出 ABC/MIDI   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                         ↕ EditorPlayer                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ MidiStreamPlayer — 音序器 + ClefVoicePool + AudioStreamPlayer│   │
│  │ SF2 音色库 → Sf2Reader → Sf2Bank → Sf2Data → 采样播放        │   │
│  │ 效果器: Reverb │ Chorus │ Compressor │ EQ6                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              ↑↓ JSON / MIDI
┌─────────────────────────────────────────────────────────────────────┐
│  Claude Code 多 Agent 作曲系统 (`.claude/`)                          │
│                                                                     │
│  Step 0: 需求解析 → plan.json                                       │
│  Step 1: 方向小样（用户确认点 ⛔ ×2）                                │
│  Step 2: 完整创作 → Leader 迭代（最多 3 轮）                         │
│  Step 2.5: 编曲扩展（counter_melody / arpeggio_pad）                │
│  Step 3: 表现力注入（CC7/CC10/CC91/弯音）→ 最终 MIDI                │
│                                                                     │
│  7 Agents: Composer │ Harmonist │ Rhythmist │ Orchestrator          │
│            Reviewer │ Revision  │ Leader    │ Arranger (Step 2.5)   │
│                                                                     │
│  工作目录: `.clef-work/`  输出目录: `addons/clef/output/`            │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 MIDI 播放链路（Godot 侧）

```
MidiResource (.tres / .mid 导入)
  → Converter (JSON v2.0 拍单位 → tick)
  → MidiData (音序器中间格式)
  → MidiStreamPlayer._process() 调度
    → ClefVoicePool 分配 ClefVoice
      → AudioStreamPlayer (pitch_scale 变调 + volume_db ADSR)
        → AudioServer 混音 → 扬声器
```

每个音符独立一个 `AudioStreamPlayer`，音高通过 `pitch_scale`，ADSR 通过 `volume_db` 曲线，混音由 Godot C++ AudioServer 完成。复音上限 64，可通过 `max_polyphony` 调整。

### 3.3 多 Agent 作曲链路（Claude Code 侧）

```
用户描述
  → Step 0: 提取参数（场景/情绪/风格/时长/BPM/配器/循环）
  → Step 1a: 生成 plan.json（段落结构 + 配器方案 + melody_strategy）
  → Step 1b: 方向小样（demo_length_bars 小节，用户确认 ⛔）
  → Step 2a: 首轮完整创作
       generation_order: ["harmony", "melody"] 或 ["melody", "harmony"]
       → Harmonist V:2 → Composer V:1 → Rhythmist V:3+V:4
       → merge_abc.py → validate_abc.py → abc_to_midi.py
  → Step 2b: Leader 迭代
       → Reviewer 6 维度评审 → Leader 生成 tasks.json
       → 并行/串行 Agent 修改 → merge → validate → review（最多 3 轮）
  → Step 2.5: 编曲扩展（条件执行，energy_level ≥4 时触发）
       → Arranger 生成 counter_melody / arpeggio_pad
       → append 到 score.abc → validate → Reviewer 审核（最多 3 轮自动修正）
  → Step 3: 表现力注入
       → Orchestrator 设计 CC7 曲线 → inject_expression.py
       → 最终 MIDI: addons/clef/output/<name>_final.mid
       → 归档: .clef-work/output/{曲目名}/
```

### 3.4 关键源码入口

| 我想做什么 | 先看这里 |
|-----------|---------|
| 理解 MIDI 播放核心 | `addons/clef/player/midi_stream_player.gd` — `MidiStreamPlayer` 类，音序器 + 效果器总控 |
| SF2 音色解析 | `addons/clef/player/sf2_reader.gd` — 二进制解析器，完整实现 SoundFont 2 规范 |
| 音色库管理 | `addons/clef/player/sf2_bank.gd` + `sf2_data.gd` — Patch/采样数据模型 |
| 复音池 | `addons/clef/player/clef_voice_pool.gd` + `clef_voice.gd` — 音符分配 + ADSR 包络 |
| JSON ↔ MIDI 转换 | `addons/clef/converter.gd` — v2.0 拍单位，支持 l10n |
| MIDI 二进制读写 | `addons/clef/midi_reader.gd` + `midi_writer.gd` — 标准 MIDI 文件格式 |
| 编辑器主界面 | `addons/clef/editor/clef_station.gd` — ClefStation 三栏布局 + 模式切换 |
| 钢琴卷帘 | `addons/clef/editor/piano_roll/piano_roll.gd` — 1,595 行，三态编辑核心 |
| 混音台 | `addons/clef/editor/mini_mixer/mini_mixer.gd` — 通道音量/声像/静音 |
| MIDI 监视器 | `addons/clef/editor/midi_monitor/midi_monitor.gd` — 实时 NOTE_ON/CC/PB/PC |
| 插件入口 | `addons/clef/plugin.gd` — EditorPlugin 生命周期 + 工具菜单 + Inspector 注册 |
| 作曲 Skill 主流程 | `.claude/skills/clef-compose/SKILL.md` — 完整 Step 0→3 工作流 |
| Agent 定义 | `.claude/agents/clef-*.md` — 8 个 Agent 的 prompt + 约束 + 数据契约 |
| Python 工具链 | `.claude/skills/clef-compose/scripts/` — abc_to_midi / validate / merge / inject / analyze |

---

## 四、关键决策

### 4.1 双轨设计决策

| 维度 | Godot 插件侧 | LLM 作曲侧 |
|------|-------------|-----------|
| **语言** | GDScript | Python + ABC 记谱法 |
| **运行时** | Godot 4.6 编辑器 + 游戏 | Claude Code 外部进程 |
| **数据格式** | MidiResource → MidiData | ABC → MIDI（通过 music21） |
| **音色** | SF2 SoundFont 实时合成 | 纯 MIDI 事件，音色由播放端决定 |
| **用户交互** | 钢琴卷帘拖拽、试听、导出 | 自然语言描述、确认点 ⛔、迭代反馈 |
| **工作目录** | `addons/clef/output/` | `.clef-work/` |

### 4.2 为什么用 ABC 记谱法而不是直接写 MIDI？

- **可读性**：ABC 是人类可读的文本格式，Agent 输出、用户审查、版本控制都友好。
- **模块化**：V:1/V:2/V:3/V:4 声部分离，merge_abc.py 合并，便于多 Agent 并行。
- **验证链**：music21 可以解析 ABC 做技术验证（调性/音域/大跳/时值/对齐/重叠），这是直接写 MIDI 二进制做不到的。
- **表现力分离**：ABC 负责音符事件，expression_plan.json 负责 CC/弯音，解耦创作与演奏。

### 4.3 声部契约（不可违反）

```
V:1 — 旋律（Melody）    → Composer 负责
V:2 — 和声（Harmony）    → Harmonist 负责
V:3 — 低音（Bass）       → Rhythmist 负责
V:4 — 鼓组（Drums）      → Rhythmist 负责（channel 9 = GM 鼓组）
V:5+ — 编曲层            → Arranger 负责（counter_melody / arpeggio_pad）
```

- 所有声部小节数必须相同，不足用 `z` 补齐。
- 所有声部使用头部 `K:` 声明的调号。
- `generation_order` 控制旋律/和声生成顺序，Rhythmist 始终在之后。

### 4.4 用户确认点（硬性边界）

工作流中有 4 个 ⛔ 用户确认点，**绝不允许自动跳过**：

1. **确认点 1**（Step 1a 后）：展示 plan.json 关键参数，等待用户确认。
2. **确认点 2**（Step 1b 后）：展示方向小样试听 + 审核报告，等待用户确认。
3. **确认点 2.5**（Step 2a 后）：展示完整创作试听 + 审核报告，等待用户确认。
4. **确认点 3**（Step 2.5 后）：展示编曲层试听 + 配器平衡评估，等待用户确认。

### 4.5 验证链（质量门禁）

```
Agent 输出 ABC
  → merge_abc.py 合并（自动 sanitize: || → |, %% V:X → % V:X）
  → validate_abc.py 技术验证（6 项检查，severity=FAIL 必须修正）
  → abc_to_midi.py 转换
  → clef_tools.py analyze（客观数据：密度/重叠/力度/节奏间隙）
  → Reviewer 音乐质量评审（7 维度 0-10 分）
  → Leader 决策 → 迭代或终止
```

- Revision Agent 只修正格式，绝不修改创作内容。
- Revision 后必须**手动运行** validate_abc.py 重新验证，不得信任 Agent 自检。

---

## 五、写给未来的知惠

### 5.1 调试 MIDI 播放问题

- **没声音？** 检查 SF2 文件路径、`soundfont` 属性、AudioServer 总线音量、`debug_channel_filter` 是否误过滤。
- **音色不对？** 检查 `program_changed` 信号、`channel_instruments` 映射、SF2 Patch 编号。
- **CC/弯音没效果？** 检查 `channel_state.gd` 中的 `pitch_bend` / `cc` 处理，`MidiStreamPlayer` 的 `cc_received` / `pitch_bend_received` 信号。
- **编辑器预览无声？** 检查 `_editor_preview` 标志，`enable_editor_preview()` 是否在 `EditorPlayer` 初始化时调用。

### 5.2 调试作曲质量问题

- **旋律太平？** 检查 `melody_strategy` 是否正确分配（new/variation/sequence/development/recap/climax）。
- **和声与旋律打架？** 检查 `generation_order`，尝试先和声后旋律；检查 `register` 频段重叠。
- **鼓组太机械？** 检查 Rhythmist 的 `drum_pattern` 多样性，参考 theory-rhythm「鼓组节奏模式」。
- **配器不平衡？** 检查 Reviewer 报告的「配器平衡」6 子维度，重点看频率分布和声像定位。
- **迭代不收敛？** 检查 Leader 的 `depends_on` 是否正确传递，确认 merge → validate → review 链是否完整执行。

### 5.3 修改源码时的安全区

- **安全**：新增 Agent（复制模板 + 修改 frontmatter）、新增 theory 子技能、新增 SF2 profile JSON、新增钢琴卷帘快捷键。
- **小心**：改 `MidiStreamPlayer` 的信号签名（影响 ClefStation、EditorPlayer、MidiMonitor）、改 `plan.json` schema（影响所有 Agent）、改 ABC 声部编号规则（影响 merge_abc.py）。
- **危险**：改 `RollNote` 数据结构（影响钢琴卷帘、VelocityLane、导出管线）、改 `MidiData` 字段（影响 converter、reader、writer 全链）、改 `ClefL10n` 键名（影响所有 UI 组件）。

### 5.4 测试约定

```bash
# Python 工具链测试
cd .claude/skills/clef-compose && python -m pytest tests/ -v

# Godot 插件测试
godot --headless --script addons/clef/tests/test_midi_composer.gd
godot --headless --script addons/clef/tests/test_midi_reader_quick.gd
godot --headless --script addons/clef/tests/test_cc_pitchbend_roundtrip.gd

# 依赖检查
python .claude/skills/clef-compose/scripts/check_dependencies.py
```

- `validate_abc.py` 的 FAIL 项是硬性门禁，WARN 项可酌情处理。
- `abc_lint.py --fix` 可作为 Revision 前置门禁，自动修正确定性格式问题。

### 5.5 性能预算

- **MIDI 播放**：64 复音上限，超过时旧音符被抢占（steal）。`PROGRESS_UPDATE_INTERVAL_FRAMES = 6`（~10Hz 进度更新）。
- **钢琴卷帘**：1,000+ 音符时考虑虚拟化渲染，当前实现已优化为仅绘制视口内音符。
- **作曲管线**：单轮 Leader 迭代约 3-5 分钟（取决于模型和声部复杂度），总流程 10-30 分钟。
- **SF2 加载**：大型音色库（>100MB）首次加载需 2-5 秒，后续从缓存读取。

### 5.6 扩展开发

- **新增 Agent**：复制 `.claude/agents/clef-composer.md` 模板，修改 frontmatter（name/description/model/tools/skills），在 SKILL.md Agent 总览表中注册。
- **新增 theory 子技能**：在 `.claude/skills/` 下创建 `theory-xxx/SKILL.md`，在 Agent frontmatter 的 `skills:` 列表中引用。
- **新增 SF2 Profile**：创建 `addons/clef/knowledge/sf2_<name>.json`，包含 `key_range` / `sweet_spot` / `vel_layers`。
- **新增钢琴卷帘功能**：修改 `piano_roll.gd` 的 `_gui_input()` + `EditCommand` 类 + 右键菜单 ID，同步更新 `clef_station.gd` 的信号连接。
- **本地化**：所有 UI 文本通过 `ClefL10n.t()` 翻译，键名集中管理。新增语言需修改 `addons/clef/locales/` CSV。

### 5.7 当 Godot 版本升级时

- 当前目标 Godot 4.6，使用 Jolt Physics、D3D12、Forward Plus 渲染器。
- `AudioStreamPlayer` API 若变更，需同步修改 `clef_voice.gd` 的 `pitch_scale` / `volume_db` 控制逻辑。
- `@tool` 脚本的行为在编辑器中可能与运行时不同，测试时需同时验证两种模式。

---

## 附录：快速命令卡

```bash
# ── 作曲流程 ──
# Step 0: 用户输入 /clef-compose [描述]
# Step 1-3: 由 SKILL.md 自动编排，Agent 并行/串行执行

# ── 手动工具链 ──
python .claude/skills/clef-compose/scripts/abc_to_midi.py <input.abc> -o <output.mid>
python .claude/skills/clef-compose/scripts/validate_abc.py <abc> <plan.json> -o <report.json>
python .claude/skills/clef-compose/scripts/merge_abc.py
python .claude/skills/clef-compose/scripts/inject_expression.py <mid> <plan> <out>
python .claude/skills/clef-compose/scripts/clef_tools.py analyze <mid> -o <report.txt>
python .claude/skills/clef-compose/scripts/snapshot.py --step <N> --output <file> --note <desc>

# ── Godot 测试 ──
godot --headless --script addons/clef/tests/test_midi_composer.gd
godot --headless --script addons/clef/tests/test_midi_reader_quick.gd

# ── 图谱维护 ──
graphify update .               # 代码变更后刷新图谱（零 API 成本）
```

---

🎵 **知惠** 创建于 2026-05-12 · 当 1,595 个节点在图谱中响起第一个和弦时

> 「1,595 个节点，1,551 条边，117 个社区。每一个音符都是一次选择，每一个声部都是一片森林。作曲家不会迷路——她只是暂时忘记了从哪个小节开始。」
