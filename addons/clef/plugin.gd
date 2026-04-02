@tool
extends EditorPlugin

const _MENU_COMPOSE: int = 0
const _MENU_EXPORT: int = 1

var _submenu: PopupMenu = null
var _submenu_name: String = ""
var _file_context_menu: ClefFileContextMenu
var _import_plugin: MidiImportPlugin
var _inspector_plugin: MidiInspectorPlugin
var _main_screen: ClefStation = null
var _bridge: RefCounted = null
var _l10n: ClefL10n = null


func _enter_tree() -> void:
	_l10n = ClefL10n.new()
	_l10n.setup()
	MidiComposerConverter.l10n = _l10n
	_submenu = PopupMenu.new()
	_submenu.name = "ClefUtilityMenu"
	_submenu.add_item(_l10n.t("Compose MIDI from JSON..."), _MENU_COMPOSE)
	_submenu.add_item(_l10n.t("Export MIDI to JSON..."), _MENU_EXPORT)
	_submenu.id_pressed.connect(_on_submenu_id_pressed)
	_submenu_name = _l10n.t("Clef Utility")
	add_tool_submenu_item(_submenu_name, _submenu)
	_import_plugin = MidiImportPlugin.new()
	add_import_plugin(_import_plugin)
	_inspector_plugin = MidiInspectorPlugin.new()
	_inspector_plugin.l10n = _l10n
	add_inspector_plugin(_inspector_plugin)
	_file_context_menu = ClefFileContextMenu.new()
	_file_context_menu.l10n = _l10n
	add_context_menu_plugin(EditorContextMenuPlugin.CONTEXT_SLOT_FILESYSTEM, _file_context_menu)
	_main_screen = ClefStation.new()
	_main_screen.name = "ClefStation"
	EditorInterface.get_editor_main_screen().add_child(_main_screen)
	_bridge = load("res://addons/clef/editor/clef_station_editor_bridge.gd").new()
	_main_screen.set_bridge(_bridge)
	_make_visible(false)
	_register_project_settings()


func _exit_tree() -> void:
	if _l10n:
		MidiComposerConverter.l10n = null
		_l10n.cleanup()
		_l10n = null
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
		remove_tool_menu_item(_submenu_name)
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
		_show_error(_l10n.t("Select a JSON file in the FileSystem panel first"))
		return

	var json_path: String = paths[0]
	if not json_path.ends_with(".json"):
		_show_error(_l10n.t("Selected file is not a .json file: ") + json_path)
		return

	if not FileAccess.file_exists(json_path):
		_show_error(_l10n.t("File not found: ") + json_path)
		return

	var file := FileAccess.open(json_path, FileAccess.READ)
	if file == null:
		_show_error(_l10n.t("Cannot read file: ") + json_path + "\n" + str(FileAccess.get_open_error()))
		return

	var json_text: String = file.get_as_text()

	var result := MidiComposerConverter.from_json_string(json_text)
	if not result.ok:
		_show_error(_l10n.t("JSON conversion failed: ") + result.error_message)
		return

	var midi_bytes: PackedByteArray = MidiWriter.encode(result.midi_data)

	var dialog := EditorFileDialog.new()
	dialog.file_mode = EditorFileDialog.FILE_MODE_SAVE_FILE
	dialog.access = EditorFileDialog.ACCESS_RESOURCES
	dialog.title = _l10n.t("Save MIDI")
	dialog.filters = PackedStringArray([_l10n.t("*.mid ; MIDI Files")])
	dialog.current_dir = json_path.get_base_dir()
	dialog.current_file = json_path.get_file().get_basename() + ".mid"
	dialog.canceled.connect(func():
		EditorInterface.get_base_control().remove_child(dialog)
		dialog.queue_free()
	)
	dialog.file_selected.connect(func(path: String) -> void:
		var out_file := FileAccess.open(path, FileAccess.WRITE)
		if out_file == null:
			_show_error(_l10n.t("Cannot write MIDI file: ") + path)
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
		_show_error(_l10n.t("Select a .mid or .tres file in the FileSystem panel first"))
		return

	var input_path: String = paths[0]
	if not (input_path.ends_with(".mid") or input_path.ends_with(".tres")):
		_show_error(_l10n.t("Unsupported file format, please select a .mid or .tres file"))
		return

	if not FileAccess.file_exists(input_path):
		_show_error(_l10n.t("File not found: ") + input_path)
		return

	var midi_data: MidiData = null
	if input_path.ends_with(".tres"):
		var res = load(input_path)
		if res == null or not res is MidiResource:
			_show_error(_l10n.t("Cannot load MidiResource: ") + input_path)
			return
		midi_data = res.get_midi_data()
	else:
		var file := FileAccess.open(input_path, FileAccess.READ)
		if file == null:
			_show_error(_l10n.t("Cannot read file: ") + input_path)
			return
		var bytes := file.get_buffer(file.get_length())
		var result := MidiReader.from_bytes(bytes)
		if not result.ok:
			_show_error(_l10n.t("MIDI parse failed: ") + result.error_message)
			return
		midi_data = result.midi_data

	if midi_data == null:
		_show_error(_l10n.t("Cannot get MIDI data"))
		return

	var json_text: String = MidiComposerConverter.to_json_string(midi_data)

	var dialog := EditorFileDialog.new()
	dialog.file_mode = EditorFileDialog.FILE_MODE_SAVE_FILE
	dialog.access = EditorFileDialog.ACCESS_RESOURCES
	dialog.title = _l10n.t("Export JSON")
	dialog.filters = PackedStringArray([_l10n.t("*.json ; JSON Files")])
	dialog.current_dir = input_path.get_base_dir()
	dialog.current_file = input_path.get_file().get_basename() + ".json"
	dialog.canceled.connect(func():
		EditorInterface.get_base_control().remove_child(dialog)
		dialog.queue_free()
	)
	dialog.file_selected.connect(func(path: String) -> void:
		var file := FileAccess.open(path, FileAccess.WRITE)
		if file == null:
			_show_error(_l10n.t("Cannot write file: ") + path)
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
