@tool
class_name ClefFileContextMenu
extends EditorContextMenuPlugin

## 文件系统面板右键菜单
## 选中 .json 时显示 "Convert to MIDI"
## 选中 .mid / .tres 时显示 "Export to JSON"

var _pending_paths: PackedStringArray = []


func _popup_menu(paths: PackedStringArray) -> void:
	if paths.is_empty():
		return

	var path: String = paths[0]
	_pending_paths = paths

	if path.ends_with(".json") and _is_clef_json(path):
		add_context_menu_item("Convert to MIDI", _on_convert_json_to_midi)
	elif path.ends_with(".mid") or path.ends_with(".tres"):
		add_context_menu_item("Export to JSON", _on_export_midi_to_json)


func _is_clef_json(path: String) -> bool:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return false
	var text: String = file.get_as_text()
	file.close()
	var data = JSON.parse_string(text)
	if data == null or not data is Dictionary:
		return false
	var version = data.get("format_version", "")
	return version in ["1.0", "1.1", "2.0"]


func _on_convert_json_to_midi(_paths: PackedStringArray) -> void:
	var json_path: String = _pending_paths[0]

	var file := FileAccess.open(json_path, FileAccess.READ)
	if file == null:
		_show_error("无法读取文件：" + json_path)
		return

	var json_text: String = file.get_as_text()
	var result := MidiComposerConverter.from_json_string(json_text)
	if not result.ok:
		_show_error("JSON 转换失败：" + result.error_message)
		return

	var midi_bytes: PackedByteArray = MidiWriter.encode(result.midi_data)

	_save_file_dialog(
		"保存 MIDI",
		["*.mid ; MIDI 文件"],
		json_path.get_file().get_basename() + ".mid",
		json_path.get_base_dir(),
		func(path: String) -> void:
			var out_file := FileAccess.open(path, FileAccess.WRITE)
			if out_file == null:
				_show_error("无法写入 MIDI 文件：" + path)
				return
			out_file.store_buffer(midi_bytes)
			out_file.close()
			EditorInterface.get_resource_filesystem().scan(),
	)


func _on_export_midi_to_json(_paths: PackedStringArray) -> void:
	var input_path: String = _pending_paths[0]

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

	var json_text: String = MidiComposerConverter.to_json_string(midi_data)

	_save_file_dialog(
		"导出 JSON",
		["*.json ; JSON 文件"],
		input_path.get_file().get_basename() + ".json",
		input_path.get_base_dir(),
		func(path: String) -> void:
			var file := FileAccess.open(path, FileAccess.WRITE)
			if file == null:
				_show_error("无法写入文件：" + path)
				return
			file.store_string(json_text)
			file.close()
			EditorInterface.get_resource_filesystem().scan(),
	)


func _save_file_dialog(
	title: String,
	filters: PackedStringArray,
	default_file: String,
	default_dir: String,
	on_selected: Callable,
) -> void:
	var dialog := EditorFileDialog.new()
	dialog.file_mode = EditorFileDialog.FILE_MODE_SAVE_FILE
	dialog.access = EditorFileDialog.ACCESS_RESOURCES
	dialog.title = title
	dialog.filters = filters
	dialog.current_dir = default_dir
	dialog.current_file = default_file
	dialog.file_selected.connect(func(path: String) -> void:
		on_selected.call(path)
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
