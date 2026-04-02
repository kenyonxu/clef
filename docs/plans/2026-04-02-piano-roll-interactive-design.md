# Piano Roll 可操作编辑设计

> 前置文档：[2026-03-30-piano-roll-design.md](2026-03-30-piano-roll-design.md)（只读可视化）

## 概述

将现有 PianoRoll 从只读可视化升级为**可操作的审查微调工具**。核心定位：服务于 `/clef-compose` LLM 作曲工作流，让用户在播放过程中发现问题、微调修正、试听效果，并将反馈结构化输出给 Agent。

### 使用场景

1. **轻量修正** — 改音高、力度、删音符，微调 LLM 生成结果
2. **播放标注** — 播放过程中标记问题音符、添加备注
3. **试听工具** — 添加/屏蔽指定音色的临时音符，对比效果
4. **导出保存** — 保存为新的 `.mid` + `.abc` 文件
5. **Agent 反馈** — 半自动生成结构化反馈，喂给 Composer/Revision Agent

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| UI 位置 | 原地升级现有 PianoRoll | 零迁移成本，复用现有数据流 |
| 技术方案 | A+：自绘渲染层 + 原生控件交互层 | 当前需求轻量可控，未来 DAW 扩展有清晰升级路径 |
| 数据模型 | 内存数组直接修改 + 序列化 | 简单直接，无 Diff 层复杂度 |
| ABC 导出 | music21 MIDI→ABC 反向转换 | 复用已有 Python 工具链 |

## Section 1：架构分层

```
PianoRoll (Control, @tool)
├── 渲染层 (_draw)
│   ├── 网格 + 音符矩形 + 播放头（现有）
│   ├── 选中态高亮（新增）
│   └── 标注标记点（新增）
│
├── 交互层 (子节点, 动态创建)
│   ├── _context_menu: PopupMenu          ← 右键菜单
│   ├── _annotation_popup: PanelContainer  ← 标注输入弹窗
│   └── _note_property_panel: VBoxContainer ← 音符属性面板(未来)
│
├── 状态管理
│   ├── _selection: Array[int]             ← 选中音符索引
│   ├── _annotations: Array[Annotation]    ← 标注数据
│   └── _edit_history: Array[EditAction]   ← 撤销栈(未来)
│
└── 信号
    ├── seek_requested (现有)
    ├── note_edited (新增)                 ← 音符被修改
    ├── annotation_added (新增)            ← 添加标注
    └── export_requested (新增)            ← 请求导出
```

**核心原则**：渲染层只读数据、画完即结束；交互层通过信号通知修改数据、触发 `queue_redraw()`；外部通过公共 API 和信号通信。

**升级路径**：未来加力度滑块、钢琴键盘等，只需在交互层加子节点 + 注册信号，渲染层最多加几行绘制代码。

## Section 2：数据模型与状态

### 编辑状态（新增字段）

```gdscript
## 选中音符的索引集合
var _selection: Array[int] = []

## 标注数据
var _annotations: Array[Annotation] = []

## 编辑模式
enum EditMode { SELECT, ANNOTATE, ADD_NOTE }
var _edit_mode: EditMode = EditMode.SELECT

## 拖拽状态
var _dragging: bool = false
var _drag_type: int = 0  # NONE=0, MOVE=1, RESIZE_LEFT=2, RESIZE_RIGHT=3
var _drag_start_pos: Vector2 = Vector2.ZERO
var _drag_original_notes: Array[Dictionary] = []  # 拖拽前快照

## 临时音符与屏蔽
var _temp_notes: Array[RollNote] = []       # 临时试听音符
var _muted_indices: Array[int] = []         # 屏蔽的原始音符索引
```

### 标注结构

```gdscript
class Annotation:
    var note_index: int       # 指向 _notes 中的索引
    var time: float           # 标注时间点（秒）
    var text: String          # 标注文字
    var severity: String      # "info" | "warning" | "error"
    var bar_beat: String      # 导出用：小节:拍
```

### 数据流

```
用户操作 → _gui_input() → 修改 _notes / _selection / _annotations
         → queue_redraw() → _draw() 读取数据绘制
         → emit signal    → 外部监听（导出/Agent 反馈）
```

`RollNote` 保持现有结构不变（channel, pitch, start_time, duration, velocity）。

## Section 3：撤销/重做

### 设计方案：Command 模式

每次编辑操作封装为一个 `EditCommand`，记录操作类型和操作前的数据快照。撤销时反向执行，重做时正向执行。

```gdscript
class EditCommand:
    var type: String          # "move", "resize", "delete", "add", "mute", "unmute", "property", "annotation"
    var description: String   # 人类可读描述（如 "移动音符 C4 → D4"）
    var before: Dictionary    # 操作前状态快照
    var after: Dictionary     # 操作后状态快照（undo 时用到）
```

### 状态字段

```gdscript
## 撤销/重做栈
var _undo_stack: Array[EditCommand] = []
var _redo_stack: Array[EditCommand] = []
const MAX_HISTORY: int = 100  # 最大历史记录数
```

### 操作流程

```
编辑操作开始 → _begin_command(type, description)
               → 快照当前受影响数据到 command.before

编辑操作完成 → _commit_command(command)
               → 快照操作后数据到 command.after
               → _undo_stack.append(command)
               → _redo_stack.clear()      # 新操作清空重做栈
               → queue_redraw()

Ctrl+Z        → _undo()
               → 从 command.before 恢复数据
               → _redo_stack.append(command)
               → _undo_stack.pop()
               → queue_redraw()

Ctrl+Shift+Z  → _redo()
               → 从 command.after 恢复数据
               → _undo_stack.append(command)
               → _redo_stack.pop()
               → queue_redraw()
```

### 快照策略

不同操作类型的快照内容：

| type | before 快照 | after 快照 |
|------|------------|-----------|
| move | `{index, pitch, start_time}` | 同 |
| resize | `{index, start_time, duration}` | 同 |
| delete | `{index, note_data}`（完整音符数据） | `{index}` |
| add | `{}` | `{temp_index, note_data}` |
| mute | `{index}` | `{index}` |
| property | `{index, velocity, channel}` | 同 |
| annotation | `{}` 或 `{ann_index}` | `{annotation_data}` |

### 批量操作

拖拽过程中不逐帧创建 command，而是拖拽结束时一次性 commit。如果一次操作影响多个音符（如多选后删除），合并为单个 command。

### 快捷键

- `Ctrl+Z`：撤销
- `Ctrl+Shift+Z` / `Ctrl+Y`：重做

## Section 4：编辑操作

### 鼠标交互映射

| 操作 | 模式 | 行为 |
|------|------|------|
| 左键点击音符 | SELECT | 选中/取消选中（Ctrl 多选） |
| 左键拖拽音符 | SELECT | 移动音高或时间位置 |
| 左键拖拽音符边缘 | SELECT | 调整时长（左/右边缘） |
| 左键点击空白 | SELECT | 取消全部选中 |
| 左键点击空白 | ADD_NOTE | 在该音高+时间添加临时音符 |
| 右键点击音符 | 任意 | 弹出上下文菜单 |
| 双击音符 | 任意 | 打开属性编辑（力度/通道） |
| 右键点击空白 | ANNOTATE | 弹出标注输入框 |

### 命中检测

```gdscript
func _hit_test(pos: Vector2) -> Dictionary:
    var time := _pixel_to_time(pos.x)
    var pitch := _y_to_pitch(pos.y)
    for i in range(_notes.size() - 1, -1, -1):  # 后绘制的优先
        var n := _notes[i]
        if n.channel == 9 and _muted_channels.has(n.channel):
            continue
        if pitch == n.pitch and time >= n.start_time and time <= n.start_time + n.duration:
            var edge := _check_edge(pos, n)  # 容差 4px
            return {"index": i, "edge": edge}
    return {"index": -1, "edge": "none"}
```

### 右键菜单

```
┌──────────────────────┐
│ 编辑力度...           │
│ 改变音高 ↑/↓          │
│ 删除音符              │
│ 屏蔽（临时静音）       │
│──────────────────────│
│ 添加标注...           │
│──────────────────────│
│ 导出修改后的 MIDI     │
│ 导出修改后的 ABC      │
│ 生成 Agent 反馈       │
└──────────────────────┘
```

## Section 5：标注与审查系统

### 标注可视化

- 小三角标记在音符上方，颜色按 severity（红/黄/青）
- 悬停时显示文字 tooltip（通过 `CURSOR_HELP` 光标 + 子节点 TooltipPanel 实现）
- 多个标注的三角水平错开避免重叠

### 标注输入弹窗

右键 → "添加标注" → 弹出 `_annotation_popup`（PanelContainer）：

```
┌─ 添加标注 ─────────────┐
│ 严重度: [info ▼]        │
│ 备注: [_____________]  │
│         [取消] [确认]   │
└────────────────────────┘
```

弹出位置锚定到 `get_global_mouse_position()`，超出 Control 边界时自动修正。

```gdscript
# PopupMenu 弹出示例
_annotation_popup.position = get_global_mouse_position()
_annotation_popup.popup()
```

### Agent 反馈导出

点击 "生成 Agent 反馈" 时，输出 JSON 到 `.clef-work/`：

```json
{
  "version": 1,
  "source_file": "DungeonExploration_final.mid",
  "annotations": [
    {
      "bar_beat": "3:2",
      "channel": 1,
      "pitch": 67,
      "original_pitch": 67,
      "severity": "error",
      "note": "这个音和低音冲突，听起来不和谐"
    }
  ],
  "modifications": [
    {
      "action": "pitch_change",
      "original_pitch": 65,
      "new_pitch": 64,
      "bar_beat": "5:1",
      "reason": "用户手动修正"
    }
  ]
}
```

Leader Agent 在迭代流程中读取此文件，合并到 `review_report.json`，驱动 Composer/Revision Agent 重新生成。

## Section 6：临时音符与屏蔽

### 屏蔽 vs 删除

| 操作 | 数据变化 | 渲染 | 播放 | 可恢复 |
|------|---------|------|------|--------|
| 删除 | 从 `_notes` 移除 | 消失 | 不发声 | 仅撤销 |
| 屏蔽 | 索引加入 `_muted_indices` | 灰色半透明 + 删除线 | 不发声 | 右键一键恢复 |

屏蔽是试听核心——"去掉这个音会怎样"，但还没决定真删。

### 临时音符

切换到 ADD_NOTE 模式后，左键点击网格空白处添加：

- 使用当前选中通道的默认力度（100）
- 默认时长 0.5 秒（可拖拽调整）
- 渲染时用**虚线边框**区别于原始音符
- 右键临时音符可编辑力度/时长，或删除

### 导出合并策略

```gdscript
func _get_final_notes() -> Array[RollNote]:
    var result: Array[RollNote] = []
    # GDScript 无 HashSet，用 Dictionary 模拟集合
    var muted_set: Dictionary = {}
    for i in _muted_indices:
        muted_set[i] = true
    for i in _notes.size():
        if not muted_set.has(i):
            result.append(_notes[i])
    result.append_array(_temp_notes)
    result.sort_custom(func(a, b): return a.start_time < b.start_time)
    return result
```

用户可选择：导出合并结果，或仅导出修改差异。

## Section 7：导出管线

### MIDI 导出

复用已有链路：

```
_notes (Array[RollNote])
    ↓ 遍历构建
MidiData (converter.gd 的 Converter)
    ↓ MidiWriter
.mid 文件 → addons/clef/output/
```

需补一个 `Converter` 方法从 `Array[RollNote]` 构建 `MidiData`。

### ABC 导出

在 `clef_tools.py` 中新增 `midi-to-abc` 子命令：

```python
def midi_to_abc(midi_path: str, output_path: str) -> None:
    from music21 import converter, midi
    mf = midi.MidiFile()
    mf.open(midi_path)
    mf.read()
    mf.close()
    score = midi.translate.midiFileToStream(mf)
    abc_str = converter.freezeStr(score, fmt='abc')
    Path(output_path).write_text(abc_str, encoding='utf-8')
```

### 导出触发

1. **右键菜单** → 导出（覆盖或另存）
2. **工具栏按钮**（PianoRoll 上方父面板），批量导出 `.mid` + `.abc`
3. 导出前自动保存标注到同名 `.annotations.json`（加载 MIDI 时恢复）

## Section 8：实现分阶段路线图

### Phase 1：基础编辑 + 撤销/重做

- [ ] `EditMode` 枚举 + 工具栏切换（SELECT / ANNOTATE / ADD_NOTE）
- [ ] `EditCommand` 类 + 撤销/重做栈（`_undo_stack` / `_redo_stack`）
- [ ] `_begin_command()` / `_commit_command()` / `_undo()` / `_redo()` 框架
- [ ] Ctrl+Z / Ctrl+Shift+Z 快捷键绑定
- [ ] 选中系统（点击选中、Ctrl 多选、点击空白取消）
- [ ] 音符移动（拖拽改音高/时间，结束时 commit 单个 command）
- [ ] 右键菜单（删除、改变音高、屏蔽）— 每个操作带 command
- [ ] `_notes` 直接修改 + `queue_redraw()`
- [ ] MIDI 导出（复用 MidiWriter）

### Phase 2：标注与反馈

- [ ] `Annotation` 类 + 标注输入弹窗
- [ ] 标注渲染（三角形标记 + 悬停 tooltip）
- [ ] Agent 反馈 JSON 导出
- [ ] 标注持久化（`.annotations.json`）

### Phase 3：试听工具

- [ ] ADD_NOTE 模式 + 临时音符绘制（虚线边框）
- [ ] 屏蔽系统（半透明 + 删除线渲染）
- [ ] 导出合并策略

### Phase 4：ABC 导出

- [ ] `clef_tools.py` 新增 `midi-to-abc` 子命令
- [ ] 双格式导出触发

## Section 9：DAW 特性扩展路线图

> 以下功能均不在当前设计范围，按价值和实现成本分梯队，供未来参考。

### 第一梯队：高价值、低成本

与现有架构直接衔接，实现成本相对小：

- **力度编辑器** — 水平 `HSlider` 子节点，选中音符后拖拽改力度。修正 LLM 生成的力度层次
- **钢琴键盘侧栏** — 左侧绘制黑白键，点击试听音高。帮助非乐谱阅读者定位问题音符
- **量化（Quantize）** — 手动微调的音符对齐到网格。LLM 时值有时精确但不"音乐化"
- **键盘快捷键扩展** — `Delete` 删除、方向键微调音高/时间、`Ctrl+D` 复制、`Ctrl+A` 全选

### 第二梯队：中价值、中等成本

提升审查效率：

- **时间标尺 + 小节线** — 横轴显示小节号，和 Agent 反馈的 `bar_beat` 对应
- **速度/节拍信息显示** — 从 MIDI 读取 tempo track，标尺上标注速度变化点
- **片段循环播放** — 选中区域反复播放，精确定位问题
- **波形/频谱叠加** — piano roll 下方显示音频波形，对齐看哪个音对应哪个声部

### 第三梯队：锦上添花

实现成本高，核心工作流稳定后再考虑：

- **CC 曲线编辑器** — 单独面板绘制 CC7/CC10/CC91 连续控制器曲线，精细控制表情
- **弯音可视化** — 用曲线显示弯音数据，直观看到滑音/颤音效果
- **多轨拆分视图** — 按通道上下分栏显示，每个声部独立滚动/缩放
- **Mark/SMPTE 时间码** — 和视频时间线对齐，适配游戏场景配乐工作流

### 不建议引入

- **MIDI 录制（MIDI In）** — clef 核心是 LLM 生成，手动录入不是目标
- **VST/AU 插件宿主** — 太重，和 Godot 插件定位冲突
- **自动化包络线** — 超出审查微调范畴
- **混音台/效果器链** — DAW 核心功能但不是 clef 的目标
