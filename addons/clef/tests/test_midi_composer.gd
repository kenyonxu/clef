## MIDI Composer 集成测试
## 用法: godot --headless --script addons/clef/tests/test_midi_composer.gd
## 测试全流程: JSON → Converter → Writer → 验证二进制输出

extends SceneTree

var _pass_count: int = 0
var _fail_count: int = 0


func _init() -> void:
	print("\n========================================")
	print("  MIDI Composer 集成测试")
	print("========================================\n")

	_test_basic_single_note()
	_test_multi_track()
	_test_validation_errors()
	_test_vlq_encoding()
	_test_cc_events()
	_test_pitch_bend_events()
	_test_tempo_changes()

	_print_summary()


func _ready() -> void:
	quit(1 if _fail_count > 0 else 0)


# =============================================================================
# Test 1: 单音符基本转换
# =============================================================================

func _test_basic_single_note() -> void:
	print("--- Test 1: 单音符基本转换 ---")

	var json_text := JSON.stringify({
		"format_version": "1.0",
		"tempo": 120,
		"tracks": [{
			"name": "Test Track",
			"channel": 0,
			"instrument": 0,
			"notes": [{
				"pitch": 60,
				"start": 0.0,
				"duration": 1.0,
				"velocity": 100,
			}],
		}],
	}, "  ")

	var result = MidiComposerConverter.from_json_string(json_text)

	_assert_true(result.ok, "ConvertResult.ok == true")
	_assert_not_null(result.midi_data, "midi_data 非 null")

	if result.midi_data == null:
		return

	_assert_eq(result.midi_data.tempo, 120, "tempo == 120")
	_assert_eq(result.midi_data.tracks.size(), 1, "tracks 数量 == 1")
	_assert_eq(result.midi_data.timebase, 480, "timebase == 480")

	# 验证音符 tick 转换
	# 120 BPM, 480 ticks/beat → 960 ticks/sec
	# start=0.0s → 0 ticks, duration=1.0s → 960 ticks
	var note = result.midi_data.tracks[0].notes[0]
	_assert_eq(note.pitch, 60, "pitch == 60")
	_assert_eq(note.velocity, 100, "velocity == 100")
	_assert_eq(note.start_ticks, 0, "start_ticks == 0")
	_assert_eq(note.duration_ticks, 960, "duration_ticks == 960")

	# 编码为二进制
	var binary: PackedByteArray = MidiWriter.encode(result.midi_data)

	# 验证 MThd header
	_assert_eq(binary.size() > 50, true, "二进制大小 > 50 字节 (实际: %d)" % binary.size())
	_assert_eq(binary[0], 0x4D, "binary[0] == 0x4D ('M')")
	_assert_eq(binary[1], 0x54, "binary[1] == 0x54 ('T')")
	_assert_eq(binary[2], 0x68, "binary[2] == 0x68 ('h')")
	_assert_eq(binary[3], 0x64, "binary[3] == 0x64 ('d')")

	# 验证 header 中的 track count
	# header: MThd(4) + size(4) + format(2) + ntracks(2) + timebase(2)
	var track_count: int = (binary[10] << 8) | binary[11]
	_assert_eq(track_count, 2, "header 中 track count == 2 (1 音轨 + 1 速度轨)")

	print("")


# =============================================================================
# Test 2: 多音轨转换 (4 轨道 + 1 速度轨)
# =============================================================================

func _test_multi_track() -> void:
	print("--- Test 2: 多音轨转换 (4 轨道示例) ---")

	var json_dict := {
		"format_version": "1.0",
		"tempo": 140,
		"tracks": [
			{
				"name": "Melody",
				"channel": 0,
				"instrument": 0,
				"notes": [
					{"pitch": 60, "start": 0.0, "duration": 0.5, "velocity": 100},
					{"pitch": 64, "start": 0.5, "duration": 0.5, "velocity": 100},
					{"pitch": 67, "start": 1.0, "duration": 0.5, "velocity": 100},
				],
			},
			{
				"name": "Bass",
				"channel": 1,
				"instrument": 32,
				"notes": [
					{"pitch": 48, "start": 0.0, "duration": 1.0, "velocity": 90},
					{"pitch": 43, "start": 1.0, "duration": 1.0, "velocity": 90},
				],
			},
			{
				"name": "Pad",
				"channel": 2,
				"instrument": 88,
				"notes": [
					{"pitch": 60, "start": 0.0, "duration": 2.0, "velocity": 60},
					{"pitch": 64, "start": 0.0, "duration": 2.0, "velocity": 60},
					{"pitch": 67, "start": 0.0, "duration": 2.0, "velocity": 60},
				],
			},
			{
				"name": "Drums",
				"channel": 9,
				"instrument": 0,
				"notes": [
					{"pitch": 36, "start": 0.0, "duration": 0.1, "velocity": 120},
					{"pitch": 38, "start": 0.5, "duration": 0.1, "velocity": 100},
					{"pitch": 36, "start": 1.0, "duration": 0.1, "velocity": 120},
				],
			},
		],
	}
	var json_text := JSON.stringify(json_dict, "  ")

	var result = MidiComposerConverter.from_json_string(json_text)

	_assert_true(result.ok, "ConvertResult.ok == true")
	_assert_not_null(result.midi_data, "midi_data 非 null")

	if result.midi_data == null:
		return

	_assert_eq(result.midi_data.tempo, 140, "tempo == 140")
	_assert_eq(result.midi_data.tracks.size(), 4, "音轨数量 == 4")

	# 验证各轨道名称
	_assert_eq(result.midi_data.tracks[0].name, "Melody", "Track 0 名称 == 'Melody'")
	_assert_eq(result.midi_data.tracks[1].name, "Bass", "Track 1 名称 == 'Bass'")
	_assert_eq(result.midi_data.tracks[2].name, "Pad", "Track 2 名称 == 'Pad'")
	_assert_eq(result.midi_data.tracks[3].name, "Drums", "Track 3 名称 == 'Drums'")

	# 验证各轨道 channel
	_assert_eq(result.midi_data.tracks[0].channel, 0, "Melody channel == 0")
	_assert_eq(result.midi_data.tracks[1].channel, 1, "Bass channel == 1")
	_assert_eq(result.midi_data.tracks[2].channel, 2, "Pad channel == 2")
	_assert_eq(result.midi_data.tracks[3].channel, 9, "Drums channel == 9")

	# 验证音符数量
	_assert_eq(result.midi_data.tracks[0].notes.size(), 3, "Melody 音符数 == 3")
	_assert_eq(result.midi_data.tracks[1].notes.size(), 2, "Bass 音符数 == 2")
	_assert_eq(result.midi_data.tracks[2].notes.size(), 3, "Pad 音符数 == 3")
	_assert_eq(result.midi_data.tracks[3].notes.size(), 3, "Drums 音符数 == 3")

	# 编码为二进制
	var binary: PackedByteArray = MidiWriter.encode(result.midi_data)

	_assert_eq(binary.size() > 200, true, "二进制大小 > 200 字节 (实际: %d)" % binary.size())

	# 验证 header track count = 5 (4 音轨 + 1 速度轨)
	var track_count: int = (binary[10] << 8) | binary[11]
	_assert_eq(track_count, 5, "header 中 track count == 5 (4 音轨 + 1 速度轨)")

	# 验证 timebase
	var timebase: int = (binary[12] << 8) | binary[13]
	_assert_eq(timebase, 480, "timebase == 480")

	print("")


# =============================================================================
# Test 3: 验证错误
# =============================================================================

func _test_validation_errors() -> void:
	print("--- Test 3: 验证错误 ---")

	# 3a: 缺少 tempo
	var no_tempo := JSON.stringify({
		"format_version": "1.0",
		"tracks": [{
			"name": "Test",
			"channel": 0,
			"instrument": 0,
			"notes": [{"pitch": 60, "start": 0.0, "duration": 1.0, "velocity": 100}],
		}],
	})
	var r1 = MidiComposerConverter.from_json_string(no_tempo)
	_assert_true(not r1.ok, "缺少 tempo → ok == false")
	_assert_true(r1.error_message != "", "缺少 tempo → error_message 非空")
	_assert_true("tempo" in r1.error_message.to_lower(), "error_message 包含 'tempo'")

	# 3b: 不支持的 format_version
	var bad_version := JSON.stringify({
		"format_version": "2.0",
		"tempo": 120,
		"tracks": [{
			"name": "Test",
			"channel": 0,
			"instrument": 0,
			"notes": [{"pitch": 60, "start": 0.0, "duration": 1.0, "velocity": 100}],
		}],
	})
	var r2 = MidiComposerConverter.from_json_string(bad_version)
	_assert_true(not r2.ok, "无效 format_version → ok == false")
	_assert_true(r2.error_message != "", "无效 format_version → error_message 非空")
	_assert_true("format_version" in r2.error_message.to_lower(), "error_message 包含 'format_version'")

	# 3c: 空 tracks 数组
	var empty_tracks := JSON.stringify({
		"format_version": "1.0",
		"tempo": 120,
		"tracks": [],
	})
	var r3 = MidiComposerConverter.from_json_string(empty_tracks)
	_assert_true(not r3.ok, "空 tracks → ok == false")
	_assert_true(r3.error_message != "", "空 tracks → error_message 非空")
	_assert_true("tracks" in r3.error_message.to_lower(), "error_message 包含 'tracks'")

	# 3d: 无效 JSON
	var r4 = MidiComposerConverter.from_json_string("not valid json {{{")
	_assert_true(not r4.ok, "无效 JSON → ok == false")
	_assert_true(r4.error_message != "", "无效 JSON → error_message 非空")

	# 3e: 根元素不是对象
	var r5 = MidiComposerConverter.from_json_string("[1, 2, 3]")
	_assert_true(not r5.ok, "根元素非对象 → ok == false")

	# 3f: tempo 为 0
	var zero_tempo := JSON.stringify({
		"format_version": "1.0",
		"tempo": 0,
		"tracks": [{
			"name": "Test",
			"channel": 0,
			"instrument": 0,
			"notes": [{"pitch": 60, "start": 0.0, "duration": 1.0, "velocity": 100}],
		}],
	})
	var r6 = MidiComposerConverter.from_json_string(zero_tempo)
	_assert_true(not r6.ok, "tempo == 0 → ok == false")

	print("")


# =============================================================================
# Test 4: VLQ 编码验证
# =============================================================================

func _test_vlq_encoding() -> void:
	print("--- Test 4: VLQ 编码验证 ---")

	# 120 BPM → 960 ticks/sec
	# 一个 start=0.5s 的音符 → start_ticks = 480
	# 480 > 127，所以 delta time 需要多字节 VLQ 编码
	var json_text := JSON.stringify({
		"format_version": "1.0",
		"tempo": 120,
		"tracks": [{
			"name": "VLQ Test",
			"channel": 0,
			"instrument": 0,
			"notes": [
				{"pitch": 60, "start": 0.0, "duration": 0.5, "velocity": 100},
				{"pitch": 72, "start": 0.5, "duration": 0.5, "velocity": 100},
			],
		}],
	})

	var result = MidiComposerConverter.from_json_string(json_text)
	_assert_true(result.ok, "VLQ 测试: 转换成功")
	_assert_not_null(result.midi_data, "VLQ 测试: midi_data 非 null")

	if result.midi_data == null:
		return

	# 验证 tick 转换
	_assert_eq(result.midi_data.tracks[0].notes[0].start_ticks, 0, "note0 start_ticks == 0")
	_assert_eq(result.midi_data.tracks[0].notes[0].duration_ticks, 480, "note0 duration_ticks == 480")
	_assert_eq(result.midi_data.tracks[0].notes[1].start_ticks, 480, "note1 start_ticks == 480")
	_assert_eq(result.midi_data.tracks[0].notes[1].duration_ticks, 480, "note1 duration_ticks == 480")

	# 编码为二进制
	var binary: PackedByteArray = MidiWriter.encode(result.midi_data)
	_assert_eq(binary.size() > 50, true, "VLQ 测试: 二进制大小 > 50 字节 (实际: %d)" % binary.size())

	# 验证 MThd
	_assert_eq(binary[0], 0x4D, "VLQ 测试: MThd header 正确")

	# 搜索 VLQ(480) 编码序列: 0x83 0x60
	var vlq_found: bool = false
	for i in range(binary.size() - 1):
		if binary[i] == 0x83 and binary[i + 1] == 0x60:
			vlq_found = true
			break

	_assert_true(vlq_found, "在二进制中找到 VLQ(480) 编码序列 0x83 0x60")

	# 额外验证：解码 VLQ 回 480
	var vlq_bytes: PackedByteArray = [0x83, 0x60]
	var decoded_value: int = _decode_vlq(vlq_bytes)
	_assert_eq(decoded_value, 480, "VLQ(0x83, 0x60) 解码 == 480")

	print("")


# =============================================================================
# 辅助函数
# =============================================================================

func _decode_vlq(bytes: PackedByteArray) -> int:
	var value: int = 0
	for b in bytes:
		value = (value << 7) | (b & 0x7F)
		if (b & 0x80) == 0:
			break
	return value


# =============================================================================
# 断言函数
# =============================================================================

func _assert_true(condition: bool, description: String) -> void:
	if condition:
		_pass_count += 1
		print("  [PASS] %s" % description)
	else:
		_fail_count += 1
		print("  [FAIL] %s" % description)


func _assert_eq(actual: Variant, expected: Variant, description: String) -> void:
	var passed: bool = actual == expected
	if passed:
		_pass_count += 1
		print("  [PASS] %s" % description)
	else:
		_fail_count += 1
		print("  [FAIL] %s (expected: %s, actual: %s)" % [description, expected, actual])


func _assert_not_null(value: Variant, description: String) -> void:
	var passed: bool = value != null
	if passed:
		_pass_count += 1
		print("  [PASS] %s" % description)
	else:
		_fail_count += 1
		print("  [FAIL] %s (value is null)" % description)


# =============================================================================
# Test 5: CC 事件转换
# =============================================================================

func _test_cc_events() -> void:
	print("--- Test 5: CC 事件转换 ---")

	var json_text := JSON.stringify({
		"format_version": "1.1",
		"tempo": 120,
		"tracks": [{
			"name": "CC Test",
			"channel": 0,
			"instrument": 0,
			"notes": [{"pitch": 60, "start": 0.0, "duration": 1.0, "velocity": 100}],
			"cc_events": [
				{"time": 0.0, "controller": 7, "value": 100},
				{"time": 0.5, "controller": 10, "value": 64},
				{"time": 1.0, "controller": 1, "value": 64}
			],
		}],
	})

	var result = MidiComposerConverter.from_json_string(json_text)
	_assert_true(result.ok, "CC 测试: 转换成功")
	_assert_not_null(result.midi_data, "CC 测试: midi_data 非 null")

	if result.midi_data == null:
		return

	var track: TrackData = result.midi_data.tracks[0]
	_assert_eq(track.cc_events.size(), 3, "CC 测试: 3 个 CC 事件")

	# 120 BPM, 480 ticks/beat → 960 ticks/sec
	# time=0.0 → 0 ticks
	_assert_eq(track.cc_events[0]["time_ticks"], 0, "CC0 time_ticks == 0")
	_assert_eq(track.cc_events[0]["controller"], 7, "CC0 controller == 7 (volume)")
	_assert_eq(track.cc_events[0]["value"], 100, "CC0 value == 100")

	# time=0.5 → 480 ticks
	_assert_eq(track.cc_events[1]["time_ticks"], 480, "CC1 time_ticks == 480")
	_assert_eq(track.cc_events[1]["controller"], 10, "CC1 controller == 10 (pan)")

	# time=1.0 → 960 ticks
	_assert_eq(track.cc_events[2]["time_ticks"], 960, "CC2 time_ticks == 960")
	_assert_eq(track.cc_events[2]["controller"], 1, "CC2 controller == 1 (modulation)")

	# 向后兼容: v1.0 无 cc_events 不报错
	var v10_json := JSON.stringify({
		"format_version": "1.0",
		"tempo": 120,
		"tracks": [{
			"name": "V10",
			"channel": 0,
			"instrument": 0,
			"notes": [{"pitch": 60, "start": 0.0, "duration": 1.0, "velocity": 100}],
		}],
	})
	var v10_result = MidiComposerConverter.from_json_string(v10_json)
	_assert_true(v10_result.ok, "v1.0 向后兼容: 转换成功")
	_assert_eq(v10_result.midi_data.tracks[0].cc_events.size(), 0, "v1.0 向后兼容: 无 CC 事件")

	print("")


# =============================================================================
# Test 6: Pitch Bend 事件转换
# =============================================================================

func _test_pitch_bend_events() -> void:
	print("--- Test 6: Pitch Bend 事件转换 ---")

	var json_text := JSON.stringify({
		"format_version": "1.1",
		"tempo": 120,
		"tracks": [{
			"name": "PB Test",
			"channel": 0,
			"instrument": 0,
			"notes": [{"pitch": 60, "start": 0.0, "duration": 2.0, "velocity": 100}],
			"pitch_bend_events": [
				{"time": 0.5, "value": 0},
				{"time": 1.0, "value": 8192},
				{"time": 1.5, "value": 16383}
			],
		}],
	})

	var result = MidiComposerConverter.from_json_string(json_text)
	_assert_true(result.ok, "PB 测试: 转换成功")
	_assert_not_null(result.midi_data, "PB 测试: midi_data 非 null")

	if result.midi_data == null:
		return

	var track: TrackData = result.midi_data.tracks[0]
	_assert_eq(track.pitch_bend_events.size(), 3, "PB 测试: 3 个 PB 事件")

	# time=0.5 → 480 ticks
	_assert_eq(track.pitch_bend_events[0]["time_ticks"], 480, "PB0 time_ticks == 480")
	_assert_eq(track.pitch_bend_events[0]["value"], 0, "PB0 value == 0 (min bend)")

	# time=1.0 → 960 ticks
	_assert_eq(track.pitch_bend_events[1]["time_ticks"], 960, "PB1 time_ticks == 960")
	_assert_eq(track.pitch_bend_events[1]["value"], 8192, "PB1 value == 8192 (center)")

	# time=1.5 → 1440 ticks
	_assert_eq(track.pitch_bend_events[2]["time_ticks"], 1440, "PB2 time_ticks == 1440")
	_assert_eq(track.pitch_bend_events[2]["value"], 16383, "PB2 value == 16383 (max bend)")

	# clamp 验证: 超范围值被截断
	var clamp_json := JSON.stringify({
		"format_version": "1.1",
		"tempo": 120,
		"tracks": [{
			"name": "Clamp",
			"channel": 0,
			"instrument": 0,
			"notes": [{"pitch": 60, "start": 0.0, "duration": 1.0, "velocity": 100}],
			"pitch_bend_events": [
				{"time": 0.0, "value": -100},
				{"time": 0.0, "value": 99999}
			],
		}],
	})
	var clamp_result = MidiComposerConverter.from_json_string(clamp_json)
	_assert_true(clamp_result.ok, "clamp 测试: 转换成功")
	var pb: Array[Dictionary] = clamp_result.midi_data.tracks[0].pitch_bend_events
	_assert_eq(pb[0]["value"], 0, "clamp 测试: -100 → 0")
	_assert_eq(pb[1]["value"], 16383, "clamp 测试: 99999 → 16383")

	print("")


# =============================================================================
# Test 7: Tempo 变化转换
# =============================================================================

func _test_tempo_changes() -> void:
	print("--- Test 7: Tempo 变化转换 ---")

	var json_text := JSON.stringify({
		"format_version": "1.1",
		"tempo": 120,
		"tempo_changes": [
			{"time": 2.0, "bpm": 80},
			{"time": 4.0, "bpm": 160}
		],
		"tracks": [{
			"name": "Tempo Test",
			"channel": 0,
			"instrument": 0,
			"notes": [{"pitch": 60, "start": 0.0, "duration": 1.0, "velocity": 100}],
		}],
	})

	var result = MidiComposerConverter.from_json_string(json_text)
	_assert_true(result.ok, "Tempo 测试: 转换成功")
	_assert_not_null(result.midi_data, "Tempo 测试: midi_data 非 null")

	if result.midi_data == null:
		return

	_assert_eq(result.midi_data.tempo_events.size(), 2, "Tempo 测试: 2 个 tempo 变化")

	# 初始 tempo 120 BPM → 960 ticks/sec, time=2.0 → 1920 ticks
	_assert_eq(result.midi_data.tempo_events[0]["time_ticks"], 1920, "Tempo0 time_ticks == 1920")
	_assert_eq(result.midi_data.tempo_events[0]["bpm"], 80, "Tempo0 bpm == 80")

	# time=4.0 → 3840 ticks (仍用初始 tempo 计算秒→tick)
	_assert_eq(result.midi_data.tempo_events[1]["time_ticks"], 3840, "Tempo1 time_ticks == 3840")
	_assert_eq(result.midi_data.tempo_events[1]["bpm"], 160, "Tempo1 bpm == 160")

	# 向后兼容: v1.0 无 tempo_changes 不报错
	var v10_json := JSON.stringify({
		"format_version": "1.0",
		"tempo": 120,
		"tracks": [{
			"name": "V10",
			"channel": 0,
			"instrument": 0,
			"notes": [{"pitch": 60, "start": 0.0, "duration": 1.0, "velocity": 100}],
		}],
	})
	var v10_result = MidiComposerConverter.from_json_string(v10_json)
	_assert_true(v10_result.ok, "v1.0 向后兼容: 转换成功")
	_assert_eq(v10_result.midi_data.tempo_events.size(), 0, "v1.0 向后兼容: 无 tempo 变化")

	# 无效 bpm 被跳过
	var bad_json := JSON.stringify({
		"format_version": "1.1",
		"tempo": 120,
		"tempo_changes": [
			{"time": 1.0, "bpm": 0},
			{"time": 2.0, "bpm": 100},
			{"not": "a dict"}
		],
		"tracks": [{
			"name": "Bad",
			"channel": 0,
			"instrument": 0,
			"notes": [{"pitch": 60, "start": 0.0, "duration": 1.0, "velocity": 100}],
		}],
	})
	var bad_result = MidiComposerConverter.from_json_string(bad_json)
	_assert_true(bad_result.ok, "无效 tempo 测试: 转换成功")
	_assert_eq(bad_result.midi_data.tempo_events.size(), 1, "无效 tempo 测试: 仅有效项保留")

	print("")


# =============================================================================
# 汇总
# =============================================================================

func _print_summary() -> void:
	print("========================================")
	var total: int = _pass_count + _fail_count
	print("  结果: %d / %d 通过" % [_pass_count, total])
	if _fail_count > 0:
		print("  状态: 失败 (%d 个断言未通过)" % _fail_count)
	else:
		print("  状态: 全部通过")
	print("========================================")
