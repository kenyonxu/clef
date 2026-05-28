## MIDI SMF 二进制解析器
## 将 .mid 文件二进制数据解析为 MidiData 对象
## 独立实现，不依赖 addons/midi/SMF.gd

class_name MidiReader
extends RefCounted

# -----------------------------------------------------------------------------
# 常量

## MIDI 事件状态字节
const _STATUS_NOTE_OFF: int = 0x80
const _STATUS_NOTE_ON: int = 0x90
const _STATUS_POLY_KEY_PRESSURE: int = 0xA0
const _STATUS_CONTROL_CHANGE: int = 0xB0
const _STATUS_PROGRAM_CHANGE: int = 0xC0
const _STATUS_CHANNEL_PRESSURE: int = 0xD0
const _STATUS_PITCH_BEND: int = 0xE0
const _STATUS_META: int = 0xFF
const _STATUS_SYSEX: int = 0xF0
const _STATUS_SYSEX_END: int = 0xF7

## Meta 事件类型
const _META_TRACK_NAME: int = 0x03
const _META_END_OF_TRACK: int = 0x2F
const _META_SET_TEMPO: int = 0x51

# -----------------------------------------------------------------------------
# 结果类型

## 解析结果
class ReadResult:
	var ok: bool = false
	var midi_data: MidiData = null
	var error_message: String = ""

	func _init(p_ok: bool = false, p_midi_data: MidiData = null, p_error_message: String = "") -> void:
		ok = p_ok
		midi_data = p_midi_data
		error_message = p_error_message

# -----------------------------------------------------------------------------
# 公开接口

## 从字节数组解析 MIDI 数据
static func from_bytes(data: PackedByteArray) -> ReadResult:
	if data.size() < 14:
		return ReadResult.new(false, null, "数据过短，不是有效的 MIDI 文件 (至少需要 14 字节)")

	var stream: StreamPeerBuffer = StreamPeerBuffer.new()
	stream.big_endian = true
	stream.put_data(data)
	# 重置读取位置到开头
	stream.seek(0)

	return _parse(stream)


## 从文件路径解析 MIDI 数据
static func from_file(path: String) -> ReadResult:
	if not FileAccess.file_exists(path):
		return ReadResult.new(false, null, "文件不存在: %s" % path)

	var file: FileAccess = FileAccess.open(path, FileAccess.READ)
	if file == null:
		return ReadResult.new(false, null, "无法打开文件: %s" % path)

	var data: PackedByteArray = file.get_buffer(file.get_length())
	file.close()

	return from_bytes(data)

# -----------------------------------------------------------------------------
# 主解析流程

## 解析 SMF 数据流
static func _parse(stream: StreamPeerBuffer) -> ReadResult:
	# 1. 读取 MThd 头
	var header_result: _HeaderResult = _read_header(stream)
	if not header_result.ok:
		return ReadResult.new(false, null, header_result.error_message)

	var format: int = header_result.format
	var ntracks: int = header_result.ntracks
	var timebase: int = header_result.timebase

	# 2. 读取所有轨道的原始事件
	var track_raw_events: Array[Array] = []
	for track_idx in range(ntracks):
		var track_result := _read_track_events(stream)
		if not track_result.ok:
			return ReadResult.new(false, null, "轨道 %d 解析失败: %s" % [track_idx, track_result.error_message])
		track_raw_events.append(track_result.events)

	# 3. 根据格式处理
	# DEBUG: 每轨道事件类型摘要
	if ProjectSettings.get_setting("clef/debug_verbose", false):
		print("[Clef Reader] Format=%d, Tracks=%d, Timebase=%d" % [format, ntracks, timebase])
	for track_idx in range(track_raw_events.size()):
		var type_counts: Dictionary = {}
		for ev in track_raw_events[track_idx]:
			var t: String = ev.get("type", "?")
			type_counts[t] = type_counts.get(t, 0) + 1
		if ProjectSettings.get_setting("clef/debug_verbose", false):
			print("[Clef Reader]   Track %d: %s" % [track_idx, type_counts])

	if format == 0:
		return _build_format_0(timebase, track_raw_events)
	elif format == 1:
		return _build_format_1(timebase, track_raw_events)
	else:
		return ReadResult.new(false, null, "不支持的 MIDI 格式: %d (仅支持 0 和 1)" % format)

# -----------------------------------------------------------------------------
# Header 解析

## 头部解析结果
class _HeaderResult:
	var ok: bool = false
	var format: int = 0
	var ntracks: int = 0
	var timebase: int = 0
	var error_message: String = ""

	func _init(p_ok: bool = false, p_format: int = 0, p_ntracks: int = 0, p_timebase: int = 0, p_error_message: String = "") -> void:
		ok = p_ok
		format = p_format
		ntracks = p_ntracks
		timebase = p_timebase
		error_message = p_error_message


## 读取并验证 MThd 头部
static func _read_header(stream: StreamPeerBuffer) -> _HeaderResult:
	# 读取 4 字节 magic
	if stream.get_available_bytes() < 14:
		return _HeaderResult.new(false, 0, 0, 0, "数据不足以读取头部")

	var magic: PackedByteArray = stream.get_data(4)[1]
	var magic_str: String = magic.get_string_from_ascii()

	if magic_str != "MThd":
		return _HeaderResult.new(false, 0, 0, 0, "无效的 MIDI 文件头部，期望 'MThd'，实际为 '%s'" % magic_str)

	# 读取 header data size (应为 6)
	var header_size: int = stream.get_u32()
	if header_size != 6:
		return _HeaderResult.new(false, 0, 0, 0, "无效的 header 大小: %d (期望 6)" % header_size)

	var format: int = stream.get_u16()
	var ntracks: int = stream.get_u16()
	var timebase: int = stream.get_u16()

	if format != 0 and format != 1:
		return _HeaderResult.new(false, 0, 0, 0, "不支持的 MIDI 格式: %d" % format)

	if ntracks < 1:
		return _HeaderResult.new(false, 0, 0, 0, "无效的轨道数量: %d" % ntracks)

	return _HeaderResult.new(true, format, ntracks, timebase)

# -----------------------------------------------------------------------------
# Track 解析

## 轨道解析结果
class _TrackEventsResult:
	var ok: bool = false
	var events: Array = []
	var error_message: String = ""

	func _init(p_ok: bool = false, p_events: Array = [], p_error_message: String = "") -> void:
		ok = p_ok
		events = p_events
		error_message = p_error_message


## 读取单个轨道的所有原始事件
static func _read_track_events(stream: StreamPeerBuffer) -> _TrackEventsResult:
	# 读取 MTrk chunk header
	if stream.get_available_bytes() < 8:
		return _TrackEventsResult.new(false, [], "数据不足以读取轨道头部")

	var chunk_id: PackedByteArray = stream.get_data(4)[1]
	var chunk_id_str: String = chunk_id.get_string_from_ascii()
	if chunk_id_str != "MTrk":
		return _TrackEventsResult.new(false, [], "期望 'MTrk'，实际为 '%s'" % chunk_id_str)

	var chunk_size: int = stream.get_u32()
	if stream.get_available_bytes() < chunk_size:
		return _TrackEventsResult.new(false, [], "轨道数据不完整 (期望 %d 字节，剩余 %d)" % [chunk_size, stream.get_available_bytes()])

	# 将轨道数据提取到独立流
	var track_data: PackedByteArray = stream.get_data(chunk_size)[1]
	var track_stream: StreamPeerBuffer = StreamPeerBuffer.new()
	track_stream.big_endian = true
	track_stream.put_data(track_data)
	track_stream.seek(0)

	# 解析轨道内的事件
	var events: Array = []
	var current_time: int = 0
	var running_status: int = -1

	while track_stream.get_available_bytes() > 0:
		# 读取 delta time
		var delta_time: int = _read_vlq(track_stream)
		current_time += delta_time

		# 读取状态字节 (可能使用 running status)
		var peek_byte: int = track_stream.get_u8()

		var status_byte: int
		if peek_byte >= 0x80:
			# 新状态字节
			status_byte = peek_byte
			# Meta 和 SysEx 不更新 running status
			if status_byte != _STATUS_META and status_byte != _STATUS_SYSEX and status_byte != _STATUS_SYSEX_END:
				running_status = status_byte
		else:
			# 数据字节 — 使用 running status
			if running_status == -1:
				return _TrackEventsResult.new(false, [], "遇到数据字节但没有有效的 running status")
			status_byte = running_status
			track_stream.seek(track_stream.get_position() - 1)  # 回退，让事件解析器读取

		# 解析事件
		var event_result: Dictionary = _parse_event(track_stream, status_byte)
		# 空 dict 表示跳过的事件 (SysEx, Control Change 等)，不视为错误
		if event_result.has("type"):
			event_result["time_ticks"] = current_time
			events.append(event_result)

	return _TrackEventsResult.new(true, events)

# -----------------------------------------------------------------------------
# 事件解析

## 解析单个 MIDI 事件
## 返回 Dictionary 或空 Dictionary（表示错误）
static func _parse_event(stream: StreamPeerBuffer, status_byte: int) -> Dictionary:
	var event_type: int = status_byte & 0xF0
	var channel: int = status_byte & 0x0F

	# Meta 事件
	if status_byte == _STATUS_META:
		return _parse_meta_event(stream)

	# SysEx 事件
	if status_byte == _STATUS_SYSEX or status_byte == _STATUS_SYSEX_END:
		_skip_sysex(stream)
		return {}

	# Channel 事件
	match event_type:
		_STATUS_NOTE_ON:
			return _parse_note_on(stream, channel)

		_STATUS_NOTE_OFF:
			return _parse_note_off(stream, channel)

		_STATUS_PROGRAM_CHANGE:
			return _parse_program_change(stream, channel)

		_STATUS_CONTROL_CHANGE:
			if stream.get_available_bytes() >= 2:
				var controller: int = stream.get_u8()
				var value: int = stream.get_u8()
				# DEBUG: Bank Select 和 Program Change 诊断
				if controller == 0 or controller == 32:
					if ProjectSettings.get_setting("clef/debug_verbose", false):
						print("[Clef Reader] CC%d (Bank %s) ch=%d value=%d" % [controller, "MSB" if controller == 0 else "LSB", channel, value])
				return {
					"type": "control_change",
					"channel": channel,
					"controller": controller,
					"value": value,
				}
			return {}

		_STATUS_POLY_KEY_PRESSURE:
			# 读取 2 个数据字节并跳过
			if stream.get_available_bytes() >= 2:
				stream.get_u8()
				stream.get_u8()
			return {}

		_STATUS_CHANNEL_PRESSURE:
			# 读取 1 个数据字节并跳过
			if stream.get_available_bytes() >= 1:
				stream.get_u8()
			return {}

		_STATUS_PITCH_BEND:
			if stream.get_available_bytes() >= 2:
				var lsb: int = stream.get_u8()
				var msb: int = stream.get_u8()
				var raw_value: int = (msb << 7) | lsb
				return {
					"type": "pitch_bend",
					"channel": channel,
					"value": raw_value,
				}
			return {}

		_:
			return {}


## 解析 Note On 事件
static func _parse_note_on(stream: StreamPeerBuffer, channel: int) -> Dictionary:
	if stream.get_available_bytes() < 2:
		return {}

	var pitch: int = stream.get_u8()
	var velocity: int = stream.get_u8()

	# velocity 0 视为 Note Off
	if velocity == 0:
		return {
			"type": "note_off",
			"channel": channel,
			"pitch": pitch,
		}
	else:
		return {
			"type": "note_on",
			"channel": channel,
			"pitch": pitch,
			"velocity": velocity,
		}


## 解析 Note Off 事件
static func _parse_note_off(stream: StreamPeerBuffer, channel: int) -> Dictionary:
	if stream.get_available_bytes() < 2:
		return {}

	var pitch: int = stream.get_u8()
	stream.get_u8()  # velocity (通常为 0，不需要保存)

	return {
		"type": "note_off",
		"channel": channel,
		"pitch": pitch,
	}


## 解析 Program Change 事件
static func _parse_program_change(stream: StreamPeerBuffer, channel: int) -> Dictionary:
	if stream.get_available_bytes() < 1:
		return {}

	var program: int = stream.get_u8()

	# DEBUG: Program Change 诊断
	if ProjectSettings.get_setting("clef/debug_verbose", false):
		print("[Clef Reader] Program Change ch=%d program=%d (%s)" % [channel, program, _gm_instrument_name(program)])

	return {
		"type": "program_change",
		"channel": channel,
		"program": program,
	}


## GM 标准音色名称（诊断用）
static func _gm_instrument_name(program: int) -> String:
	var names: PackedStringArray = [
		"Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano", "Honky-tonk Piano",
		"Electric Piano 1", "Electric Piano 2", "Harpsichord", "Clavinet",
		"Celesta", "Glockenspiel", "Music Box", "Vibraphone",
		"Marimba", "Xylophone", "Tubular Bells", "Dulcimer",
		"Drawbar Organ", "Percussive Organ", "Rock Organ", "Church Organ",
		"Reed Organ", "Accordion", "Harmonica", "Tango Accordion",
		"Nylon Guitar", "Steel Guitar", "Jazz Guitar", "Clean Guitar",
		"Muted Guitar", "Overdriven Guitar", "Distortion Guitar", "Guitar Harmonics",
		"Acoustic Bass", "Finger Bass", "Pick Bass", "Fretless Bass",
		"Slap Bass 1", "Slap Bass 2", "Synth Bass 1", "Synth Bass 2",
		"Violin", "Viola", "Cello", "Contrabass",
		"Tremolo Strings", "Pizzicato Strings", "Orchestral Harp", "Timpani",
		"String Ensemble 1", "String Ensemble 2", "Synth Strings 1", "Synth Strings 2",
		"Choir Aahs", "Voice Oohs", "Synth Choir", "Orchestra Hit",
		"Trumpet", "Trombone", "Tuba", "Muted Trumpet",
		"French Horn", "Brass Section", "Synth Brass 1", "Synth Brass 2",
		"Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax",
		"Oboe", "English Horn", "Bassoon", "Clarinet",
		"Piccolo", "Flute", "Recorder", "Pan Flute",
		"Blown Bottle", "Shakuhachi", "Whistle", "Ocarina",
		"Lead 1 (Square)", "Lead 2 (Sawtooth)", "Lead 3 (Calliope)", "Lead 4 (Chiff)",
		"Lead 5 (Charang)", "Lead 6 (Voice)", "Lead 7 (Fifths)", "Lead 8 (Bass+Lead)",
		"Pad 1 (New Age)", "Pad 2 (Warm)", "Pad 3 (Polysynth)", "Pad 4 (Choir)",
		"Pad 5 (Bowed)", "Pad 6 (Metal)", "Pad 7 (Halo)", "Pad 8 (Sweep)",
		"FX 1 (Rain)", "FX 2 (Soundtrack)", "FX 3 (Crystal)", "FX 4 (Atmosphere)",
		"FX 5 (Brightness)", "FX 6 (Goblins)", "FX 7 (Echoes)", "FX 8 (Sci-Fi)",
		"Sitar", "Banjo", "Shamisen", "Koto",
		"Kalimba", "Bagpipe", "Fiddle", "Shanai",
		"Tinkle Bell", "Agogo", "Steel Drums", "Woodblock",
		"Taiko Drum", "Melodic Tom", "Synth Drum", "Reverse Cymbal",
		"Guitar Fret Noise", "Breath Noise", "Seashore", "Bird Tweet",
		"Telephone Ring", "Helicopter", "Applause", "Gunshot",
	]
	if program >= 0 and program < names.size():
		return names[program]
	return "Unknown(%d)" % program


## 解析 Meta 事件
static func _parse_meta_event(stream: StreamPeerBuffer) -> Dictionary:
	if stream.get_available_bytes() < 1:
		return {}

	var meta_type: int = stream.get_u8()
	var length: int = _read_vlq(stream)

	match meta_type:
		_META_TRACK_NAME:
			if stream.get_available_bytes() < length:
				return {}
			var text_bytes: PackedByteArray = stream.get_data(length)[1]
			return {
				"type": "meta_track_name",
				"name": text_bytes.get_string_from_ascii(),
			}

		_META_SET_TEMPO:
			if length != 3:
				# 跳过无效数据
				if stream.get_available_bytes() >= length:
					stream.get_data(length)
				return {}
			var us_per_beat: int = stream.get_u8() << 16
			us_per_beat |= stream.get_u8() << 8
			us_per_beat |= stream.get_u8()
			# 转换为 BPM: 60000000 / us_per_beat
			var bpm: int = 60000000 / us_per_beat
			return {
				"type": "meta_tempo",
				"tempo": bpm,
			}

		_META_END_OF_TRACK:
			return {
				"type": "meta_end_of_track",
			}

		_:
			# 跳过未知 meta 事件数据
			if stream.get_available_bytes() >= length:
				stream.get_data(length)
			return {}


## 跳过 SysEx 事件
static func _skip_sysex(stream: StreamPeerBuffer) -> void:
	var length: int = _read_vlq(stream)
	if stream.get_available_bytes() >= length:
		stream.get_data(length)

# -----------------------------------------------------------------------------
# VLQ 解码

## 读取 Variable-Length Quantity
## 每字节: bit 7 = 延续标志, bits 6-0 = 数据
static func _read_vlq(stream: StreamPeerBuffer) -> int:
	var value: int = 0
	for _i in range(4):  # MIDI/SF2 规范: VLQ 最多 4 字节
		if stream.get_available_bytes() < 1:
			break
		var byte: int = stream.get_u8()
		value = (value << 7) | (byte & 0x7F)
		if (byte & 0x80) == 0:
			break
	return value

# -----------------------------------------------------------------------------
# Format 0 处理

## 将 Format 0 的单轨道数据按通道拆分为多轨道
static func _build_format_0(timebase: int, track_raw_events: Array[Array]) -> ReadResult:
	# Format 0 只有一个轨道
	if track_raw_events.is_empty():
		return ReadResult.new(false, null, "Format 0 没有轨道数据")

	var raw_events: Array = track_raw_events[0]

	# 收集 tempo 和按通道分组的事件
	var tempo: int = 120
	var track_name: String = ""
	var channel_events: Dictionary = {}  # channel -> Array[Dictionary]
	var channel_instruments: Dictionary = {}  # channel -> int (取第一个 program_change)
	var tempo_events: Array[Dictionary] = []
	var cc_events: Array[Dictionary] = []
	var pitch_bend_events: Array[Dictionary] = []
	var program_events: Array[Dictionary] = []
	var channel_first_pc_seen: Dictionary = {}  # channel -> bool

	for event in raw_events:
		var event_type: String = event.get("type", "")
		match event_type:
			"meta_tempo":
				tempo = event.get("tempo", 120)
				tempo_events.append({"time_ticks": event["time_ticks"], "bpm": event["tempo"]})
			"meta_track_name":
				track_name = event.get("name", "")
			"note_on", "note_off", "program_change", "control_change", "pitch_bend":
				var ch: int = event.get("channel", 0)
				if not channel_events.has(ch):
					channel_events[ch] = []
					channel_instruments[ch] = 0
				channel_events[ch].append(event)
				if event_type == "program_change":
					if not channel_first_pc_seen.has(ch):
						channel_instruments[ch] = event.get("program", 0)
						channel_first_pc_seen[ch] = true
					program_events.append({
						"time_ticks": event.get("time_ticks", 0),
						"channel": ch,
						"preset_index": event.get("program", 0),
					})

	# 构建轨道列表
	var tracks: Array[TrackData] = []

	# 按通道编号排序
	var channels: Array = channel_events.keys()
	channels.sort()

	for ch in channels:
		var ch_events: Array = channel_events[ch]
		var notes: Array[NoteData] = _pair_notes(ch_events)

		# 从通道事件中提取 CC 和 Pitch Bend 到全局和轨道级数组
		var global_extracted: Dictionary = _extract_cc_and_pitch_bend(ch_events, true)
		cc_events.append_array(global_extracted["cc"])
		pitch_bend_events.append_array(global_extracted["pb"])
		var track_extracted: Dictionary = _extract_cc_and_pitch_bend(ch_events, false)
		var track_cc: Array[Dictionary] = track_extracted["cc"]
		var track_pb: Array[Dictionary] = track_extracted["pb"]

		var ch_name: String = track_name if track_name != "" and ch == channels[0] else ""
		if ch_name == "":
			ch_name = "Channel %d" % ch

		tracks.append(TrackData.new(ch_name, ch, channel_instruments[ch], notes, track_cc, track_pb))

	return ReadResult.new(true, MidiData.new(tempo, tracks, timebase, tempo_events, cc_events, pitch_bend_events, program_events))

## 将 Format 1 的多轨道原始事件构建为 MidiData
## 与 MidiWriter.encode() 的输出结构对应:
##   Track 0 = tempo track (meta events only)
##   Track 1..N = note tracks (name + program change + notes)
static func _build_format_1(timebase: int, track_raw_events: Array[Array]) -> ReadResult:
	var tempo: int = 120
	var tracks: Array[TrackData] = []
	var tempo_events: Array[Dictionary] = []
	var cc_events: Array[Dictionary] = []
	var pitch_bend_events: Array[Dictionary] = []
	var program_events: Array[Dictionary] = []

	# 只从第一个轨道提取初始 tempo 和所有轨道的 tempo 变化事件
	if not track_raw_events.is_empty():
		for event in track_raw_events[0]:
			if event.get("type") == "meta_tempo":
				tempo = event["tempo"]
				break

	# 从所有轨道收集 tempo 变化事件 (不覆盖初始 tempo)
	for track_idx in range(track_raw_events.size()):
		var raw_events: Array = track_raw_events[track_idx]
		for event in raw_events:
			if event.get("type") == "meta_tempo":
				tempo_events.append({"time_ticks": event["time_ticks"], "bpm": event["tempo"]})

	# 从非 tempo 轨道收集全局 CC、Pitch Bend 和 Program Change 事件
	for track_idx in range(1, track_raw_events.size()):
		var raw_events: Array = track_raw_events[track_idx]
		var extracted: Dictionary = _extract_cc_and_pitch_bend(raw_events, true)
		cc_events.append_array(extracted["cc"])
		pitch_bend_events.append_array(extracted["pb"])
		for event in raw_events:
			if event.get("type") == "program_change":
				program_events.append({
					"time_ticks": event.get("time_ticks", 0),
					"channel": event.get("channel", 0),
					"preset_index": event.get("program", 0),
				})

	for track_idx in range(track_raw_events.size()):
		var raw_events: Array = track_raw_events[track_idx]
		var track_data: TrackData = _build_track_from_events(raw_events, track_idx)

		if track_data == null:
			continue

		# 第一个轨道可能是 tempo track（不含音符）
		if track_idx == 0 and track_data.notes.is_empty():
			continue

		tracks.append(track_data)

	return ReadResult.new(true, MidiData.new(tempo, tracks, timebase, tempo_events, cc_events, pitch_bend_events, program_events))
## @param events 原始事件数组
## @param include_channel 是否在结果中包含 channel 字段
## @return Dictionary { "cc": Array[Dictionary], "pb": Array[Dictionary] }
static func _extract_cc_and_pitch_bend(events: Array, include_channel: bool) -> Dictionary:
	var cc_result: Array[Dictionary] = []
	var pb_result: Array[Dictionary] = []
	for event in events:
		var event_type: String = event.get("type", "")
		if event_type == "control_change":
			var entry: Dictionary = {
				"time_ticks": event.get("time_ticks", 0),
				"controller": event.get("controller", 0),
				"value": event.get("value", 0),
			}
			if include_channel:
				entry["channel"] = event.get("channel", 0)
			cc_result.append(entry)
		elif event_type == "pitch_bend":
			var entry: Dictionary = {
				"time_ticks": event.get("time_ticks", 0),
				"value": event.get("value", 0),
			}
			if include_channel:
				entry["channel"] = event.get("channel", 0)
			pb_result.append(entry)
	return {"cc": cc_result, "pb": pb_result}


## 从原始事件数组构建 TrackData
static func _build_track_from_events(raw_events: Array, track_idx: int) -> TrackData:
	var track_name: String = "Track %d" % track_idx
	var instrument: int = -1  # -1 表示未设置, 保留第一个 program_change
	var channel: int = -1  # -1 表示未确定

	# 第一遍：提取轨道名称、乐器和通道
	for event in raw_events:
		var event_type: String = event.get("type", "")
		if event_type == "meta_track_name":
			track_name = event.get("name", track_name)
		elif event_type == "program_change":
			if instrument < 0:
				instrument = event.get("program", 0)
			if channel < 0:
				channel = event.get("channel", 0)
		elif (event_type == "note_on" or event_type == "note_off") and channel < 0:
			# 没有 program_change 的轨道 (如鼓组) 从 note 事件获取通道
			channel = event.get("channel", 0)

	if instrument < 0:
		instrument = 0
	if channel < 0:
		channel = 0

	# 第二遍：配对音符
	var notes: Array[NoteData] = _pair_notes(raw_events)

	# 第三遍：提取 CC 和 Pitch Bend 事件（轨道级，不含 channel）
	var track_extracted: Dictionary = _extract_cc_and_pitch_bend(raw_events, false)
	var track_cc: Array[Dictionary] = track_extracted["cc"]
	var track_pb: Array[Dictionary] = track_extracted["pb"]

	return TrackData.new(track_name, channel, instrument, notes, track_cc, track_pb)

# -----------------------------------------------------------------------------
# Note On/Off 配对

## 将原始事件数组中的 Note On/Note Off 配对为 NoteData
static func _pair_notes(raw_events: Array) -> Array[NoteData]:
	var notes: Array[NoteData] = []
	# 按通道分组的活动音符: channel -> { pitch -> {time_ticks, velocity} }
	var active_notes: Dictionary = {}

	for event in raw_events:
		var event_type: String = event.get("type", "")

		if event_type == "note_on":
			var ch: int = event.get("channel", 0)
			var pitch: int = event.get("pitch", 0)
			var velocity: int = event.get("velocity", 0)
			var time_ticks: int = event.get("time_ticks", 0)

			if not active_notes.has(ch):
				active_notes[ch] = {}

			# 如果已有同 pitch 的活动音符，先关闭它
			if active_notes[ch].has(pitch):
				var active: Dictionary = active_notes[ch][pitch]
				var start_time: int = active["time_ticks"]
				var duration: int = time_ticks - start_time
				if duration > 0:
					notes.append(NoteData.new(pitch, start_time, duration, active["velocity"]))

			# 添加新的活动音符
			active_notes[ch][pitch] = {
				"time_ticks": time_ticks,
				"velocity": velocity,
			}

		elif event_type == "note_off":
			var ch: int = event.get("channel", 0)
			var pitch: int = event.get("pitch", 0)
			var time_ticks: int = event.get("time_ticks", 0)

			if active_notes.has(ch) and active_notes[ch].has(pitch):
				var active: Dictionary = active_notes[ch][pitch]
				var start_time: int = active["time_ticks"]
				var duration: int = time_ticks - start_time
				if duration > 0:
					notes.append(NoteData.new(pitch, start_time, duration, active["velocity"]))
				active_notes[ch].erase(pitch)

	return notes
