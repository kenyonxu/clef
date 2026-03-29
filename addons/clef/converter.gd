## JSON 转 MidiData 转换器
## 验证 JSON 结构，将拍(v2.0)或秒数(v1.1)转换为 tick，输出 MidiData 对象。
## 导出时统一使用 v2.0（拍单位）。

class_name MidiComposerConverter
extends RefCounted

const _TIMEBASE: int = 480

## 转换结果
class ConvertResult:
	var ok: bool = false
	var midi_data: MidiData = null
	var error_message: String = ""

	func _init(p_ok: bool = false, p_midi_data: MidiData = null, p_error_message: String = "") -> void:
		ok = p_ok
		midi_data = p_midi_data
		error_message = p_error_message


## 主入口：将 JSON 字符串解析并转换为 MidiData
static func from_json_string(json_text: String) -> ConvertResult:
	var data = JSON.parse_string(json_text)
	if data == null:
		return ConvertResult.new(
			false, null,
			"JSON 解析失败：无效的 JSON 格式"
		)
	if not data is Dictionary:
		return ConvertResult.new(
			false, null,
			"JSON 解析失败：根元素必须是对象"
		)

	var version_error: String = _validate_root(data)
	if version_error != "":
		return ConvertResult.new(false, null, version_error)

	return _convert(data)


## 将 MidiData 转换为 JSON 字符串（v2.0 拍单位）
static func to_json_string(midi_data: MidiData) -> String:
	var tb: int = midi_data.timebase
	var tracks_array: Array = []
	for track_data in midi_data.tracks:
		var track_dict: Dictionary = {"name": track_data.name}
		if track_data.channel != 0:
			track_dict["channel"] = track_data.channel
		if track_data.instrument != 0:
			track_dict["instrument"] = track_data.instrument

		var notes_array: Array = []
		for note in track_data.notes:
			notes_array.append({
				"pitch": note.pitch,
				"start": _ticks_to_beats(note.start_ticks, tb),
				"duration": _ticks_to_beats(note.duration_ticks, tb),
				"velocity": note.velocity,
			})
		track_dict["notes"] = notes_array

		if not track_data.cc_events.is_empty():
			var cc_array: Array = []
			for cc in track_data.cc_events:
				cc_array.append({
					"time": _ticks_to_beats(cc["time_ticks"], tb),
					"controller": cc["controller"],
					"value": cc["value"],
				})
			track_dict["cc_events"] = cc_array

		if not track_data.pitch_bend_events.is_empty():
			var pb_array: Array = []
			for pb in track_data.pitch_bend_events:
				pb_array.append({
					"time": _ticks_to_beats(pb["time_ticks"], tb),
					"value": pb["value"],
				})
			track_dict["pitch_bend_events"] = pb_array

		tracks_array.append(track_dict)

	var root: Dictionary = {
		"format_version": "2.0",
		"tempo": midi_data.tempo,
		"tracks": tracks_array,
	}

	if tb != _TIMEBASE:
		root["timebase"] = tb

	if not midi_data.tempo_events.is_empty():
		var tc_array: Array = []
		for tc in midi_data.tempo_events:
			tc_array.append({
				"time": _ticks_to_beats(tc["time_ticks"], tb),
				"bpm": tc["bpm"],
			})
		root["tempo_changes"] = tc_array

	return JSON.stringify(root, "  ")


## 秒→tick 转换速率（v1.1 兼容）
static func _ticks_per_second(tempo: int, timebase: int = -1) -> float:
	var tb: int = timebase if timebase > 0 else _TIMEBASE
	return (float(tempo) / 60.0) * float(tb)


## tick→秒转换（v1.1 兼容）
static func _tick_to_seconds(ticks: int, ticks_per_second: float) -> float:
	if ticks_per_second <= 0.0:
		return 0.0
	return float(ticks) / ticks_per_second


## 拍→tick 转换（v2.0）
static func _beats_to_ticks(beats: float, timebase: int) -> int:
	return int(beats * float(timebase))


## tick→拍 转换（v2.0）
static func _ticks_to_beats(ticks: int, timebase: int) -> float:
	if timebase <= 0:
		return 0.0
	return float(ticks) / float(timebase)


## 根级字段验证
static func _validate_root(data: Dictionary) -> String:
	if data.has("format_version"):
		if not data["format_version"] is String:
			return "format_version 必须是字符串"
		if data["format_version"] != "1.0" and data["format_version"] != "1.1" and data["format_version"] != "2.0":
			return "不支持的 format_version：'%s'，当前支持 '1.0'、'1.1' 和 '2.0'" % str(data["format_version"])

	if not data.has("tempo"):
		return "缺少必填字段：tempo"
	if not data["tempo"] is int and not data["tempo"] is float:
		return "tempo 必须是整数"
	var tempo: int = int(data["tempo"])
	if tempo <= 0:
		return "tempo 必须大于 0，当前值：%d" % tempo

	if not data.has("tracks"):
		return "缺少必填字段：tracks"
	if not data["tracks"] is Array:
		return "tracks 必须是数组"
	if data["tracks"].is_empty():
		return "tracks 不能为空数组"

	return ""


## 将验证通过的 Dictionary 转换为 MidiData
static func _convert(data: Dictionary) -> ConvertResult:
	var tempo: int = int(data["tempo"])
	var timebase: int = int(data.get("timebase", _TIMEBASE))
	var tracks_array: Array = data["tracks"]
	var is_v2: bool = data.get("format_version", "1.1") == "2.0"

	var tempo_events: Array[Dictionary] = []
	if data.has("tempo_changes") and data["tempo_changes"] is Array:
		for tc in data["tempo_changes"]:
			if not tc is Dictionary:
				continue
			var tc_bpm: int = int(tc.get("bpm", 0))
			if tc_bpm > 0:
				var tc_time: float = float(tc.get("time", 0.0))
				var time_ticks: int
				if is_v2:
					time_ticks = _beats_to_ticks(tc_time, timebase)
				else:
					var tps: float = _ticks_per_second(tempo, timebase)
					time_ticks = int(tc_time * tps)
				tempo_events.append({
					"time_ticks": time_ticks,
					"bpm": tc_bpm,
				})

	var midi_data := MidiData.new(tempo, [], timebase, tempo_events)

	# 从轨道 instrument 字段生成 program_events（JSON 场景每个轨道只有一个乐器）
	var program_events: Array[Dictionary] = []
	for track_index in range(tracks_array.size()):
		var track_entry = tracks_array[track_index]
		if not track_entry is Dictionary:
			continue
		var notes_array: Array = track_entry.get("notes", [])
		if not notes_array is Array or notes_array.is_empty():
			continue
		var ch: int = int(track_entry.get("channel", 0))
		var inst: int = int(track_entry.get("instrument", 0))
		var first_start: float = float(notes_array[0].get("start", 0.0))
		var time_ticks: int
		if is_v2:
			time_ticks = _beats_to_ticks(first_start, timebase)
		else:
			var tps: float = _ticks_per_second(tempo, timebase)
			time_ticks = int(first_start * tps)
		program_events.append({
			"time_ticks": time_ticks,
			"channel": ch,
			"preset_index": inst,
		})

	for track_index in range(tracks_array.size()):
		var track_entry = tracks_array[track_index]
		if not track_entry is Dictionary:
			push_error("音轨 %d：必须是对象，已跳过" % track_index)
			continue

		var track_data: TrackData = _convert_track(
			track_entry as Dictionary, track_index, tempo, timebase, is_v2
		)
		if track_data == null:
			continue
		midi_data.tracks.append(track_data)

	if midi_data.tracks.is_empty():
		return ConvertResult.new(
			false, null,
			"转换失败：没有有效的音轨数据"
		)

	midi_data.program_events = program_events

	return ConvertResult.new(true, midi_data, "")


## 转换单个音轨
static func _convert_track(track_dict: Dictionary, track_index: int, tempo: int, timebase: int = -1, is_v2: bool = false) -> TrackData:
	var track_name: String = ""
	if track_dict.has("name"):
		if not track_dict["name"] is String:
			push_error("音轨 %d：name 必须是字符串，已忽略" % track_index)
		else:
			track_name = track_dict["name"]

	var channel: int = 0
	if track_dict.has("channel"):
		if not track_dict["channel"] is int and not track_dict["channel"] is float:
			push_error("音轨 %d：channel 必须是整数，已跳过该音轨" % track_index)
			return null
		channel = int(track_dict["channel"])
		if channel < 0 or channel > 15:
			push_error("音轨 %d：channel 必须在 0-15 范围内，当前值：%d，已跳过该音轨" % [track_index, channel])
			return null

	var instrument: int = 0
	if track_dict.has("instrument"):
		if not track_dict["instrument"] is int and not track_dict["instrument"] is float:
			push_error("音轨 %d：instrument 必须是整数，已跳过该音轨" % track_index)
			return null
		instrument = int(track_dict["instrument"])
		if instrument < 0 or instrument > 127:
			push_error("音轨 %d：instrument 必须在 0-127 范围内，当前值：%d，已跳过该音轨" % [track_index, instrument])
			return null

	if not track_dict.has("notes"):
		push_error("音轨 %d：缺少必填字段 notes，已跳过该音轨" % track_index)
		return null
	if not track_dict["notes"] is Array:
		push_error("音轨 %d：notes 必须是数组，已跳过该音轨" % track_index)
		return null

	var notes_array: Array = track_dict["notes"]
	var notes: Array[NoteData] = []
	for note_index in range(notes_array.size()):
		var note_entry = notes_array[note_index]
		if not note_entry is Dictionary:
			push_error("音轨 %d 音符 %d：必须是对象，已跳过" % [track_index, note_index])
			continue
		var note_data: NoteData = _convert_note(
			note_entry as Dictionary, track_index, note_index, tempo, timebase, is_v2
		)
		if note_data == null:
			continue
		notes.append(note_data)

	var cc_events: Array[Dictionary] = _parse_cc_events(track_dict, tempo, timebase, is_v2)
	var pitch_bend_events: Array[Dictionary] = _parse_pitch_bend_events(track_dict, tempo, timebase, is_v2)

	return TrackData.new(track_name, channel, instrument, notes, cc_events, pitch_bend_events)


## 解析 CC 事件数组
static func _parse_cc_events(track_dict: Dictionary, tempo: int, timebase: int = -1, is_v2: bool = false) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if not track_dict.has("cc_events") or not track_dict["cc_events"] is Array:
		return result
	var tb: int = timebase if timebase > 0 else _TIMEBASE
	for cc in track_dict["cc_events"]:
		if not cc is Dictionary:
			continue
		var cc_time: float = float(cc.get("time", 0.0))
		var cc_controller: int = int(cc.get("controller", 0))
		var cc_value: int = int(cc.get("value", 0))
		var time_ticks: int
		if is_v2:
			time_ticks = _beats_to_ticks(cc_time, tb)
		else:
			time_ticks = int(cc_time * _ticks_per_second(tempo, tb))
		result.append({
			"time_ticks": time_ticks,
			"controller": clampi(cc_controller, 0, 127),
			"value": clampi(cc_value, 0, 127),
		})
	return result


## 解析 Pitch Bend 事件数组
static func _parse_pitch_bend_events(track_dict: Dictionary, tempo: int, timebase: int = -1, is_v2: bool = false) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	if not track_dict.has("pitch_bend_events") or not track_dict["pitch_bend_events"] is Array:
		return result
	var tb: int = timebase if timebase > 0 else _TIMEBASE
	for pb in track_dict["pitch_bend_events"]:
		if not pb is Dictionary:
			continue
		var pb_time: float = float(pb.get("time", 0.0))
		var pb_value: int = int(pb.get("value", 8192))
		var time_ticks: int
		if is_v2:
			time_ticks = _beats_to_ticks(pb_time, tb)
		else:
			time_ticks = int(pb_time * _ticks_per_second(tempo, tb))
		result.append({
			"time_ticks": time_ticks,
			"value": clampi(pb_value, 0, 16383),
		})
	return result


## 转换单个音符，将拍(v2.0)或秒(v1.1)转换为 tick
static func _convert_note(note_dict: Dictionary, track_index: int, note_index: int, tempo: int, timebase: int = -1, is_v2: bool = false) -> NoteData:
	if not note_dict.has("pitch"):
		push_error("音轨 %d 音符 %d：缺少必填字段 pitch，已跳过" % [track_index, note_index])
		return null
	if not note_dict["pitch"] is int and not note_dict["pitch"] is float:
		push_error("音轨 %d 音符 %d：pitch 必须是整数，已跳过" % [track_index, note_index])
		return null
	var pitch: int = int(note_dict["pitch"])
	if pitch < 0 or pitch > 127:
		push_error("音轨 %d 音符 %d：pitch 必须在 0-127 范围内，当前值：%d，已跳过" % [track_index, note_index, pitch])
		return null

	if not note_dict.has("start"):
		push_error("音轨 %d 音符 %d：缺少必填字段 start，已跳过" % [track_index, note_index])
		return null
	if not note_dict["start"] is int and not note_dict["start"] is float:
		push_error("音轨 %d 音符 %d：start 必须是数值，已跳过" % [track_index, note_index])
		return null
	var start_seconds: float = float(note_dict["start"])
	if start_seconds < 0.0:
		push_error("音轨 %d 音符 %d：start 不能为负数，当前值：%.3f，已跳过" % [track_index, note_index, start_seconds])
		return null

	if not note_dict.has("duration"):
		push_error("音轨 %d 音符 %d：缺少必填字段 duration，已跳过" % [track_index, note_index])
		return null
	if not note_dict["duration"] is int and not note_dict["duration"] is float:
		push_error("音轨 %d 音符 %d：duration 必须是数值，已跳过" % [track_index, note_index])
		return null
	var duration_seconds: float = float(note_dict["duration"])
	if duration_seconds <= 0.0:
		push_error("音轨 %d 音符 %d：duration 必须大于 0，当前值：%.3f，已跳过" % [track_index, note_index, duration_seconds])
		return null

	var tb: int = timebase if timebase > 0 else _TIMEBASE
	var start_ticks: int
	var duration_ticks: int
	if is_v2:
		start_ticks = _beats_to_ticks(start_seconds, tb)
		duration_ticks = _beats_to_ticks(duration_seconds, tb)
	else:
		var tps: float = _ticks_per_second(tempo, tb)
		start_ticks = int(start_seconds * tps)
		duration_ticks = int(duration_seconds * tps)

	var velocity: int = 100
	if note_dict.has("velocity"):
		if not note_dict["velocity"] is int and not note_dict["velocity"] is float:
			push_error("音轨 %d 音符 %d：velocity 必须是整数，已跳过" % [track_index, note_index])
			return null
		velocity = int(note_dict["velocity"])
		if velocity < 0 or velocity > 127:
			push_error("音轨 %d 音符 %d：velocity 必须在 0-127 范围内，当前值：%d，已跳过" % [track_index, note_index, velocity])
			return null

	if duration_ticks < 1:
		duration_ticks = 1

	return NoteData.new(pitch, start_ticks, duration_ticks, velocity)
