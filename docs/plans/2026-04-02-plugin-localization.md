# Plugin Localization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add full i18n support to the Clef editor plugin using Godot 4.6's built-in TranslationDomain system, with zh_CN as the first translated language.

**Architecture:** A static helper class `ClefL10n` wraps a custom `TranslationDomain` named `"clef"`. The domain is initialized in `plugin.gd`'s `_enter_tree()` and cleaned up in `_exit_tree()`. All plugin scripts call `ClefL10n.t("key")` to get translated strings. Source keys are English; translations live in CSV files under `addons/clef/locales/`.

**Tech Stack:** GDScript, Godot 4.6 TranslationServer / TranslationDomain / Translation (CSV format)

**Reference:** `docs/plugin-localization.md` — design document with API details

---

## String inventory

| Category | Count | Files |
|----------|-------|-------|
| Error/validation messages | ~50 | plugin.gd, clef_file_context_menu.gd, converter.gd |
| UI buttons/labels/tooltips | ~30 | transport_bar, clef_station, mini_mixer, midi_monitor, soundfont_browser |
| FileDialog titles/filters | ~10 | plugin.gd, clef_file_context_menu.gd, midi_inspector_plugin.gd |
| Plugin metadata | 2 | plugin.cfg |
| **Total user-visible** | **~92** | **18 files** |

**Excluded:** `push_error`/`push_warning` debug strings (keep English), GM instrument names (standard English terms), emoji icon strings.

---

### Task 1: Create ClefL10n helper class

**Files:**
- Create: `addons/clef/editor/clef_l10n.gd`

**Step 1: Create the helper class**

```gdscript
## Localization helper for the Clef editor plugin.
## Wraps a custom TranslationDomain so all plugin scripts can call ClefL10n.t().
@tool
class_name ClefL10n
extends RefCounted

const DOMAIN_NAME: StringName = &"clef"

var _domain: TranslationDomain


func _init() -> void:
	_domain = TranslationServer.get_or_add_domain(DOMAIN_NAME)
	_domain.set_locale_override(TranslationServer.get_tool_locale())


func setup() -> void:
	"""Scan locales/ directory and load all .translation files."""
	var dir := DirAccess.open("res://addons/clef/locales/")
	if dir == null:
		return
	dir.list_dir_begin()
	var file_name := dir.get_next()
	while file_name != "":
		if file_name.ends_with(".translation"):
			var translation = load("res://addons/clef/locales/" + file_name)
			if translation is Translation:
				_domain.add_translation(translation)
		file_name = dir.get_next()
	dir.list_dir_end()


func cleanup() -> void:
	if _domain:
		_domain.clear()
		if TranslationServer.has_domain(DOMAIN_NAME):
			TranslationServer.remove_domain(DOMAIN_NAME)
		_domain = null


func t(message: String, context: String = "") -> String:
	"""Translate a message using the clef domain. Falls back to message itself."""
	if _domain:
		return _domain.translate(message, context)
	return message


func refresh_locale() -> void:
	"""Re-sync with editor locale (call on locale change)."""
	if _domain:
		_domain.set_locale_override(TranslationServer.get_tool_locale())
```

**Step 2: Verify the file was created correctly**

Run: `godot --headless --script addons/clef/tests/test_l10n_helper.gd`
(generated in Task 6)

---

### Task 2: Integrate ClefL10n into plugin.gd

**Files:**
- Modify: `addons/clef/plugin.gd`

**Step 1: Add L10n initialization to _enter_tree()**

In `plugin.gd`, add a member variable and wire up the helper:

```gdscript
# Add near the top, after existing var declarations:
var _l10n: ClefL10n = null
```

At the **beginning** of `_enter_tree()`, before any other setup:

```gdscript
func _enter_tree() -> void:
	_l10n = ClefL10n.new()
	_l10n.setup()
	# ... rest of existing code unchanged
```

At the **beginning** of `_exit_tree()`, before any other cleanup:

```gdscript
func _exit_tree() -> void:
	if _l10n:
		_l10n.cleanup()
		_l10n = null
	# ... rest of existing cleanup unchanged
```

**Step 2: Verify plugin loads without errors**

Run: `godot --headless --quit`
Expected: Clean exit, no errors in console output.

---

### Task 3: Create zh_CN CSV translation file

**Files:**
- Create: `addons/clef/locales/clef.zh_CN.csv`

**Step 1: Create the locales directory**

```bash
mkdir -p addons/clef/locales
```

**Step 2: Create the CSV file with all keys**

The CSV uses the first column as keys, subsequent columns as locale translations.
Column headers: `keys,zh_CN`

```csv
keys,zh_CN
"Play","播放"
"Stop","停止"
"Pause","暂停"
"Loop","循环"
"No file loaded","未加载文件"
"Load MIDI","加载 MIDI"
"Export JSON","导出 JSON"
"Save MIDI","保存 MIDI"
"Export to JSON","导出为 JSON"
"Convert to MIDI","转换为 MIDI"
"Compose MIDI from JSON...","从 JSON 合成 MIDI..."
"Export MIDI to JSON...","导出 MIDI 为 JSON..."
"Clef Utility","Clef 工具"
"Search:","搜索："
"Name or number...","名称或编号..."
"Preset","音色"
"No matching results","无匹配结果"
"No soundfont loaded","未加载音色库"
"Range: %s","音域: %s"
"Velocity: %s","力度: %s"
"Sweet spot: %s","甜区: %s"
"Quality: %s","品质: %s"
"Layers: %d","层次: %d"
"Load a MIDI file to view piano roll","加载 MIDI 文件以查看钢琴卷帘"
"SF2 Browser","SF2 浏览器"
"Toggle Soundfont Browser panel","切换音色库浏览器面板"
"MIDI Monitor","MIDI 监控"
"Toggle MIDI Monitor panel","切换 MIDI 监控面板"
"Auto","自动"
"Auto-load last file on startup","启动时自动加载上次文件"
"Load .mid / .tres / .json file","加载 .mid / .tres / .json 文件"
"Toggle auto-scroll","切换自动滚动"
"Clear","清空"
"Clear event log","清空事件日志"
"Copy","复制"
"Copy event log to clipboard","复制事件日志到剪贴板"
"Ch:","通道:"
"All","全部"
"Channel filter: All","通道过滤: 全部"
"Toggle %s filter","切换 %s 过滤"
"Events: %d | Notes: %d | %d/s","事件: %d | 音符: %d | %d/秒"
"(empty)","(空)"
"Channel %d","通道 %d"
"Channel %d volume","通道 %d 音量"
"Mute Channel %d","静音通道 %d"
"Master","主音量"
"Master volume","主音量"
"Channel %d: %s","通道 %d: %s"
"Please configure default Soundfont","请配置默认 Soundfont"
"Preview MIDI playback","预览播放 MIDI"
"Export MIDI resource to Clef JSON v2.0 format (for LLM composition)","将 MIDI 资源导出为 Clef JSON v2.0 格式（供 LLM 编曲使用）"
"Select a JSON file in the FileSystem panel first","请先在文件系统面板中选择一个 JSON 文件"
"Selected file is not a .json file: ","选中的文件不是 .json 文件："
"File not found: ","文件不存在："
"Cannot read file: ","无法读取文件："
"JSON conversion failed: ","JSON 转换失败："
"Cannot write MIDI file: ","无法写入 MIDI 文件："
"Select a .mid or .tres file in the FileSystem panel first","请先在文件系统面板中选择 .mid 或 .tres 文件"
"Unsupported file format, please select a .mid or .tres file","不支持的文件格式，请选择 .mid 或 .tres 文件"
"Cannot load MidiResource: ","无法加载 MidiResource："
"MIDI parse failed: ","MIDI 解析失败："
"Cannot get MIDI data","无法获取 MIDI 数据"
"Cannot write file: ","无法写入文件："
"File not found","文件未找到"
"Failed to load .tres","加载 .tres 失败"
"Unsupported format","不支持的格式"
"*.mid ; MIDI Files","*.mid ; MIDI 文件"
"*.json ; JSON Files","*.json ; JSON 文件"
"MIDI Resource","MIDI 资源"
"MIDI playback engine with SF2 synthesis and CC/pitchbend support","MIDI 播放引擎，支持 SF2 音色合成与 CC/弯音控制"
```

**Step 3: Import the CSV in Godot editor**

In the Godot editor:
1. Go to **Project > Project Settings > Localization > Translations**
2. Click **Add** and select `addons/clef/locales/clef.zh_CN.csv`
3. Godot will generate `addons/clef/locales/clef.zh_CN.translation`
4. Commit the generated `.translation` file

**Step 4: Commit**

```bash
git add addons/clef/locales/
git commit -m "feat(clef): add zh_CN translation CSV and generated .translation file"
```

---

### Task 4: Localize plugin.gd

**Files:**
- Modify: `addons/clef/plugin.gd`

**Step 1: Replace hardcoded strings with ClefL10n.t() calls**

Replace each hardcoded string. Example changes:

```gdscript
# Line 6 — submenu name constant becomes a key
# Change: const _SUBMENU_NAME: String = "Clef Utility"
# To: (remove the constant, use t() inline)

# Line 19-20 — menu items
_submenu.add_item(_l10n.t("Compose MIDI from JSON..."), _MENU_COMPOSE)
_submenu.add_item(_l10n.t("Export MIDI to JSON..."), _MENU_EXPORT)
add_tool_submenu_item(_l10n.t("Clef Utility"), _submenu)
```

Replace all `_show_error(...)` calls:

```gdscript
# Line 107
_show_error(_l10n.t("Select a JSON file in the FileSystem panel first"))

# Line 112
_show_error(_l10n.t("Selected file is not a .json file: ") + json_path)

# Line 116
_show_error(_l10n.t("File not found: ") + json_path)

# Line 121
_show_error(_l10n.t("Cannot read file: ") + json_path + "\n" + str(FileAccess.get_open_error()))

# Line 128
_show_error(_l10n.t("JSON conversion failed: ") + result.error_message)

# Line 137-138 — FileDialog
dialog.title = _l10n.t("Save MIDI")
dialog.filters = PackedStringArray([_l10n.t("*.mid ; MIDI Files")])

# Line 148
_show_error(_l10n.t("Cannot write MIDI file: ") + path)

# Line 163
_show_error(_l10n.t("Select a .mid or .tres file in the FileSystem panel first"))

# Line 168
_show_error(_l10n.t("Unsupported file format, please select a .mid or .tres file"))

# Line 172
_show_error(_l10n.t("File not found: ") + input_path)

# Line 180
_show_error(_l10n.t("Cannot load MidiResource: ") + input_path)

# Line 186
_show_error(_l10n.t("Cannot read file: ") + input_path)

# Line 191
_show_error(_l10n.t("MIDI parse failed: ") + result.error_message)

# Line 196
_show_error(_l10n.t("Cannot get MIDI data"))

# Line 206-207 — FileDialog
dialog.title = _l10n.t("Export JSON")
dialog.filters = PackedStringArray([_l10n.t("*.json ; JSON Files")])

# Line 217
_show_error(_l10n.t("Cannot write file: ") + path)
```

Remove the `_SUBMENU_NAME` constant since it's now localized. Update `_exit_tree()`:

```gdscript
remove_tool_menu_item(_l10n.t("Clef Utility"))
```

**Step 2: Verify in editor**

Run Godot editor, activate Clef plugin, check:
- Top menu shows localized "Clef 工具" submenu (if editor is zh_CN)
- Tool menu items show Chinese text
- JSON conversion error dialogs show Chinese messages

**Step 3: Commit**

```bash
git add addons/clef/plugin.gd
git commit -m "feat(clef): localize plugin.gd menu items and error messages"
```

---

### Task 5: Localize clef_file_context_menu.gd

**Files:**
- Modify: `addons/clef/editor/clef_file_context_menu.gd`

**Step 1: Add ClefL10n dependency and replace strings**

The file context menu is created via `ClefFileContextMenu.new()` in plugin.gd. Since it's not in the scene tree initially, we need to pass the L10n helper or access it statically.

**Approach:** Add a `l10n` property that plugin.gd sets after construction.

In `plugin.gd`, after creating `_file_context_menu`:

```gdscript
_file_context_menu = ClefFileContextMenu.new()
_file_context_menu.l10n = _l10n
```

In `clef_file_context_menu.gd`, add:

```gdscript
var l10n: ClefL10n
```

Then replace all hardcoded strings with `l10n.t(...)`:

```gdscript
# Line 20 — menu item
func _populate_menu(menu: PopupMenu, file_path: String) -> void:
	if file_path.ends_with(".json"):
		menu.add_icon_item(...)
		menu.set_item_text(1, l10n.t("Convert to MIDI"))
	elif file_path.ends_with(".mid") or file_path.ends_with(".tres"):
		menu.add_icon_item(...)
		menu.set_item_text(1, l10n.t("Export to JSON"))
```

Replace all error messages and FileDialog strings similarly to Task 4.

**Step 2: Verify context menu**

Right-click a `.json` and `.mid` file in the FileSystem panel. Verify Chinese menu items and error messages.

**Step 3: Commit**

```bash
git add addons/clef/editor/clef_file_context_menu.gd addons/clef/plugin.gd
git commit -m "feat(clef): localize file context menu strings"
```

---

### Task 6: Localize midi_inspector_plugin.gd

**Files:**
- Modify: `addons/clef/midi_inspector_plugin.gd`

**Step 1: Add L10n and replace strings**

The inspector plugin is created via `MidiInspectorPlugin.new()` in plugin.gd. Set `l10n` after creation:

```gdscript
# plugin.gd
_inspector_plugin = MidiInspectorPlugin.new()
_inspector_plugin.l10n = _l10n
```

In `midi_inspector_plugin.gd`, add `var l10n: ClefL10n` and replace:

```gdscript
# Line 49-50 — Play button
_btn_play.text = "▶ " + l10n.t("Play")
_btn_play.tooltip_text = l10n.t("Preview MIDI playback")

# Line 57-58 — Stop button
_btn_stop.text = "⏹ " + l10n.t("Stop")
_btn_stop.tooltip_text = l10n.t("Stop")

# Line 65-66 — Pause button (keep icon)
_btn_pause.tooltip_text = l10n.t("Pause")

# Line 90 — Warning
_warning_label.text = l10n.t("Please configure default Soundfont")

# Line 100-101 — Export JSON button
_btn_export.text = l10n.t("Export JSON")
_btn_export.tooltip_text = l10n.t("Export MIDI resource to Clef JSON v2.0 format (for LLM composition)")

# Line 243-244 — FileDialog
dialog.title = l10n.t("Export JSON")
dialog.filters = PackedStringArray([l10n.t("*.json ; JSON Files")])
```

**Step 2: Verify in inspector**

Select a `.tres` MidiResource file in the FileSystem panel. Check the Inspector shows localized buttons and tooltips.

**Step 3: Commit**

```bash
git add addons/clef/midi_inspector_plugin.gd addons/clef/plugin.gd
git commit -m "feat(clef): localize inspector plugin UI strings"
```

---

### Task 7: Localize clef_station.gd and transport_bar.gd

**Files:**
- Modify: `addons/clef/editor/clef_station.gd`
- Modify: `addons/clef/editor/transport_bar/transport_bar.gd`

**Step 1: Add l10n property to both classes**

Both are created in plugin.gd / clef_station.gd. Pass `l10n` through:

In `clef_station.gd`:

```gdscript
var l10n: ClefL10n
```

Pass to TransportBar (if created programmatically):

```gdscript
_transport_bar.l10n = l10n
```

In `transport_bar.gd`:

```gdscript
var l10n: ClefL10n

func _build_ui() -> void:
	_file_label.text = l10n.t("No file loaded")
	_btn_play.text = l10n.t("Play")
	_btn_play.tooltip_text = l10n.t("Play")
	_btn_pause.text = l10n.t("Pause")
	_btn_pause.tooltip_text = l10n.t("Pause")
	_btn_stop.text = l10n.t("Stop")
	_btn_stop.tooltip_text = l10n.t("Stop")
	_loop_btn.text = l10n.t("Loop")
	_loop_btn.tooltip_text = l10n.t("Loop")
```

In `clef_station.gd`, replace:

```gdscript
# Line 77-88 — Toolbar buttons
_btn_sf2.text = l10n.t("SF2 Browser")
_btn_sf2.tooltip_text = l10n.t("Toggle Soundfont Browser panel")
_btn_monitor.text = l10n.t("MIDI Monitor")
_btn_monitor.tooltip_text = l10n.t("Toggle MIDI Monitor panel")

# Line 142-152 — Load/Auto buttons
_btn_load.text = l10n.t("Load MIDI")
_btn_load.tooltip_text = l10n.t("Load .mid / .tres / .json file")
_btn_auto.text = l10n.t("Auto")
_btn_auto.tooltip_text = l10n.t("Auto-load last file on startup")

# Line 295-296 — FileDialog
dialog.title = l10n.t("Load MIDI")
```

**Step 2: Verify main screen**

Open the Clef main screen in the editor. Check toolbar buttons and transport bar.

**Step 3: Commit**

```bash
git add addons/clef/editor/clef_station.gd addons/clef/editor/transport_bar/transport_bar.gd
git commit -m "feat(clef): localize ClefStation and TransportBar"
```

---

### Task 8: Localize mini_mixer.gd and midi_monitor.gd

**Files:**
- Modify: `addons/clef/editor/mini_mixer/mini_mixer.gd`
- Modify: `addons/clef/editor/midi_monitor/midi_monitor.gd`

**Step 1: Mini mixer — add l10n and replace strings**

In `mini_mixer.gd`, add `var l10n: ClefL10n` and replace:

```gdscript
# Channel labels — use t() with format
channel_label.text = "Ch%d" % (i + 1)  # Keep "Ch" as technical abbreviation

# Tooltips
channel_btn.tooltip_text = l10n.t("Channel %d") % (i + 1)
volume_slider.tooltip_text = l10n.t("Channel %d volume") % (i + 1)
mute_btn.tooltip_text = l10n.t("Mute Channel %d") % (i + 1)
mute_btn.text = l10n.t("M")  # "M" is universal, but keep consistent

# Master
_master_label.text = l10n.t("Master")
_master_slider.tooltip_text = l10n.t("Master volume")

# Solo tooltip
solo_btn.tooltip_text = l10n.t("Channel %d") % (i + 1)

# Channel info tooltip
channel_btn.tooltip_text = l10n.t("Channel %d: %s") % [i + 1, instrument_name]
```

**Step 2: MIDI monitor — add l10n and replace strings**

In `midi_monitor.gd`, add `var l10n: ClefL10n` and replace:

```gdscript
# Line 86 — Channel label
_ch_label.text = l10n.t("Ch:")

# Line 90-94 — All button
_all_btn.text = l10n.t("All")
_all_btn.tooltip_text = l10n.t("Channel filter: All")

# Line 104 — Toggle filter tooltip
filter_btn.tooltip_text = l10n.t("Toggle %s filter") % filter_name

# Line 111-115 — Auto button
_auto_btn.text = l10n.t("Auto")
_auto_btn.tooltip_text = l10n.t("Toggle auto-scroll")

# Line 125-127 — Clear button
_clear_btn.text = l10n.t("Clear")
_clear_btn.tooltip_text = l10n.t("Clear event log")

# Line 132-134 — Copy button
_copy_btn.text = l10n.t("Copy")
_copy_btn.tooltip_text = l10n.t("Copy event log to clipboard")

# Line 326 — Stats
_stats_label.text = l10n.t("Events: %d | Notes: %d | %d/s") % [event_count, note_count, rate]

# Line 347 — Empty clipboard
_display_toast(l10n.t("(empty)"))
```

**Step 3: Verify both panels**

Open the MIDI Monitor and check channel buttons, tooltips, and stats. Open a MIDI file and check the mini mixer labels.

**Step 4: Commit**

```bash
git add addons/clef/editor/mini_mixer/mini_mixer.gd addons/clef/editor/midi_monitor/midi_monitor.gd
git commit -m "feat(clef): localize MiniMixer and MidiMonitor"
```

---

### Task 9: Localize soundfont_browser.gd and piano_roll.gd

**Files:**
- Modify: `addons/clef/editor/soundfont_browser/soundfont_browser.gd`
- Modify: `addons/clef/editor/piano_roll/piano_roll.gd`

**Step 1: Soundfont browser — add l10n and replace strings**

```gdscript
var l10n: ClefL10n

# Line 28-32 — Search bar
search_label.text = l10n.t("Search:")
_search_line.placeholder_text = l10n.t("Name or number...")

# Line 44 — Tree column
_tree.set_column_title(0, l10n.t("Preset"))

# Line 114 — Empty state
_empty_label.text = l10n.t("No matching results")

# Line 117 — Default empty state
_empty_label.text = l10n.t("No soundfont loaded")

# Line 159-163 — Info panel
_range_label.text = l10n.t("Range: %s") % range_str
_velocity_label.text = l10n.t("Velocity: %s") % vel_str
_sweet_label.text = l10n.t("Sweet spot: %s") % sweet_str
_quality_label.text = l10n.t("Quality: %s") % quality_str
_layers_label.text = l10n.t("Layers: %d") % layers
```

**Step 2: Piano roll — add l10n and replace strings**

```gdscript
var l10n: ClefL10n

# Line 224 — Placeholder
_placeholder_label.text = l10n.t("Load a MIDI file to view piano roll")
```

**Step 3: Verify**

Open the SF2 Browser panel. Check search bar, tree column headers, info panel. Open a MIDI file and check the piano roll placeholder.

**Step 4: Commit**

```bash
git add addons/clef/editor/soundfont_browser/ addons/clef/editor/piano_roll/
git commit -m "feat(clef): localize SoundfontBrowser and PianoRoll"
```

---

### Task 10: Localize converter.gd

**Files:**
- Modify: `addons/clef/converter.gd`

**Step 1: Add static access pattern**

`converter.gd` is a class used by both the plugin and potentially at runtime. It returns error messages via `ConvertResult.error_message`. The cleanest approach: accept an optional `l10n` parameter or use a static reference.

**Approach:** Add a static `l10n` property on the Converter class, set from plugin.gd.

In `converter.gd`:

```gdscript
class_name MidiComposerConverter
extends RefCounted

## Set by the editor plugin during init. Null at runtime.
static var l10n: ClefL10n = null
```

Add a private helper:

```gdscript
static func _t(message: String) -> String:
	if l10n:
		return l10n.t(message)
	return message
```

Replace all error strings. Examples:

```gdscript
# Line 28
return ConvertResult.error("JSON parse failed: invalid JSON format")

# Line 33
return ConvertResult.error("JSON parse failed: root element must be an object")

# Line 135
return ConvertResult.error("format_version must be a string")

# Line 137
return ConvertResult.error("Unsupported format_version: '%s', currently supporting '1.0', '1.1', and '2.0'" % version)

# Line 140
return ConvertResult.error("Missing required field: tempo")
# ... (all ~25 validation error strings)
```

In `plugin.gd` `_enter_tree()`, after creating `_l10n`:

```gdscript
MidiComposerConverter.l10n = _l10n
```

In `plugin.gd` `_exit_tree()`:

```gdscript
MidiComposerConverter.l10n = null
```

**Step 2: Verify**

Trigger a JSON conversion error (e.g., select an invalid JSON file). Check the error dialog shows Chinese text.

**Step 3: Commit**

```bash
git add addons/clef/converter.gd addons/clef/plugin.gd
git commit -m "feat(clef): localize converter validation error messages"
```

---

### Task 11: Localize editor_player.gd and midi_import_plugin.gd

**Files:**
- Modify: `addons/clef/editor/editor_player/editor_player.gd`
- Modify: `addons/clef/midi_import_plugin.gd`

**Step 1: editor_player.gd — localize error signals**

```gdscript
var l10n: ClefL10n

# Replace signal error strings
# Line 24: "File not found" → l10n.t("File not found")
# Line 32: "Failed to load .tres" → l10n.t("Failed to load .tres")
# Line 37: "Cannot read file" → l10n.t("Cannot read file")
# Line 50: "Cannot read file" → l10n.t("Cannot read file")
# Line 60: "Unsupported format" → l10n.t("Unsupported format")
```

Pass `l10n` from clef_station.gd or wherever EditorPlayer is instantiated.

**Step 2: midi_import_plugin.gd — localize visible name**

```gdscript
# Line 11 — importer visible name
func _get_importer_name() -> String:
	return "Clef MIDI"  # Keep plugin name, no need to translate

func _get_visible_name() -> String:
	return "MIDI Resource"  # This is a resource type name, keep English

func _get_recognized_extensions() -> PackedStringArray:
	return PackedStringArray(["mid"])
```

Note: The `push_error` strings in this file (lines 45, 51) are debug-only and should **not** be localized.

**Step 3: Commit**

```bash
git add addons/clef/editor/editor_player/ addons/clef/midi_import_plugin.gd
git commit -m "feat(clef): localize editor player and import plugin"
```

---

### Task 12: Wire l10n through the component tree

**Files:**
- Modify: `addons/clef/plugin.gd`
- Modify: `addons/clef/editor/clef_station.gd`

**Step 1: Ensure l10n propagates to all child components**

In `plugin.gd` `_enter_tree()`:

```gdscript
_l10n = ClefL10n.new()
_l10n.setup()

# Pass l10n to all components that need it
_inspector_plugin = MidiInspectorPlugin.new()
_inspector_plugin.l10n = _l10n

_file_context_menu = ClefFileContextMenu.new()
_file_context_menu.l10n = _l10n

# ClefStation gets l10n after construction
_main_screen = ClefStation.new()
_main_screen.l10n = _l10n  # ADD THIS LINE
```

In `clef_station.gd`, propagate to child panels:

```gdscript
func _build_panels() -> void:
	# When creating transport bar:
	_transport_bar.l10n = l10n

	# When creating midi monitor:
	_midi_monitor.l10n = l10n

	# When creating mini mixer:
	_mini_mixer.l10n = l10n

	# When creating soundfont browser:
	_sf2_browser.l10n = l10n

	# When creating piano roll:
	_piano_roll.l10n = l10n

	# When creating editor player:
	_editor_player.l10n = l10n
```

**Step 2: Full integration test**

1. Open Godot editor with Clef plugin active
2. Switch editor language to zh_CN (Editor > Editor Settings > Interface > Editor Language)
3. Verify all panels show Chinese text:
   - Clef main screen toolbar
   - Transport bar buttons
   - MIDI Monitor labels and buttons
   - SF2 Browser search bar and info panel
   - Inspector plugin buttons
   - File context menu items
   - Error dialogs
4. Switch back to English and verify English text

**Step 3: Commit**

```bash
git add addons/clef/
git commit -m "feat(clef): complete localization integration — all panels and error messages"
```

---

### Task 13: Update plugin.cfg description

**Files:**
- Modify: `addons/clef/plugin.cfg`

**Step 1: The description in plugin.cfg is the plugin marketplace description**

This is typically kept in English as it targets the Godot asset library. No change needed.

However, if a localized description is desired later, it can be handled via the asset library's own localization mechanism — not via TranslationServer.

**Step 2: No commit needed** — skip this task.

---

### Task 14: Final verification and cleanup

**Step 1: Grep for remaining hardcoded user-visible Chinese strings**

```bash
grep -rn "[\x{4e00}-\x{9fff}]" addons/clef/ --include="*.gd" | grep -v "push_error\|push_warning\|# "
```

This finds Chinese characters in GDScript files, excluding comments and debug logs.

**Expected result:** No remaining Chinese strings in user-facing code (comments and push_error are OK).

**Step 2: Grep for hardcoded English UI strings that should be localized**

```bash
grep -rn '"Play"\|"Stop"\|"Pause"\|"Loop"\|"Export"\|"Load"\|"Save"\|"Search"' addons/clef/ --include="*.gd"
```

**Expected result:** All matches should be inside `l10n.t(...)` calls, not bare string assignments.

**Step 3: Test with no translation loaded**

Disable the zh_CN translation in Project Settings. Verify all strings fall back to English keys (the behavior when no translation matches).

**Step 4: Final commit if any cleanup is needed**

```bash
git add -A addons/clef/
git commit -m "fix(clef): localization cleanup — remove remaining hardcoded strings"
```

---

## Notes for the implementer

1. **Fallback behavior:** When `l10n` is `null` (e.g., at runtime in an exported game), `ClefL10n.t()` returns the key itself. This means English keys serve as built-in English strings.

2. **Format strings:** Strings with `%s`, `%d` placeholders must use the same placeholder positions in all translations. The `.format()` call happens after `t()` returns the translated string.

3. **GM instrument names:** The 128 GM names in `mini_mixer.gd` and `piano_roll.gd` are standard English MIDI terms. Do not translate them — they are universal identifiers.

4. **push_error / push_warning:** These are debug messages visible in the editor Output panel. Keep them in English for debugging consistency across locales.

5. **Translation file generation:** After editing the CSV in Godot (Project Settings > Localization), the `.translation` file must be re-generated and committed.
