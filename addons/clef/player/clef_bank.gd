## Clef 音色库 — 将 SF2 采样转换为 AudioStreamWAV 并缓存
## 包装 Sf2Bank 的匹配逻辑，添加 AudioStreamWAV 生成层
## 支持多区域叠加: 同一键位的多个匹配采样同时返回
class_name ClefBank extends RefCounted

## 前置静音采样数 (44100/8 = 5512, 约 125ms, 防止播放咔嗒声)
const HEAD_SILENT_SAMPLES: int = 5512

var _sf2_bank: Sf2Bank = null
var _cache: Dictionary = {}
## 每个采样前置的静音数据 (PackedByteArray, 5512 * 2 bytes)
var _head_silent: PackedByteArray = []
## 立体声静音数据 (PackedByteArray, 5512 * 4 bytes = L0R0L1R1...)
var _head_silent_stereo: PackedByteArray = []


## 加载 SF2 数据
func load_from_sf2(sf2_data: Sf2Data) -> void:
	_cache.clear()
	_head_silent = PackedByteArray()
	_head_silent.resize(HEAD_SILENT_SAMPLES * 2)
	_head_silent.fill(0)
	_head_silent_stereo = PackedByteArray()
	_head_silent_stereo.resize(HEAD_SILENT_SAMPLES * 4)
	_head_silent_stereo.fill(0)
	if sf2_data == null:
		_sf2_bank = null
		return
	_sf2_bank = Sf2Bank.new()
	_sf2_bank.load_from_data(sf2_data)


## 获取所有匹配的乐器信息 (多区域叠加, 带缓存)
## @param preset_index 预设编号 (0-127)
## @param key MIDI 键位 (0-127)
## @param velocity 力度 (0-127)
## @param channel MIDI 通道 (0-15)
## @return 乐器信息数组, 若未找到返回空数组
func get_instruments(preset_index: int, key: int, velocity: int, channel: int) -> Array[ClefInstrumentInfo]:
	var result: Array[ClefInstrumentInfo] = []
	if _sf2_bank == null:
		return result

	var samples: Array[Sf2SampleInfo] = _sf2_bank.get_samples(preset_index, key, velocity, channel)
	for sample in samples:
		if sample.sample_data.size() == 0:
			continue

		var info := _build_instrument_info(sample, channel)
		if info != null:
			result.append(info)

	return result


## 为单个采样构建 ClefInstrumentInfo (带缓存)
func _build_instrument_info(sample: Sf2SampleInfo, channel: int) -> ClefInstrumentInfo:
	var is_stereo: bool = sample.linked_sample_data.size() > 0

	# 缓存 key: 基于采样数据特征
	var cache_key: String = "%d_%d_%d_%d_%d_%d_%d_%d" % [
		sample.sample_data.size(), sample.root_key,
		sample.sample_rate, sample.tuning_cents,
		1 if sample.has_loop else 0,
		1 if is_stereo else 0,
		sample.filter_fc if sample.filter_fc >= 0 else -1,
		sample.filter_q if sample.filter_q >= 0 else -1,
	]
	if _cache.has(cache_key):
		return _cache[cache_key]

	var info := ClefInstrumentInfo.new()
	info.is_stereo = is_stereo

	# 生成 AudioStreamWAV
	var asw := AudioStreamWAV.new()
	asw.format = AudioStreamWAV.FORMAT_16_BITS
	asw.mix_rate = 44100
	asw.stereo = is_stereo

	var full_data: PackedByteArray

	if is_stereo:
		# 交错 L/R PCM 数据: L0_lo L0_hi R0_lo R0_hi L1_lo L1_hi R1_lo R1_hi ...
		var min_len: int = mini(sample.sample_data.size(), sample.linked_sample_data.size())
		min_len -= min_len % 2  # 对齐到 2 字节 (每个采样 2 字节)
		var interleaved := PackedByteArray()
		interleaved.resize(min_len * 2)
		for i in range(0, min_len, 2):
			var frame_offset: int = i * 2  # stereo: 每帧 4 字节
			interleaved[frame_offset] = sample.sample_data[i]
			interleaved[frame_offset + 1] = sample.sample_data[i + 1]
			interleaved[frame_offset + 2] = sample.linked_sample_data[i]
			interleaved[frame_offset + 3] = sample.linked_sample_data[i + 1]
		full_data = _head_silent_stereo + interleaved
	else:
		full_data = _head_silent + sample.sample_data

	# 离线 LPF: 对 PCM 预处理, 绕开 Godot AudioEffectFilter 的已知 bug
	if sample.filter_fc >= 0 and sample.filter_fc < 20000.0:
		var q: float = sample.filter_q if sample.filter_q >= 0.0 else 0.0
		full_data = AudioFilter.apply_biquad_lpf(full_data, sample.filter_fc, q, 44100, is_stereo)

	asw.data = full_data

	# 循环设置
	if sample.has_loop:
		asw.loop_mode = AudioStreamWAV.LOOP_FORWARD
		asw.loop_begin = sample.loop_start / 2 + HEAD_SILENT_SAMPLES
		asw.loop_end = sample.loop_end / 2 + HEAD_SILENT_SAMPLES
	else:
		asw.loop_mode = AudioStreamWAV.LOOP_DISABLED

	# DIAG: AudioStreamWAV loop config
	if ProjectSettings.get_setting("clef/debug_verbose", false):
		print("[BANK] has_loop=%s loop_mode=%d loop_begin=%d loop_end=%d data=%d stereo=%s" % ["YES" if sample.has_loop else "NO", asw.loop_mode, asw.loop_begin, asw.loop_end, asw.data.size(), "YES" if is_stereo else "NO"])
	info.stream = asw
	info.root_key = sample.root_key

	# base_pitch: 采样率补偿 + 音高微调 (不含 key 偏移)
	info.base_pitch = float(sample.tuning_cents) / 1200.0
	if sample.sample_rate != 44100:
		info.base_pitch += log(float(sample.sample_rate) / 44100.0) / log(2.0)

	# ADSR 参数
	info.attack = sample.attack
	info.hold = sample.hold
	info.decay = sample.decay
	info.sustain_db = linear_to_db(sample.sustain)
	info.release = sample.release
	info.filter_fc = sample.filter_fc
	info.filter_q = sample.filter_q
	info.mod_env_to_filter_fc = sample.mod_env_to_filter_fc

	_cache[cache_key] = info
	return info
