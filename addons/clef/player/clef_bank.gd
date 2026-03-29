## Clef 音色库 — 将 SF2 采样转换为 AudioStreamWAV 并缓存
## 包装 Sf2Bank 的匹配逻辑，添加 AudioStreamWAV 生成层
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


## 获取乐器信息 (带缓存)
## @param preset_index 预设编号 (0-127)
## @param key MIDI 键位 (0-127)
## @param velocity 力度 (0-127)
## @param channel MIDI 通道 (0-15)
## @return 乐器信息, 若未找到返回 null
func get_instrument(preset_index: int, key: int, velocity: int, channel: int) -> ClefInstrumentInfo:
	if _sf2_bank == null:
		return null
	var sample: Sf2SampleInfo = _sf2_bank.get_sample(preset_index, key, velocity, channel)
	if sample == null or sample.sample_data.size() == 0:
		return null

	var is_stereo: bool = sample.linked_sample_data.size() > 0

	# 缓存 key: 基于采样数据特征
	var cache_key: String = "%d_%d_%d_%d_%d_%d" % [
		sample.sample_data.size(), sample.root_key,
		sample.sample_rate, sample.tuning_cents,
		1 if sample.has_loop else 0,
		1 if is_stereo else 0,
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

	asw.data = full_data

	# 循环设置
	if sample.has_loop:
		asw.loop_mode = AudioStreamWAV.LOOP_FORWARD
		asw.loop_begin = sample.loop_start / 2 + HEAD_SILENT_SAMPLES
		asw.loop_end = sample.loop_end / 2 + HEAD_SILENT_SAMPLES
	else:
		asw.loop_mode = AudioStreamWAV.LOOP_DISABLED

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

	_cache[cache_key] = info
	return info
