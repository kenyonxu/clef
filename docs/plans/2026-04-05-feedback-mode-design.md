# Feedback Mode 设计方案

## 背景

当前 Piano Roll 有两个布尔状态 `_editing` 和 `_playing`，右键菜单混合了编辑和反馈操作。标注（Annotation）功能与编辑操作耦合在一起，缺乏清晰的模式边界。

## 方案

### 1. 三态模式系统

```gdscript
enum Mode { PLAYING, EDITING, FEEDBACK }
var _mode: Mode = Mode.PLAYING
```

- `PLAYING`：只读 + 自动播放，无右键菜单
- `EDITING`：可编辑音符，显示编辑右键菜单
- `FEEDBACK`：只读 + 可选中/框选，显示反馈右键菜单，标注仅在此模式可见

`set_mode(new_mode)` 集中处理状态切换：互斥、工具栏更新、菜单重建、UI 状态。

### 2. 右键菜单分离

**编辑模式菜单**：
- 删除音符
- 音高 +1 / -1
- 编辑力度...
- 屏蔽选中音符
- 反向屏蔽

**反馈模式菜单**：
- 添加标注...（Info / Warning / Error）
- 屏蔽选中音符
- 反向屏蔽
- ---
- 生成 Agent 反馈

**播放模式**：无右键菜单。

菜单 ID 分段：编辑 0-9，反馈 10-19。

### 3. 反馈模式交互

- 复用编辑模式的选中/框选逻辑（单击、Ctrl+点击、拉框）
- 不可拖拽移动/调整/添加/删除音符
- 播放可正常使用（边听边标注）
- 播放游标可见

### 4. 工具栏 UI

```
[▶ 播放] [✏ 编辑] [💬 反馈]
```

- ButtonGroup 互斥，当前模式高亮
- 播放按钮：切到 PLAYING + 开始播放
- 编辑按钮：切到 EDITING + 停止播放
- 反馈按钮：切到 FEEDBACK，播放状态不变

### 5. EditMode 子模式简化

`EditMode { SELECT, ANNOTATE, ADD_NOTE }` → `EditMode { SELECT, ADD_NOTE }`

移除 `ANNOTATE`（归入反馈模式）。`ADD_NOTE` 保留为编辑模式子模式，channel 选择后续改进。

### 6. 向后兼容

```gdscript
func set_editing(enabled: bool) -> void:
    set_mode(Mode.EDITING if enabled else Mode.PLAYING)

func is_editing() -> bool:
    return _mode == Mode.EDITING

func is_playing() -> bool:
    return _mode == Mode.PLAYING
```

## 涉及文件

| 文件 | 变更 |
|------|------|
| `piano_roll.gd` | Mode 枚举；set_mode()；菜单按模式重建；标注仅 FEEDBACK 模式绘制 |
| `piano_roll_actions.gd` | 拆分菜单构建；菜单 ID 分段；移除 ANNOTATE 逻辑 |
| `clef_station.gd` | 适配 set_mode() API；工具栏三按钮 ButtonGroup |
| `edit_bar.gd` | 新增播放/反馈按钮 |

## 不改动

- `midi_stream_player.gd` — 播放逻辑不受模式影响
- `editor_player.gd` — 同上
- `_annotations`、`_muted_indices` 数据结构保持不变
