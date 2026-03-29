@tool
class_name MidiImportPlugin
extends EditorImportPlugin


func _get_importer_name() -> String:
	return "clef"


func _get_visible_name() -> String:
	return "MIDI Resource"


func _get_recognized_extensions() -> PackedStringArray:
	return PackedStringArray(["mid"])


func _get_resource_type() -> String:
	return "MidiResource"


func _get_save_extension() -> String:
	return "tres"


func _get_preset_count() -> int:
	return 0


func _get_import_order() -> int:
	return 0


func _get_priority() -> float:
	return 1.0


func _get_import_options(_path: String, _preset_index: int) -> Array[Dictionary]:
	return []


func _import(source_file: String, save_path: String, _options: Dictionary, _r_platform_variants: Array, _r_gen_files: Array) -> Error:
	var file := FileAccess.open(source_file, FileAccess.READ)
	if file == null:
		push_error("MidiImportPlugin: 无法读取文件 " + source_file)
		return ERR_CANT_OPEN
	var bytes: PackedByteArray = file.get_buffer(file.get_length())
	file.close()
	var result := MidiReader.from_bytes(bytes)
	if not result.ok:
		push_error("MidiImportPlugin: 解析失败 " + source_file + ": " + result.error_message)
		return ERR_PARSE_ERROR
	var resource := MidiResource.new()
	resource.from_midi_data(result.midi_data)
	print("[Clef Import] %s → %d tracks, %d program_events, %d cc_events, %d pb_events" % [
		source_file.get_file(),
		resource.tracks.size(),
		resource.program_events.size(),
		resource.cc_events.size(),
		resource.pitch_bend_events.size(),
	])
	return ResourceSaver.save(resource, save_path + ".tres")
