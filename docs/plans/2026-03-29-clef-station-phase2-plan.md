# Clef Station Phase 2 — 音色浏览器 Implementation Plan

> **Status:** COMPLETED (2026-03-29)
> **Commit:** `a8c22c5` feat: add SoundfontBrowser panel with patch list, search, and audition (Phase 2)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现左栏音色浏览器，支持加载 SF2 profile JSON、按 GM 分类浏览 Patch 列表、搜索过滤、点击试听、显示 Patch 详细信息。

**Architecture:** 新建 `SoundfontBrowser` 控件替换左栏占位。通过 `sf2_profiler.py` 生成 profile JSON 作为数据源。试听使用独立的 `ClefBank` + `ClefVoice`（不依赖 MidiStreamPlayer），在编辑器中创建临时 AudioStreamPlayer 播放单音。

**Tech Stack:** GDScript, Tree 控件, LineEdit 搜索, Sf2Reader/ClefBank/ClefVoice

---

### Task 1: 创建 PatchData 数据类

**Files:**
- Create: `addons/clef/editor/patch_data.gd`

**Step 1: 创建数据类**

```gdscript
## SF2 Patch 数据模型
class_name PatchData extends RefCounted

var preset_index: int
var name: String
var gm_category: String
var key_range: Vector2i  ## [lo, hi]
var vel_range: Vector2i  ## [lo, hi]
var sweet_spot: Vector2i  ## [lo, hi]
var vel_layers: int
var avg_attack: float
var avg_release: float
var quality: String
var characteristics: Array[String]


static func from_dict(preset_index: int, data: Dictionary) -> PatchData:
	var pd := PatchData.new()
	pd.preset_index = preset_index
	pd.name = data.get("name", "")
	pd.gm_category = _preset_to_category(preset_index)
	pd.key_range = Vector2i(data["key_range"][0], data["key_range"][1])
	pd.vel_range = Vector2i(data["vel_range"][0], data["vel_range"][1])
	var ss: Array = data.get("sweet_spot", [48, 84])
	pd.sweet_spot = Vector2i(ss[0], ss[1])
	pd.vel_layers = data.get("vel_layers", 0)
	pd.avg_attack = data.get("avg_attack", 0.0)
	pd.avg_release = data.get("avg_release", 0.0)
	pd.quality = data.get("quality", "")
	pd.characteristics = data.get("characteristics", [])
	return pd


## GM 标准分类 (每 8 个 preset 一组)
static func _preset_to_category(index: int) -> String:
	var categories := [
		"Piano", "Chromatic Percussion", "Organ", "Guitar",
		"Bass", "Strings", "Ensemble", "Brass",
		"Reed", "Pipe", "Synth Lead", "Synth Pad",
		"Synth Effects", "Ethnic", "Percussive", "Sound Effects",
	]
	return categories[mini(index / 8, categories.size() - 1)]


func format_range(range_v: Vector2i) -> String:
	return "%d-%d" % [range_v.x, range_v.y]
```

**Step 2: Commit**

```
feat: add PatchData model for soundfont browser
```

---

### Task 2: 创建 SoundfontBrowser 面板

**Files:**
- Create: `addons/clef/editor/soundfont_browser/soundfont_browser.gd`
- Modify: `addons/clef/editor/clef_station.gd` — 替换左栏占位

**Step 1: 创建 SoundfontBrowser 控件**

```gdscript
## 音色浏览器面板 — SF2 Patch 列表 + 搜索 + 试听 + 信息面板
@tool
class_name SoundfontBrowser
extends VBoxContainer

signal patch_selected(preset_index: int, patch: PatchData)

var _tree: Tree
var _search_line: LineEdit
var _info_panel: HBoxContainer
var _patches: Array[PatchData] = []
var _audition_player: Node = null  ## 临时播放节点
var _audition_bank: ClefBank = null
var _audition_timer: Timer = null


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_build_ui()


func _build_ui() -> void:
	# 搜索栏
	var search_bar := HBoxContainer.new()
	search_bar.add_theme_constant_override("separation", 4)
	var search_label := Label.new()
	search_label.text = "搜索:"
	search_label.custom_minimum_size = Vector2i(36, 0)
	search_bar.add_child(search_label)
	_search_line = LineEdit.new()
	_search_line.placeholder_text = "输入名称或编号..."
	_search_line.text_changed.connect(_on_search_changed)
	_search_line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search_bar.add_child(_search_line)
	add_child(search_bar)

	# Patch 列表
	_tree = Tree.new()
	_tree.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_tree.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_tree.hide_root = true
	_tree.columns = 1
	_tree.set_column_title(0, "Preset")
	_tree.item_selected.connect(_on_item_selected)
	_tree.item_activated.connect(_on_item_activated)  ## 双击试听
	add_child(_tree)

	# 信息面板
	_info_panel = HBoxContainer.new()
	_info_panel.custom_minimum_size = Vector2i(0, 60)
	_info_panel.alignment = BoxContainer.ALIGNMENT_BEGIN
	add_child(_info_panel)


func load_profile(json_path: String) -> bool:
	var file := FileAccess.open(json_path, FileAccess.READ)
	if file == null:
		return false
	var json := JSON.new()
	var err := json.parse(file.get_as_text())
	file.close()
	if err != OK:
		return false
	var data = json.get_data()
	if not data is Dictionary or not data.has("presets"):
		return false
	_patches.clear()
	for key in data["presets"]:
		var preset_index := int(key)
		_patches.append(PatchData.from_dict(preset_index, data["presets"][key]))
	_patches.sort_custom(func(a, b): return a.preset_index < b.preset_index)
	_populate_tree("")
	return true


func _populate_tree(filter_text: String) -> void:
	_tree.clear()
	var current_category: String = ""
	var category_root: TreeItem = null

	for patch in _patches:
		var matches := true
		if filter_text != "":
			var query := filter_text.to_lower()
			matches = query in patch.name.to_lower() or query in str(patch.preset_index)
		if not matches:
			continue

		# 创建分类根节点
		if patch.gm_category != current_category:
			current_category = patch.gm_category
			category_root = _tree.create_item()
			category_root.set_text(0, current_category)
			# 如果过滤后没有该分类的项，跳过空分类
		if category_root == null:
			category_root = _tree.create_item()

		var item := _tree.create_item(category_root)
		item.set_text(0, "%03d %s" % [patch.preset_index, patch.name])
		item.set_metadata(0, patch)


func _on_search_changed(text: String) -> void:
	_populate_tree(text)


func _on_item_selected() -> void:
	var item := _tree.get_selected()
	if item == null or item.get_metadata(0) == null:
		_update_info_panel(null)
		return
	var patch: PatchData = item.get_metadata(0)
	patch_selected.emit(patch.preset_index, patch)
	_update_info_panel(patch)


func _on_item_activated() -> void:
	var item := _tree.get_selected()
	if item == null or item.get_metadata(0) == null:
		return
	var patch: PatchData = item.get_metadata(0)
	_audition_patch(patch.preset_index)


func _update_info_panel(patch: PatchData) -> void:
	for child in _info_panel.get_children():
		child.queue_free()
	if patch == null:
		return
	var labels := [
		"音域: %s" % patch.format_range(patch.key_range),
		"力度: %s" % patch.format_range(patch.vel_range),
		"甜区: %s" % patch.format_range(patch.sweet_spot),
		"品质: %s" % patch.quality,
	]
	for text in labels:
		var lbl := Label.new()
		lbl.text = text
		lbl.add_theme_color_override("font_color", Color(0.8, 0.8, 0.8))
		_info_panel.add_child(lbl)


func _audition_patch(preset_index: int) -> void:
	if _audition_bank == null:
		return
	var inst_info: ClefInstrumentInfo = _audition_bank.get_instrument(preset_index, 60, 100, 0)
	if inst_info == null:
		return
	var voice := ClefVoice.new()
	_audition_player.add_child(voice)
	voice.start_note(inst_info, 0, 60, 100)
	voice.bus = "Master"
	# 1.5 秒后自动释放
	if _audition_timer != null:
		_audition_timer.stop()
		_audition_timer = _audition_timer if _audition_timer != null else Timer.new()
	if not _audition_timer.is_inside_tree():
		add_child(_audition_timer)
	_audition_timer.wait_time = 1.5
	_audition_timer.one_shot = true
	_audition_timer.timeout.connect(_stop_audition_voice.bind(voice))
		_audition_timer.start()


func _stop_audition_voice(voice: ClefVoice) -> void:
	if is_instance_valid(voice) and not voice.is_idle():
		voice.stop_note()
		# 等待释放完成后清理
		var t := create_tween()
		t.tween_callback(func(): if is_instance_valid(voice): voice.queue_free())


func setup_audition(sf2_path: String) -> void:
	if sf2_path == "":
		return
	if _audition_player == null:
		_audition_player = Node.new()
		_audition_player.name = "AuditionPlayer"
		add_child(_audition_player)
	if not FileAccess.file_exists(sf2_path):
		return
	var result := Sf2Reader.read_file(sf2_path)
	if result.ok:
		_audition_bank = ClefBank.new()
		_audition_bank.load_from_sf2(result.data)
```

**Step 2: 修改 clef_station.gd — 替换左栏占位**

在 `_build_layout()` 中，替换左栏的 Label 占位为 SoundfontBrowser：

```gdscript
# 在文件顶部添加 preload
const SoundfontBrowser = preload("res://addons/clef/editor/soundfont_browser/soundfont_browser.gd")

# 替换 _build_layout 中左栏部分：
# 删除原来的 _left_panel 创建代码，改为：
var left_container := VBoxContainer.new()
left_container.size_flags_vertical = Control.SIZE_EXPAND_FILL
left_container.custom_minimum_size = Vector2i(180, 0)
_style_panel_bg(left_container, Color(0.12, 0.12, 0.16))
var browser := SoundfontBrowser.new()
browser.patch_selected.connect(_on_patch_selected)
left_container.add_child(browser)
_split_main.add_child(left_container)
_left_panel = left_container
# 保存 browser 引用
var _soundfont_browser: SoundfontBrowser  # 添加到成员变量

# 在 _ready 末尾加载 profile：
var sf2_path: String = ProjectSettings.get_setting("clef/default_soundfont", "")
var profile_path: String = sf2_path.get_basename() + "_profile.json"
if profile_path != "":
	# 尝试在 SF2 同目录查找 profile
	var sf2_dir: String = sf2_path.get_base_dir()
	var full_profile := sf2_dir.path_join(profile_path)
	if not FileAccess.file_exists(full_profile):
		# 尝试生成
		var cmd := [ProjectSettings.globalize_path("res://.claude/skills/clef-compose/scripts/sf2_profiler.py"), sf2_path, "-o", full_profile]
		OS.execute("python", cmd)
	_soundfont_browser.load_profile(full_profile)
	_soundfont_browser.setup_audition(sf2_path)
```

**Step 3: 验证**

在 Godot 编辑器中重新加载，确认左栏显示 Tree 控件和搜索框。

**Step 4: Commit**

```
feat: add SoundfontBrowser panel with patch list, search, and audition
```

---

### Task 3: 试听功能验证与修复

**Files:**
- Modify: `addons/clef/editor/soundfont_browser/soundfont_browser.gd`

**Step 1: 验证试听流程**

试听需要 AudioServer 处于活动状态（编辑器运行时）。如果 `_audition_patch` 无法播放，检查：
- `_audition_player` 是否在场景树中
- `ClefVoice` 是否正确创建并播放
- `bus = "Master"` 是否有效

可能的问题：编辑器中 AudioServer 可能需要特定的 bus 设置。如果 `Master` bus 不可用，改用 `AudioServer.get_bus_name(0)` 获取第一个可用 bus。

**Step 2: Commit**

```
fix: verify and fix audition playback in editor context
```

---

### Task 4: Patch 选中联动与 UI 打磨

**Files:**
- Modify: `addons/clef/editor/soundfont_browser/soundfont_browser.gd`
- Modify: `addons/clef/editor/clef_station.gd`

**Step 1: 添加选中高亮**

为选中的 TreeItem 设置自定义字体颜色：

```gdscript
func _on_item_selected() -> void:
	var item := _tree.get_selected()
	if item == null or item.get_metadata(0) == null:
		_update_info_panel(null)
		return
	# 高亮选中项
	for cat_item in _tree.get_root().get_children():
		for patch_item in cat_item.get_children():
			patch_item.set_custom_color(0, Color(1, 1, 1))
	item.set_custom_color(0, Color(1.0, 0.85, 0.4))
	var patch: PatchData = item.get_metadata(0)
	patch_selected.emit(patch.preset_index, patch)
	_update_info_panel(patch)
```

**Step 2: 添加快捷键试听**

选中 Patch 后按 Enter 试听：

```gdscript
func _gui_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_ENTER:
		_audition_patch_selected()
```

**Step 3: 空状态提示**

当没有加载 profile 时显示提示信息：

```gdscript
func _show_empty_state() -> void:
	_tree.clear()
	var root := _tree.create_item()
	var item := _tree.create_item(root)
	item.set_text(0, "未加载音色库")
	item.set_custom_color(0, Color(0.5, 0.5, 0.5))
	item.set_selectable(false)
```

**Step 4: Commit**

```
feat: add patch selection highlight and keyboard audition
```

---

## 验收标准

Phase 2 完成后应满足：

1. 左栏显示 Tree 控件，按 GM 分类分组显示 Patch 列表 ✅
2. 搜索框可按名称或编号过滤 Patch ✅
3. 选中 Patch 显示信息面板（音域、力度、甜区、品质、层次） ✅
4. 双击或选中后按 Enter 可试听（播放 C4 约 1.5 秒） ✅
5. 无 SF2 profile 时显示空状态提示 ✅
6. 切换标签/重新加载插件无报错 ✅

## 实现笔记

### 与计划的偏差

1. **PatchData `Array[String]`**：JSON 解析返回普通 `Array`，无法赋值给 `Array[String]` 类型声明，改为 `Array`
2. **`set_selectable` API**：Godot 4.x 需要 column 参数，`set_selectable(false)` 改为 `set_selectable(0, false)`
3. **`KEY_RETURN`**：Godot 4.x 中不存在，改为 `KEY_ENTER`
4. **lambda 闭合括号**：`_audition_patch` 中 `connect(func():)` 的 `)` 缺失，`_cleanup_timer.start()` 被错误包含在 lambda 内部
5. **选中高亮**：遍历树重置所有项颜色会导致分组外音色无法恢复，改为追踪 `_selected_item` 引用
6. **字体色一致性**：重置选中色用 `Color(1,1,1)` 比主题默认色更亮，改为 `_tree.get_theme_color("font_color", "Tree")`
7. **信息面板背景**：添加 `PanelContainer` 包裹信息面板，用深色背景与列表区区分
8. **Profile 自动生成**：在 `_load_soundfont_profile()` 中，当 profile JSON 不存在时自动调用 `sf2_profiler.py` 生成

## 文件清单

| 操作 | 文件 |
|------|------|
| 新建 | `addons/clef/editor/patch_data.gd` |
| 新建 | `addons/clef/editor/soundfont_browser/soundfont_browser.gd` |
| 修改 | `addons/clef/editor/clef_station.gd` |
