## MIDI SMF Type 1 二进制编码器
## 将 MidiData 编码为标准 MIDI 文件字节流
## 独立实现，不依赖 addons/midi/SMF.gd

class_name MidiWriter
extends RefCounted

# -----------------------------------------------------------------------------
# 常量

## MIDI 事件状态字节
const _STATUS_NOTE_OFF: int = 0x80
const _STATUS_NOTE_ON: int = 0x90
const _STATUS_CONTROL_CHANGE: int = 0xB0
const _STATUS_PROGRAM_CHANGE: int = 0xC0
const _STATUS_PITCH_BEND: int = 0xE0
const _STATUS_META: int = 0xFF

## Meta 事件类型
const _META_TRACK_NAME: int = 0x03
const _META_END_OF_TRACK: int = 0x2F
const _META_SET_TEMPO: int = 0x51
const _META_TIME_SIGNATURE: int = 0x58

## 事件优先级（用于同时间排序: Note Off < Note On）
const _PRIORITY_NOTE_OFF: int = 0
const _PRIORITY_NOTE_ON: int = 1
const _PRIORITY_PROGRAM_CHANGE: int = 2
const _PRIORITY_META: int = 3
const _PRIORITY_CONTROL_CHANGE: int = 4
const _PRIORITY_PITCH_BEND: int = 5

# -----------------------------------------------------------------------------
# 公开接口

## 将 MidiData 编码为 SMF Type 1 字节流
## @param midi_data MidiData 数据对象
## @return PackedByteArray 有效的 MIDI 文件二进制数据
static func encode(midi_data: MidiData) -> PackedByteArray:
	var stream: StreamPeerBuffer = StreamPeerBuffer.new()
	stream.big_endian = true

	_write_header(stream, midi_data)
	_write_tempo_track(stream, midi_data)

	for track_data in midi_data.tracks:
		# 创建临时轨道副本，合并全局事件
		var temp_track := TrackData.new(
			track_data.name, track_data.channel, track_data.instrument,
			track_data.notes.duplicate(),
			track_data.cc_events.duplicate(),
			track_data.pitch_bend_events.duplicate()
		)

		# 合并同通道的全局 CC events
		for cc in midi_data.cc_events:
			if int(cc.get("channel", 0)) == track_data.channel:
				temp_track.cc_events.append(cc)

		# 合并同通道的全局 Pitch Bend events
		for pb in midi_data.pitch_bend_events:
			if int(pb.get("channel", 0)) == track_data.channel:
				temp_track.pitch_bend_events.append(pb)

		_write_note_track(stream, temp_track)

	return stream.data_array

# -----------------------------------------------------------------------------
# Header Chunk

## 写入 MThd 头部
## 格式: "MThd" + 6字节大小 + format(2) + ntracks(2) + timebase(2)
static func _write_header(stream: StreamPeerBuffer, midi_data: MidiData) -> void:
	stream.put_data("MThd".to_ascii_buffer())
	stream.put_u32(6)  # header data size is always 6
	stream.put_u16(1)  # format type 1 (multi-track)
	stream.put_u16(midi_data.tracks.size() + 1)  # +1 for tempo track
	stream.put_u16(midi_data.timebase)

# -----------------------------------------------------------------------------
# Tempo Track (Track 0)

## 写入速度/元信息轨道
static func _write_tempo_track(stream: StreamPeerBuffer, midi_data: MidiData) -> void:
	var buf: StreamPeerBuffer = StreamPeerBuffer.new()
	buf.big_endian = true

	# 拍号 (delta=0)
	_write_variable_length_quantity(buf, 0)
	_write_meta_time_signature(buf)

	# 初始速度 (delta=0)
	_write_variable_length_quantity(buf, 0)
	_write_meta_tempo(buf, midi_data.tempo)

	# 额外的 tempo changes
	if midi_data.tempo_events.size() > 0:
		var last_tick: int = 0
		for tc in midi_data.tempo_events:
			var tc_tick: int = int(tc.get("time_ticks", 0))
			var tc_bpm: int = int(tc.get("bpm", 0))
			if tc_tick <= 0 or tc_bpm <= 0:
				continue
			var delta: int = tc_tick - last_tick
			last_tick = tc_tick
			_write_variable_length_quantity(buf, maxi(delta, 0))
			_write_meta_tempo(buf, tc_bpm)

	# 轨道结束 (delta=0)
	_write_variable_length_quantity(buf, 0)
	_write_meta_end_of_track(buf)

	_wrap_as_track_chunk(stream, buf)

# -----------------------------------------------------------------------------
# Note Tracks (Track 1..N)

## 写入音符轨道
static func _write_note_track(stream: StreamPeerBuffer, track_data: TrackData) -> void:
	var buf: StreamPeerBuffer = StreamPeerBuffer.new()
	buf.big_endian = true

	# 轨道名称 (delta=0)
	_write_variable_length_quantity(buf, 0)
	_write_meta_track_name(buf, track_data.name)

	# Program Change (delta=0)
	_write_variable_length_quantity(buf, 0)
	_write_program_change(buf, track_data.channel, track_data.instrument)

	# 收集所有 Note On / Note Off 事件
	var events: Array[Dictionary] = []
	for note in track_data.notes:
		events.append({
			"time": note.start_ticks,
			"type": _PRIORITY_NOTE_ON,
			"status": _STATUS_NOTE_ON | (track_data.channel & 0x0F),
			"pitch": note.pitch,
			"velocity": note.velocity,
		})
		events.append({
			"time": note.start_ticks + note.duration_ticks,
			"type": _PRIORITY_NOTE_OFF,
			"status": _STATUS_NOTE_OFF | (track_data.channel & 0x0F),
			"pitch": note.pitch,
			"velocity": 0,
		})

	# 收集 CC 事件
	for cc in track_data.cc_events:
		events.append({
			"time": cc.get("time_ticks", 0),
			"type": _PRIORITY_CONTROL_CHANGE,
			"status": _STATUS_CONTROL_CHANGE | (track_data.channel & 0x0F),
			"data1": cc.get("controller", 0),
			"data2": cc.get("value", 0),
		})

	# 收集 Pitch Bend 事件
	for pb in track_data.pitch_bend_events:
		var raw_value: int = pb.get("value", 0)
		var lsb: int = raw_value & 0x7F
		var msb: int = (raw_value >> 7) & 0x7F
		events.append({
			"time": pb.get("time_ticks", 0),
			"type": _PRIORITY_PITCH_BEND,
			"status": _STATUS_PITCH_BEND | (track_data.channel & 0x0F),
			"data1": lsb,
			"data2": msb,
		})

	# 按时间排序，同时间按优先级 (Note Off < Note On)
	events.sort_custom(_sort_events)

	# 写入事件（使用 delta time）
	var last_time: int = 0
	for event in events:
		var delta: int = event.time - last_time
		last_time = event.time
		_write_variable_length_quantity(buf, delta)
		buf.put_u8(event.status)
		var d1: int = event.get("data1", event.get("pitch", 0))
		var d2: int = event.get("data2", event.get("velocity", 0))
		buf.put_u8(d1 & 0x7F)
		buf.put_u8(d2 & 0x7F)

	# 轨道结束 (delta=0，与最后一个事件同一时刻)
	_write_variable_length_quantity(buf, 0)
	_write_meta_end_of_track(buf)

	_wrap_as_track_chunk(stream, buf)

# -----------------------------------------------------------------------------
# 排序比较

## 事件排序: 先按时间，同时间按优先级
static func _sort_events(a: Dictionary, b: Dictionary) -> bool:
	if a.time < b.time:
		return true
	if b.time < a.time:
		return false
	return a.type < b.type

# -----------------------------------------------------------------------------
# Variable-Length Quantity (VLQ)

## 写入可变长度数量
## 每字节低 7 位为数据，最高位为延续标志 (1=还有后续字节)
static func _write_variable_length_quantity(stream: StreamPeerBuffer, value: int) -> void:
	if value < 0:
		value = 0

	var bytes: Array[int] = []
	# 从 LSB 提取每 7 位
	while true:
		bytes.append(value & 0x7F)
		value >>= 7
		if value == 0:
			break

	# 反转使 MSB 在前，除最后一个字节外设置延续位
	for i in range(bytes.size() - 1, 0, -1):
		stream.put_u8(bytes[i] | 0x80)
	stream.put_u8(bytes[0])

# -----------------------------------------------------------------------------
# Meta 事件写入

## 拍号: FF 58 04 nn dd cc bb
## nn=分子, dd=分母的2的幂 (4→02), cc=MIDI时钟/四分音符(通常24), bb=32分音符/四分音符(通常8)
static func _write_meta_time_signature(stream: StreamPeerBuffer) -> void:
	stream.put_u8(_STATUS_META)
	stream.put_u8(_META_TIME_SIGNATURE)
	stream.put_u8(4)  # 数据长度
	stream.put_u8(4)  # 分子 (4/4)
	stream.put_u8(2)  # 分母 4 = 2^2，所以写入 2
	stream.put_u8(24) # MIDI 时钟/四分音符
	stream.put_u8(8)  # 32 分音符/四分音符

## 速度: FF 51 03 tt tt tt
## tttttt = 60,000,000 / BPM (微秒/四分音符)
static func _write_meta_tempo(stream: StreamPeerBuffer, bpm: int) -> void:
	var us_per_beat: int = 60000000 / bpm
	stream.put_u8(_STATUS_META)
	stream.put_u8(_META_SET_TEMPO)
	stream.put_u8(3)  # 数据长度
	stream.put_u8((us_per_beat >> 16) & 0xFF)
	stream.put_u8((us_per_beat >> 8) & 0xFF)
	stream.put_u8(us_per_beat & 0xFF)

## 轨道名称: FF 03 len text
static func _write_meta_track_name(stream: StreamPeerBuffer, name: String) -> void:
	var text_bytes: PackedByteArray = name.to_ascii_buffer()
	stream.put_u8(_STATUS_META)
	stream.put_u8(_META_TRACK_NAME)
	_write_variable_length_quantity(stream, text_bytes.size())
	stream.put_data(text_bytes)

## 轨道结束: FF 2F 00
static func _write_meta_end_of_track(stream: StreamPeerBuffer) -> void:
	stream.put_u8(_STATUS_META)
	stream.put_u8(_META_END_OF_TRACK)
	stream.put_u8(0)

# -----------------------------------------------------------------------------
# Channel 事件写入

## Program Change: Cn pp (n=channel, pp=program number)
static func _write_program_change(stream: StreamPeerBuffer, channel: int, program: int) -> void:
	stream.put_u8(_STATUS_PROGRAM_CHANGE | (channel & 0x0F))
	stream.put_u8(program & 0x7F)

# -----------------------------------------------------------------------------
# Track Chunk 封装

## 将缓冲区数据封装为 MTrk chunk 写入目标流
## 格式: "MTrk" + 4字节大小 + 数据
static func _wrap_as_track_chunk(stream: StreamPeerBuffer, data_buf: StreamPeerBuffer) -> void:
	stream.put_data("MTrk".to_ascii_buffer())
	stream.put_u32(data_buf.get_size())
	stream.put_data(data_buf.data_array)
