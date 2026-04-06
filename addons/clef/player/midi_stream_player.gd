@icon("res://addons/clef/icons/clef-icon-pixel.svg")
## MIDI 流播放器 — 通过 AudioStreamPlayer 池播放 MIDI 资源
## 每个音符使用独立的 AudioStreamPlayer 播放预生成的 AudioStreamWAV
## 音高变换通过 pitch_scale, ADSR 通过 volume_db, 混音由 C++ AudioServer 完成
@tool
class_name MidiStreamPlayer
extends Node

@export var midi_resource: MidiResource : set = set_midi_resource
@export_file("*.sf2") var soundfont: String = "" : set = set_soundfont
@export var loop: bool = false
@export var autoplay: bool = false
@export_range(-80.0, 24.0, 0.1) var volume_db: float = -20.0 : set = set_volume_db
@export_range(0.01, 4.0, 0.01) var pitch_scale: float = 1.0 : set = set_pitch_scale

@export_group("Audio Effects", "")
@export var reverb_enabled: bool = true : set = set_reverb_enabled
@export_range(0.0, 1.0, 0.01) var reverb_room_size: float = 0.29 : set = set_reverb_room_size
@export_range(0.0, 1.0, 0.01) var reverb_wet: float = 0.15 : set = set_reverb_wet
@export var chorus_enabled: bool = true : set = set_chorus_enabled
@export_range(0.0, 1.0, 0.01) var chorus_wet: float = 0.2 : set = set_chorus_wet

@export_subgroup("Compressor", "")
@export var compressor_enabled: bool = false : set = set_compressor_enabled
@export_range(-60.0, 0.0, 1.0) var compressor_threshold_db: float = -12.0 : set = set_compressor_threshold_db
@export_range(1.0, 64.0, 0.1) var compressor_ratio: float = 4.0 : set = set_compressor_ratio
@export_range(-20.0, 20.0, 0.1) var compressor_gain_db: float = 0.0 : set = set_compressor_gain_db

@export_subgroup("Equalizer", "")
@export var eq_enabled: bool = false : set = set_eq_enabled

@export_group("Advanced", "")
@export_range(0.1, 2.0, 0.1) var release_multiplier: float = 1.0
@export_range(1, 128, 1) var max_polyphony: int = 64
var bus: String = "Master" : set = set_bus


signal note_triggered(channel: int, pitch: int, velocity: int)
signal note_released(channel: int, pitch: int)
signal cc_received(channel: int, controller: int, value: int)
signal pitch_bend_received(channel: int, value: int)
signal program_changed(channel: int, preset_index: int)
signal finished
signal progress_updated(position: float, duration: float)

const PROGRESS_UPDATE_INTERVAL_FRAMES: int = 6  # ~10Hz @ 60fps

var _progress_frame: int = 0
var _clef_bank: ClefBank
var _voice_pool: ClefVoicePool
var _current_tick: float = 0.0
var _is_paused: bool = false
var _is_playing: bool = false
var _clef_master_bus_idx: int = -1
## 编辑器预览播放时绕过 _process 中的 editor_hint 守卫
var _editor_preview: bool = false
var _debug_note_counts: Dictionary = {}
var _muted_channels: Array[int] = []
## 混音台独立音量 (0.0-1.0)，与 CC#7 volume 分离
var _mixer_volumes: Array[float] = []
## 调试: 设为 >= 0 时仅播放该通道 (-1 = 全部通道)
@export var debug_channel_filter: int = -1 : set = _set_debug_channel_filter
var _debug_channel_filter: int = -1

func _set_debug_channel_filter(v: int) -> void:
	_debug_channel_filter = v


## 启用编辑器预览模式
func enable_editor_preview() -> void:
	_editor_preview = true

# 音序器状态
var _sorted_events: Array[Dictionary] = []
var _event_index: int = 0
var _ticks_per_second: float = 960.0
var _timebase: int = 480
var _duration_ticks: int = 0
var _channel_instruments: Dictionary = {}
var _channel_states: Array[MidiChannelState] = []


func _get_property_list() -> Array[Dictionary]:
	var bus_names: PackedStringArray = []
	for i in range(AudioServer.get_bus_count()):
		var bus_name: String = AudioServer.get_bus_name(i)
		if not bus_name.begins_with("clef_"):
			bus_names.append(bus_name)
	return [{
		"name": "bus",
		"type": TYPE_STRING,
		"hint": PROPERTY_HINT_ENUM,
		"hint_string": ",".join(bus_names),
	}]


func _ready() -> void:
	for i in range(16):
		_channel_states.append(MidiChannelState.new())
		_mixer_volumes.append(1.0)
	_clef_bank = ClefBank.new()
	if _editor_preview:
		call_deferred("_editor_preview_init")
	else:
		_voice_pool = ClefVoicePool.new(self, max_polyphony)
		_setup_audio_buses()
		set_volume_db(volume_db)
		set_bus(bus)
		if soundfont != "":
			set_soundfont(soundfont)
		call_deferred("_deferred_play")


func _deferred_play() -> void:
	if Engine.is_editor_hint():
		return
	if autoplay:
		start_playback()


func _editor_preview_init() -> void:
	_voice_pool = ClefVoicePool.new(self, max_polyphony)
	_setup_audio_buses()
	set_volume_db(volume_db)
	set_bus(bus)
	if soundfont != "":
		set_soundfont(soundfont)


func set_midi_resource(value: MidiResource) -> void:
	midi_resource = value


func set_soundfont(path: String) -> void:
	soundfont = path
	if _clef_bank == null:
		return
	if path == "" or not FileAccess.file_exists(path):
		_clef_bank.load_from_sf2(null)
		return
	var result := Sf2Reader.read_file(path)
	if result.ok:
		_clef_bank.load_from_sf2(result.data)
	else:
		push_error("MidiStreamPlayer: SF2 加载失败: " + result.error_message)


func set_volume_db(value: float) -> void:
	volume_db = value
	if _clef_master_bus_idx >= 0:
		AudioServer.set_bus_volume_db(_clef_master_bus_idx, value)


func set_pitch_scale(value: float) -> void:
	pitch_scale = value
	if _voice_pool != null:
		for voice in _voice_pool.get_active_voices():
			voice.set_master_pitch_scale(value)


func set_bus(value: String) -> void:
	bus = value
	if _clef_master_bus_idx >= 0:
		AudioServer.set_bus_send(_clef_master_bus_idx, value)


## 设置音频总线 (ClefMaster + 16 个通道总线)

# --- Reverb setter ---
func _get_reverb_effect(bus_idx: int) -> AudioEffectReverb:
	for i in range(AudioServer.get_bus_effect_count(bus_idx)):
		var effect = AudioServer.get_bus_effect(bus_idx, i)
		if effect is AudioEffectReverb:
			return effect
	return null

func set_reverb_enabled(value: bool) -> void:
	reverb_enabled = value
	if _clef_master_bus_idx >= 0:
		var eff := _get_reverb_effect(_clef_master_bus_idx)
		if eff != null:
			AudioServer.set_bus_effect_enabled(_clef_master_bus_idx, _get_effect_index(_clef_master_bus_idx, eff), value)

func set_reverb_room_size(value: float) -> void:
	reverb_room_size = value
	if _clef_master_bus_idx >= 0:
		var eff := _get_reverb_effect(_clef_master_bus_idx)
		if eff != null:
			eff.room_size = value

func set_reverb_wet(value: float) -> void:
	reverb_wet = value
	if _clef_master_bus_idx >= 0:
		var eff := _get_reverb_effect(_clef_master_bus_idx)
		if eff != null:
			eff.wet = value

# --- Chorus setter ---
func _get_chorus_effect(bus_idx: int) -> AudioEffectChorus:
	for i in range(AudioServer.get_bus_effect_count(bus_idx)):
		var effect = AudioServer.get_bus_effect(bus_idx, i)
		if effect is AudioEffectChorus:
			return effect
	return null

func set_chorus_enabled(value: bool) -> void:
	chorus_enabled = value
	if _clef_master_bus_idx >= 0:
		var eff := _get_chorus_effect(_clef_master_bus_idx)
		if eff != null:
			AudioServer.set_bus_effect_enabled(_clef_master_bus_idx, _get_effect_index(_clef_master_bus_idx, eff), value)

func set_chorus_wet(value: float) -> void:
	chorus_wet = value
	if _clef_master_bus_idx >= 0:
		var eff := _get_chorus_effect(_clef_master_bus_idx)
		if eff != null:
			eff.wet = value

# --- Compressor setter ---
func set_compressor_enabled(v: bool) -> void:
	compressor_enabled = v
	_update_compressor()

func set_compressor_threshold_db(v: float) -> void:
	compressor_threshold_db = v
	_update_compressor()

func set_compressor_ratio(v: float) -> void:
	compressor_ratio = v
	_update_compressor()

func set_compressor_gain_db(v: float) -> void:
	compressor_gain_db = v
	_update_compressor()

func _update_compressor() -> void:
	if _clef_master_bus_idx < 0:
		return
	for i in range(AudioServer.get_bus_effect_count(_clef_master_bus_idx)):
		var effect = AudioServer.get_bus_effect(_clef_master_bus_idx, i)
		if effect is AudioEffectCompressor:
			AudioServer.set_bus_effect_enabled(_clef_master_bus_idx, i, compressor_enabled)
			effect.threshold = compressor_threshold_db
			effect.ratio = compressor_ratio
			effect.gain = compressor_gain_db
			return

	# --- EQ6 setter ---
func set_eq_enabled(v: bool) -> void:
	eq_enabled = v
	_update_eq()

func _update_eq() -> void:
	if _clef_master_bus_idx < 0:
		return
	for i in range(AudioServer.get_bus_effect_count(_clef_master_bus_idx)):
		var effect = AudioServer.get_bus_effect(_clef_master_bus_idx, i)
		if effect is AudioEffectEQ6:
			AudioServer.set_bus_effect_enabled(_clef_master_bus_idx, i, eq_enabled)
			return

# --- Helper ---
func _get_effect_index(bus_idx: int, effect: AudioEffect) -> int:
	for i in range(AudioServer.get_bus_effect_count(bus_idx)):
		if AudioServer.get_bus_effect(bus_idx, i) == effect:
			return i
	return -1

func _setup_audio_buses() -> void:
	# 检查主总线是否已存在
	var existing_idx := AudioServer.get_bus_index("ClefMaster")
	if existing_idx >= 0:
		_clef_master_bus_idx = existing_idx
	else:
		AudioServer.add_bus(-1)
		_clef_master_bus_idx = AudioServer.get_bus_count() - 1
		AudioServer.set_bus_name(_clef_master_bus_idx, "ClefMaster")
		AudioServer.set_bus_send(_clef_master_bus_idx, bus)
	AudioServer.set_bus_volume_db(_clef_master_bus_idx, volume_db)
	# --- Compressor (ensure existence on ClefMaster) ---
	var has_compressor := false
	for k in range(AudioServer.get_bus_effect_count(_clef_master_bus_idx)):
		if AudioServer.get_bus_effect(_clef_master_bus_idx, k) is AudioEffectCompressor:
			has_compressor = true
			break
	if not has_compressor:
		var compressor := AudioEffectCompressor.new()
		compressor.threshold = compressor_threshold_db
		compressor.ratio = compressor_ratio
		compressor.gain = compressor_gain_db
		compressor.attack_us = 20.0
		compressor.release_ms = 250.0
		AudioServer.add_bus_effect(_clef_master_bus_idx, compressor)
		AudioServer.set_bus_effect_enabled(_clef_master_bus_idx,
			AudioServer.get_bus_effect_count(_clef_master_bus_idx) - 1, compressor_enabled)
	# --- EQ6 (ensure existence on ClefMaster) ---
	var has_eq := false
	for k in range(AudioServer.get_bus_effect_count(_clef_master_bus_idx)):
		if AudioServer.get_bus_effect(_clef_master_bus_idx, k) is AudioEffectEQ6:
			has_eq = true
			break
	if not has_eq:
		var eq := AudioEffectEQ6.new()
		AudioServer.add_bus_effect(_clef_master_bus_idx, eq)
		AudioServer.set_bus_effect_enabled(_clef_master_bus_idx,
			AudioServer.get_bus_effect_count(_clef_master_bus_idx) - 1, eq_enabled)
	# --- Reverb/Chorus (ensure existence on ClefMaster) ---
	var has_reverb := false
	for k in range(AudioServer.get_bus_effect_count(_clef_master_bus_idx)):
		if AudioServer.get_bus_effect(_clef_master_bus_idx, k) is AudioEffectReverb:
			has_reverb = true
			break
	if not has_reverb:
		var reverb := AudioEffectReverb.new()
		reverb.predelay_msec = 15.0
		reverb.room_size = reverb_room_size
		reverb.damping = 0.3
		reverb.hipass = 0.05
		reverb.wet = reverb_wet
		AudioServer.add_bus_effect(_clef_master_bus_idx, reverb)
	var has_chorus := false
	for k in range(AudioServer.get_bus_effect_count(_clef_master_bus_idx)):
		if AudioServer.get_bus_effect(_clef_master_bus_idx, k) is AudioEffectChorus:
			has_chorus = true
			break
	if not has_chorus:
		var chorus := AudioEffectChorus.new()
		chorus.wet = chorus_wet
		AudioServer.add_bus_effect(_clef_master_bus_idx, chorus)
	# 为每个通道创建子总线（如已存在则跳过）
	for i in range(16):
		var ch_name := "clef_ch_%d" % i
		var ch_idx := AudioServer.get_bus_index(ch_name)
		if ch_idx < 0:
			AudioServer.add_bus(-1)
			ch_idx = AudioServer.get_bus_count() - 1
			AudioServer.set_bus_name(ch_idx, ch_name)
			AudioServer.set_bus_send(ch_idx, "ClefMaster")
			AudioServer.set_bus_volume_db(ch_idx, 0.0)
			var panner := AudioEffectPanner.new()
			panner.pan = 0.0
			AudioServer.add_bus_effect(ch_idx, panner)
func start_playback(from_position: float = 0.0) -> void:
	if _clef_master_bus_idx >= 0:
		AudioServer.set_bus_volume_db(_clef_master_bus_idx, volume_db)
	if midi_resource == null:
		push_warning("MidiStreamPlayer: midi_resource 为空")
		return
	if soundfont == "":
		var default_sf2: String = ProjectSettings.get_setting("clef/default_soundfont", "")
		if default_sf2 != "":
			set_soundfont(default_sf2)
	_build_sorted_events()
	# 初始化 _ticks_per_second 后再转换起始位置
	_current_tick = from_position * _ticks_per_second
	_is_paused = false
	_is_playing = true
	# 预处理: 跳到目标位置前的所有 tempo/program 事件
	_preprocess_events_up_to(int(_current_tick))
	# 取消静音 (如果之前是暂停状态)
	if _clef_master_bus_idx >= 0:
		AudioServer.set_bus_mute(_clef_master_bus_idx, false)


## 停止播放（快速衰减，避免 click/pop）
func stop() -> void:
	if _voice_pool != null:
		_voice_pool.quick_stop_all()
	_current_tick = 0.0
	_is_paused = false
	_is_playing = false
	_event_index = 0
	for state in _channel_states:
		state.reset()
	for i in range(16):
		_apply_channel_volume(i)


## 暂停播放 (真暂停 — 静音但保留所有语音状态)
func pause() -> void:
	if not _is_playing:
		return
	_is_paused = true
	if _clef_master_bus_idx >= 0:
		AudioServer.set_bus_mute(_clef_master_bus_idx, true)
	if _voice_pool != null:
		_voice_pool.pause_all()


## 恢复播放
func resume() -> void:
	if not _is_paused:
		return
	_is_paused = false
	if _clef_master_bus_idx >= 0:
		AudioServer.set_bus_mute(_clef_master_bus_idx, false)
	if _voice_pool != null:
		_voice_pool.resume_all()


## 获取当前播放位置 (秒)
func get_playback_position() -> float:
	if _ticks_per_second <= 0.0:
		return 0.0
	return _current_tick / _ticks_per_second


## 是否正在播放
func is_playing() -> bool:
	return _is_playing and not _is_paused


## 是否暂停中
func is_paused() -> bool:
	return _is_paused


## 设置混音台通道音量 (0.0-1.0)，独立于 CC#7
func set_channel_volume(channel: int, vol: float) -> void:
	if channel < 0 or channel >= _mixer_volumes.size():
		return
	_mixer_volumes[channel] = clampf(vol, 0.0, 1.0)
	_apply_channel_volume(channel)


## 获取混音台通道音量 (0.0-1.0)
func get_channel_volume(channel: int) -> float:
	if channel < 0 or channel >= _mixer_volumes.size():
		return 0.0
	return _mixer_volumes[channel]


## 跳转到指定位置
func seek(position: float) -> void:
	if _duration_ticks <= 0:
		return
	var target_tick: int = int(position * _ticks_per_second)
	_current_tick = float(clampi(target_tick, 0, _duration_ticks))
	_reset_playback_state()
	_preprocess_events_up_to(int(_current_tick))


## 热更新：从当前 midi_resource 重建事件列表（编辑同步用）
func rebuild_events() -> void:
	if midi_resource == null:
		return
	_reset_playback_state()
	var saved_tick := _current_tick
	_build_sorted_events()
	_current_tick = minf(saved_tick, float(_duration_ticks))
	_preprocess_events_up_to(int(_current_tick))


## 重置播放状态（停止所有声音、清除通道缓存）
func _reset_playback_state() -> void:
	if _voice_pool != null:
		_voice_pool.stop_all()
	_channel_instruments.clear()
	for state in _channel_states:
		state.reset()


## 获取曲目总时长 (秒)
func get_duration() -> float:
	if midi_resource == null:
		return 0.0
	# 直接从导出属性计算，避免 placeholder 实例在编辑器中无法调用脚本方法
	if midi_resource.tracks.is_empty():
		return 0.0
	var tps: float = float(midi_resource.tempo) / 60.0 * float(midi_resource.timebase)
	if tps <= 0.0:
		return 0.0
	var max_end: int = 0
	for track in midi_resource.tracks:
		for note in track.notes:
			var end_t: int = note.start_ticks + note.duration_ticks
			if end_t > max_end:
				max_end = end_t
	return float(max_end) / tps


## 将秒数格式化为 MM:SS 字符串
static func format_time(seconds: float) -> String:
	var mins: int = int(seconds) / 60
	var secs: int = int(seconds) % 60
	return "%d:%02d" % [mins, secs]


## 预处理指定 tick 之前的所有 tempo/program/CC/PitchBend 事件 (不触发 note)
func _preprocess_events_up_to(target_tick: int) -> void:
	_event_index = 0
	while _event_index < _sorted_events.size():
		var event: Dictionary = _sorted_events[_event_index]
		if event["time_ticks"] >= target_tick:
			break
		var event_type: String = event.get("type", "")
		if event_type == "tempo_change":
			_ticks_per_second = event["bpm"] / 60.0 * float(_timebase)
		elif event_type == "program_change":
			_channel_instruments[event["channel"]] = event["preset_index"]
			program_changed.emit(event["channel"], event["preset_index"])
		elif event_type == "control_change":
			cc_received.emit(event["channel"], event["controller"], event["value"])
			_process_cc(event)
		elif event_type == "pitch_bend":
			pitch_bend_received.emit(event["channel"], event["value"])
			_process_pitch_bend(event)
		_event_index += 1


## 获取事件类型排序权重 (同 tick 时决定处理顺序)
func _event_order(type: String) -> int:
	match type:
		"tempo_change": return 0
		"program_change": return 1
		"control_change": return 1
		"pitch_bend": return 1
		"note_off": return 2
		"note_on": return 3
		_: return 4


## 从 MidiResource 构建 MidiData（避免 placeholder 上调用脚本方法）
func _get_midi_data_from_resource(res: MidiResource) -> MidiData:
	var track_list: Array[TrackData] = []
	for track_res in res.tracks:
		var note_list: Array[NoteData] = []
		for note_res in track_res.notes:
			note_list.append(NoteData.new(
				note_res.pitch, note_res.start_ticks,
				note_res.duration_ticks, note_res.velocity
			))
		track_list.append(TrackData.new(
			track_res.name, track_res.channel,
			track_res.instrument, note_list,
			track_res.cc_events.duplicate(true),
			track_res.pitch_bend_events.duplicate(true)
		))
	return MidiData.new(
		res.tempo, track_list, res.timebase,
		res.tempo_events.duplicate(true),
		res.cc_events.duplicate(true),
		res.pitch_bend_events.duplicate(true),
		res.program_events.duplicate(true)
	)


## 构建按时间排序的事件列表 (从所有音轨收集)
func _build_sorted_events() -> void:
	_sorted_events.clear()
	if midi_resource == null:
		return
	var data: MidiData = _get_midi_data_from_resource(midi_resource)
	_timebase = data.timebase
	_ticks_per_second = float(data.tempo) / 60.0 * float(_timebase)
	_channel_instruments.clear()
	_duration_ticks = 0

	for tempo_event in data.tempo_events:
		_sorted_events.append({
			"time_ticks": tempo_event["time_ticks"],
			"type": "tempo_change",
			"bpm": float(tempo_event["bpm"]),
		})

	for pc_event in data.program_events:
		_sorted_events.append({
			"time_ticks": pc_event["time_ticks"],
			"type": "program_change",
			"channel": pc_event["channel"],
			"preset_index": pc_event["preset_index"],
		})

	for track_data in data.tracks:
		for note in track_data.notes:
			var end_tick: int = note.start_ticks + note.duration_ticks
			if end_tick > _duration_ticks:
				_duration_ticks = end_tick
			_sorted_events.append({
				"time_ticks": note.start_ticks,
				"type": "note_on",
				"channel": track_data.channel,
				"pitch": note.pitch,
				"velocity": note.velocity,
				"duration_ticks": note.duration_ticks,
			})
			_sorted_events.append({
				"time_ticks": end_tick,
				"type": "note_off",
				"channel": track_data.channel,
				"pitch": note.pitch,
			})

	for cc_event in data.cc_events:
		_sorted_events.append({
			"time_ticks": cc_event["time_ticks"],
			"type": "control_change",
			"channel": cc_event["channel"],
			"controller": cc_event["controller"],
			"value": cc_event["value"],
		})

	for pb_event in data.pitch_bend_events:
		_sorted_events.append({
			"time_ticks": pb_event["time_ticks"],
			"type": "pitch_bend",
			"channel": pb_event["channel"],
			"value": pb_event["value"],
		})

	_sorted_events.sort_custom(func(a, b):
		if a["time_ticks"] != b["time_ticks"]:
			return a["time_ticks"] < b["time_ticks"]
		return _event_order(a["type"]) < _event_order(b["type"])
	)


func _process(delta: float) -> void:
	if Engine.is_editor_hint() and not _editor_preview:
		return
	if _is_paused or not _is_playing or midi_resource == null:
		return

	# 以 tick 为单位推进播放位置
	_current_tick += float(delta) * _ticks_per_second
	var current_tick: int = int(_current_tick)

	# 处理当前时刻之前的所有事件
	while _event_index < _sorted_events.size():
		var event: Dictionary = _sorted_events[_event_index]
		if event["time_ticks"] > current_tick:
			break
		_process_event(event)
		_event_index += 1

	_progress_frame += 1
	# 发射进度更新信号 (~10Hz 节流，避免每帧信号开销)
	if _progress_frame % PROGRESS_UPDATE_INTERVAL_FRAMES == 0 and _duration_ticks > 0:
		var pos: float = _current_tick / _ticks_per_second
		var dur: float = float(_duration_ticks) / _ticks_per_second
		progress_updated.emit(pos, dur)

	# 检查播放结束: 所有事件已处理 且 当前位置超过曲目时长
	var all_events_done: bool = _event_index >= _sorted_events.size()
	if all_events_done and current_tick >= _duration_ticks:
		if loop and _duration_ticks > 0:
			# 循环重启: 不停止 voice (避免 AudioStreamPlayer.stop() 污染音频状态)
			# 此时所有 note_off 已处理, voice 已在 RELEASE/FINISHED 状态
			_event_index = 0
			_current_tick = 0.0
			_channel_instruments.clear()
			for state in _channel_states:
				state.reset()
			_preprocess_events_up_to(0)
		elif _voice_pool.get_active_voices().size() == 0:
			stop()
			finished.emit()


## 处理单个事件
func _process_event(event: Dictionary) -> void:
	match event["type"]:
		"note_on":
			var channel: int = event["channel"]
			if _debug_channel_filter >= 0 and channel != _debug_channel_filter:
				return
			var key: int = event["pitch"]
			var velocity: int = event["velocity"]
			var preset_index: int = _channel_instruments.get(channel, 0)
			var inst_info: ClefInstrumentInfo = _clef_bank.get_instrument(preset_index, key, velocity, channel)
			if inst_info == null:
				return
			var voice := _voice_pool.start_note(channel, key, velocity, inst_info, release_multiplier)
			if voice != null:
				var ch_state: MidiChannelState = _channel_states[channel]
				voice.set_master_pitch_scale(pitch_scale)
				voice.set_pitch_bend(ch_state.pitch_bend, ch_state.pitch_bend_sensitivity)
				voice.set_modulation(ch_state.modulation, ch_state.modulation_sensitivity)
				# 鼓组通道: ADS 完成后自动释放
				if channel == 9:
					voice._auto_release = true
			if not _debug_note_counts.has(channel):
				_debug_note_counts[channel] = 0
			_debug_note_counts[channel] += 1
			note_triggered.emit(channel, key, velocity)
		"note_off":
			var ch: int = event["channel"]
			if _channel_states[ch]._sustain:
				for voice in _voice_pool.get_active_voices_for_channel(ch):
					if voice.key == event["pitch"] and not voice.is_idle():
						voice._sustained = true
			else:
				_voice_pool.stop_note(ch, event["pitch"])
				note_released.emit(ch, event["pitch"])
		"program_change":
			_channel_instruments[event["channel"]] = event["preset_index"]
			program_changed.emit(event["channel"], event["preset_index"])
		"tempo_change":
			_ticks_per_second = event["bpm"] / 60.0 * float(_timebase)
		"control_change":
			cc_received.emit(event["channel"], event["controller"], event["value"])
			_process_cc(event)
		"pitch_bend":
			pitch_bend_received.emit(event["channel"], event["value"])
			_process_pitch_bend(event)


## 处理 CC 事件
func _process_cc(event: Dictionary) -> void:
	var ch: int = event["channel"]
	var controller: int = event["controller"]
	var value: int = event["value"]
	var state: MidiChannelState = _channel_states[ch]

	match controller:
		1:   # Modulation
			state.modulation = float(value) / 127.0
			for voice in _voice_pool.get_active_voices_for_channel(ch):
				voice.set_modulation(state.modulation)
		6:   # RPN Data Entry MSB
			state._rpn_data_msb = value
			if state.commit_rpn_data():
				for voice in _voice_pool.get_active_voices_for_channel(ch):
					voice.set_pitch_bend(state.pitch_bend, state.pitch_bend_sensitivity)
		7:   # Volume
			state.volume = float(value) / 127.0
			_apply_channel_volume(ch)
		10:  # Pan
			state.pan = float(value) / 127.0
			_apply_channel_pan(ch)
		11:  # Expression
			state.expression = float(value) / 127.0
			_apply_channel_volume(ch)
		38:  # RPN Data Entry LSB
			state._rpn_data_lsb = value
			if state.commit_rpn_data():
				for voice in _voice_pool.get_active_voices_for_channel(ch):
					voice.set_pitch_bend(state.pitch_bend, state.pitch_bend_sensitivity)
		64:  # Sustain Pedal
			if value >= 64:
				state._sustain = true
			else:
				state._sustain = false
				_release_sustained_notes(ch)
		100: # RPN LSB
			state._rpn_lsb = value
		101: # RPN MSB
			state._rpn_msb = value
		120: # All Sound Off
			_voice_pool.force_stop_all()
		123: # All Notes Off (仅目标通道)
			_voice_pool.stop_all(ch)


## 处理 Pitch Bend 事件
func _process_pitch_bend(event: Dictionary) -> void:
	var ch: int = event["channel"]
	var state: MidiChannelState = _channel_states[ch]
	state.set_pitch_bend_raw(event["value"])
	for voice in _voice_pool.get_active_voices_for_channel(ch):
		voice.set_pitch_bend(state.pitch_bend, state.pitch_bend_sensitivity)


## 释放被延音踏板保持的音符
func _release_sustained_notes(ch: int) -> void:
	for voice in _voice_pool.get_active_voices_for_channel(ch):
		if voice._sustained:
			voice._sustained = false
			voice.stop_note()


## 应用通道音量到音频总线（CC#7 volume × 混音台 volume）
func _apply_channel_volume(ch: int) -> void:
	var bus_idx: int = AudioServer.get_bus_index("clef_ch_%d" % ch)
	if bus_idx < 0:
		return
	if ch in _muted_channels:
		AudioServer.set_bus_mute(bus_idx, true)
		return
	AudioServer.set_bus_mute(bus_idx, false)
	var state: MidiChannelState = _channel_states[ch]
	var mixer_vol: float = _mixer_volumes[ch] if ch < _mixer_volumes.size() else 1.0
	var effective: float = state.get_effective_volume() * mixer_vol
	AudioServer.set_bus_volume_db(bus_idx, linear_to_db(maxf(effective, 0.001)))


## 静音/取消静音通道
func set_channel_mute(channel: int, muted: bool) -> void:
	if muted and not (channel in _muted_channels):
		_muted_channels.append(channel)
	elif not muted and channel in _muted_channels:
		_muted_channels.erase(channel)
	_apply_channel_volume(channel)


## 检查通道是否静音
func is_channel_muted(channel: int) -> bool:
	return channel in _muted_channels


## 应用通道声相到音频总线
func _apply_channel_pan(ch: int) -> void:
	var state: MidiChannelState = _channel_states[ch]
	var bus_idx: int = AudioServer.get_bus_index("clef_ch_%d" % ch)
	if bus_idx < 0:
		return
	for i in range(AudioServer.get_bus_effect_count(bus_idx)):
		var effect = AudioServer.get_bus_effect(bus_idx, i)
		if effect is AudioEffectPanner:
			effect.pan = (state.pan * 2.0) - 1.0
			break

