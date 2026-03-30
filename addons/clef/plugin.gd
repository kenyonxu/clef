@tool
extends EditorPlugin

const _MENU_COMPOSE: int = 0
const _MENU_EXPORT: int = 1
const _SUBMENU_NAME: String = "Clef Utility"

var _submenu: PopupMenu = null
var _file_context_menu: ClefFileContextMenu
var _import_plugin: MidiImportPlugin
var _inspector_plugin: MidiInspectorPlugin
var _main_screen: ClefStation = null
var _bridge: RefCounted = null


func _enter_tree() -> void:
	_submenu = PopupMenu.new()
	_submenu.name = "ClefUtilityMenu"
	_submenu.add_item("Compose MIDI from JSON...", _MENU_COMPOSE)
	_submenu.add_item("Export MIDI to JSON...", _MENU_EXPORT)
	_submenu.id_pressed.connect(_on_submenu_id_pressed)
	add_tool_submenu_item(_SUBMENU_NAME, _submenu)
	_import_plugin = MidiImportPlugin.new()
	add_import_plugin(_import_plugin)
	_inspector_plugin = MidiInspectorPlugin.new()
	add_inspector_plugin(_inspector_plugin)
	_file_context_menu = ClefFileContextMenu.new()
	add_context_menu_plugin(EditorContextMenuPlugin.CONTEXT_SLOT_FILESYSTEM, _file_context_menu)
	# Clef Station 主屏幕
	_main_screen = ClefStation.new()
	_main_screen.name = "ClefStation"
	EditorInterface.get_editor_main_screen().add_child(_main_screen)
	_bridge = load("res://addons/clef/editor/clef_station_editor_bridge.gd").new()
	_main_screen.set_bridge(_bridge)
	_make_visible(false)
	_register_project_settings()


func _exit_tree() -> void:
	if _main_screen != null:
		_main_screen.queue_free()
		_main_screen = null
	if _bridge != null:
		_bridge = null
	if _inspector_plugin != null:
		remove_inspector_plugin(_inspector_plugin)
		_inspector_plugin = null
	if _import_plugin != null:
		remove_import_plugin(_import_plugin)
		_import_plugin = null
	if _submenu != null:
		remove_tool_menu_item(_SUBMENU_NAME)
		_submenu.queue_free()
		_submenu = null
	if _file_context_menu != null:
		remove_context_menu_plugin(_file_context_menu)
		_file_context_menu = null


# ─── Main Screen ───────────────────────────────────────────

func _has_main_screen() -> bool:
	return true


func _make_visible(visible: bool) -> void:
	if _main_screen:
		_main_screen.visible = visible


func _get_plugin_name() -> String:
	return "Clef"


func _get_main_screen_icon() -> Texture2D:
	return EditorInterface.get_editor_theme().get_icon("AudioStreamPlayer", "EditorIcons")


# ─── Project Settings ──────────────────────────────────────

func _register_project_settings() -> void:
	var setting_name: String = "clef/default_soundfont"
	if not ProjectSettings.has_setting(setting_name):
		ProjectSettings.set_setting(setting_name, "")
	ProjectSettings.set_initial_value(setting_name, "")
	ProjectSettings.add_property_info({
		"name": setting_name,
		"type": TYPE_STRING,
		"hint": PROPERTY_HINT_GLOBAL_FILE,
		"hint_string": "*.sf2",
	})


# ─── Menu Actions ──────────────────────────────────────────

func _on_submenu_id_pressed(id: int) -> void:
	match id:
		_MENU_COMPOSE:
			_on_tool_menu_pressed()
		_MENU_EXPORT:
			_on_export_menu_pressed()


func _on_tool_menu_pressed() -> void:
	var paths: PackedStringArray = EditorInterface.get_selected_paths()
	if paths.is_empty():
		_show_error("请先在文件系统面板中选择一个 JSON 文件")
		return

	var json_path: String = paths[0]
	if not json_path.ends_with(".json"):
		_show_error("选中的文件不是 .json 文件：" + json_path)
		return

	if not FileAccess.file_exists(json_path):
		_show_error("文件不存在：" + json_path)
		return

	var file := FileAccess.open(json_path, FileAccess.READ)
	if file == null:
		_show_error("无法读取文件：" + json_path + "\n" + str(FileAccess.get_open_error()))
		return

	var json_text: String = file.get_as_text()

	var result := MidiComposerConverter.from_json_string(json_text)
	if not result.ok:
		_show_error("JSON 转换失败：" + result.error_message)
		return

	var midi_bytes: PackedByteArray = MidiWriter.encode(result.midi_data)

	# 弹出保存对话框
	var dialog := EditorFileDialog.new()
	dialog.file_mode = EditorFileDialog.FILE_MODE_SAVE_FILE
	dialog.access = EditorFileDialog.ACCESS_RESOURCES
	dialog.title = "保存 MIDI"
	dialog.filters = PackedStringArray(["*.mid ; MIDI 文件"])
	dialog.current_dir = json_path.get_base_dir()
	dialog.current_file = json_path.get_file().get_basename() + ".mid"
	dialog.file_selected.connect(func(path: String) -> void:
		var out_file := FileAccess.open(path, FileAccess.WRITE)
		if out_file == null:
			_show_error("无法写入 MIDI 文件：" + path)
			return
		out_file.store_buffer(midi_bytes)
		out_file.close()
		EditorInterface.get_resource_filesystem().scan()
		EditorInterface.get_base_control().remove_child(dialog)
		dialog.queue_free()
	)
	EditorInterface.get_base_control().add_child(dialog)
	dialog.popup_centered(Vector2i(800, 500))


func _on_export_menu_pressed() -> void:
	var paths: PackedStringArray = EditorInterface.get_selected_paths()
	if paths.is_empty():
		_show_error("请先在文件系统面板中选择 .mid 或 .tres 文件")
		return

	var input_path: String = paths[0]
	if not (input_path.ends_with(".mid") or input_path.ends_with(".tres")):
		_show_error("不支持的文件格式，请选择 .mid 或 .tres 文件")
		return

	if not FileAccess.file_exists(input_path):
		_show_error("文件不存在：" + input_path)
		return

	# 读取 MidiData
	var midi_data: MidiData = null
	if input_path.ends_with(".tres"):
		var res = load(input_path)
		if res == null or not res is MidiResource:
			_show_error("无法加载 MidiResource：" + input_path)
			return
		midi_data = res.get_midi_data()
	else:
		var file := FileAccess.open(input_path, FileAccess.READ)
		if file == null:
			_show_error("无法读取文件：" + input_path)
			return
		var bytes := file.get_buffer(file.get_length())
		var result := MidiReader.from_bytes(bytes)
		if not result.ok:
			_show_error("MIDI 解析失败：" + result.error_message)
			return
		midi_data = result.midi_data

	if midi_data == null:
		_show_error("无法获取 MIDI 数据")
		return

	# 转换为 JSON
	var json_text: String = MidiComposerConverter.to_json_string(midi_data)

	# 弹出保存对话框
	var dialog := EditorFileDialog.new()
	dialog.file_mode = EditorFileDialog.FILE_MODE_SAVE_FILE
	dialog.access = EditorFileDialog.ACCESS_RESOURCES
	dialog.title = "导出 JSON"
	dialog.filters = PackedStringArray(["*.json ; JSON 文件"])
	dialog.current_dir = input_path.get_base_dir()
	dialog.current_file = input_path.get_file().get_basename() + ".json"
	dialog.file_selected.connect(func(path: String) -> void:
		var file := FileAccess.open(path, FileAccess.WRITE)
		if file == null:
			_show_error("无法写入文件：" + path)
			return
		file.store_string(json_text)
		file.close()
		EditorInterface.get_resource_filesystem().scan()
		EditorInterface.get_base_control().remove_child(dialog)
		dialog.queue_free()
	)
	EditorInterface.get_base_control().add_child(dialog)
	dialog.popup_centered(Vector2i(800, 500))


func _show_error(message: String) -> void:
	var dialog := AcceptDialog.new()
	dialog.dialog_text = message
	dialog.title = "Clef"
	dialog.transient = true
	EditorInterface.get_base_control().add_child(dialog)
	dialog.popup_centered(Vector2i(400, 150))
	dialog.confirmed.connect(dialog.queue_free)
	dialog.close_requested.connect(dialog.queue_free)
