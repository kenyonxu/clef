## SF2 音色库 — 根据预设编号、键位和力度查找对应采样
## 将解析后的 Sf2Data 转换为可直接用于音频合成的采样信息
## 支持多区域叠加: 同一键位的多个匹配 preset zone 同时返回
class_name Sf2Bank
extends RefCounted

## 未找到采样时的默认值
const DEFAULT_ATTACK: float = 0.001
const DEFAULT_DECAY: float = 0.001
const DEFAULT_SUSTAIN: float = 1.0
const DEFAULT_RELEASE: float = 0.001

var _sf2_data: Sf2Data = null


## 加载 SF2 数据
func load_from_data(sf2_data: Sf2Data) -> void:
	_sf2_data = sf2_data


## 根据预设、键位和力度获取所有匹配采样 (多区域叠加)
## @param preset_index 预设编号 (0-127)
## @param key MIDI 键位 (0-127)
## @param velocity 力度 (0-127)
## @param channel MIDI 通道 (0-15), 用于判断是否为鼓组通道
## @return 匹配的采样信息数组, 若未找到返回空数组
func get_samples(preset_index: int, key: int, velocity: int, channel: int = 0) -> Array[Sf2SampleInfo]:
	var result: Array[Sf2SampleInfo] = []
	if _sf2_data == null:
		return result

	# GM 标准: 通道 9 (MIDI ch10) 为鼓组, 使用 bank 128
	var bank: int = 128 if channel == 9 else 0

	# 1. 查找预设
	var preset: Sf2Data.Sf2Preset = _find_preset(preset_index, bank)
	if preset == null:
		if bank == 128:
			preset = _find_preset(preset_index, 0)
		if preset == null:
			return result

	# 2. 分离全局区域和局部区域
	var _global_zone: Sf2Data.Sf2PresetZone = null
	var local_zones: Array[Sf2Data.Sf2PresetZone] = []

	for zone in preset.zones:
		if zone.is_global:
			_global_zone = zone
		else:
			local_zones.append(zone)

	# 3. 收集所有匹配键位/力力的局部区域 (SF2 规范: 多区域叠加)
	for zone in local_zones:
		if key < zone.key_range.x or key > zone.key_range.y:
			continue
		if velocity < zone.vel_range.x or velocity > zone.vel_range.y:
			continue

		var info := _build_sample_for_zone(zone, _global_zone, key, velocity, channel, bank, preset_index)
		if info != null:
			result.append(info)

	return result


# ---------------------------------------------------------------------------
# 内部: 为单个 preset zone 构建采样信息
# ---------------------------------------------------------------------------

func _build_sample_for_zone(
	zone: Sf2Data.Sf2PresetZone,
	_global_zone: Sf2Data.Sf2PresetZone,
	key: int,
	velocity: int,
	channel: int,
	bank: int,
	preset_index: int,
) -> Sf2SampleInfo:
	var instrument_index: int = zone.instrument_index
	if instrument_index < 0 or instrument_index >= _sf2_data.instruments.size():
		return null

	# 在乐器中查找匹配的采样
	var instrument := _sf2_data.instruments[instrument_index]

	# 收集乐器的全局区域和局部区域
	var inst_global_zone: Sf2Data.Sf2InstrumentZone = null
	var inst_local_zones: Array[Sf2Data.Sf2InstrumentZone] = []

	for izone in instrument.zones:
		if izone.is_global:
			inst_global_zone = izone
		else:
			inst_local_zones.append(izone)

	# 在局部区域中查找匹配的 (最具体优先)
	var best_inst_zone: Sf2Data.Sf2InstrumentZone = null

	for izone in inst_local_zones:
		if key < izone.key_range.x or key > izone.key_range.y:
			continue
		if velocity < izone.vel_range.x or velocity > izone.vel_range.y:
			continue
		if best_inst_zone == null:
			best_inst_zone = izone
			continue
		var key_span: int = izone.key_range.y - izone.key_range.x
		var best_key_span: int = best_inst_zone.key_range.y - best_inst_zone.key_range.x
		if key_span < best_key_span:
			best_inst_zone = izone
		elif key_span == best_key_span:
			var vel_span: int = izone.vel_range.y - izone.vel_range.x
			var best_vel_span: int = best_inst_zone.vel_range.y - best_inst_zone.vel_range.x
			if vel_span < best_vel_span:
				best_inst_zone = izone
			elif vel_span == best_vel_span:
				# 同等具体度: 优先选有循环的 zone (sustain layer),
				# 只有当新 zone 也有循环时才覆盖
				if izone.sample_modes == 1 or izone.sample_modes == 3:
					best_inst_zone = izone

	if best_inst_zone == null:
		return null

	# 构建采样信息
	var sample_index: int = best_inst_zone.sample_index
	if sample_index < 0 or sample_index >= _sf2_data.samples.size():
		return null

	var sample_header := _sf2_data.samples[sample_index]
	var info := Sf2SampleInfo.new()

	# 累积地址偏移: 全局区域 + 局部区域 (字索引单位)
	var total_start_offset: int = 0
	var total_end_offset: int = 0
	var total_loop_start_offset: int = 0
	var total_loop_end_offset: int = 0
	if inst_global_zone != null:
		total_start_offset += inst_global_zone.start_offset
		total_end_offset += inst_global_zone.end_offset
		total_loop_start_offset += inst_global_zone.loop_start_offset
		total_loop_end_offset += inst_global_zone.loop_end_offset
	total_start_offset += best_inst_zone.start_offset
	total_end_offset += best_inst_zone.end_offset
	total_loop_start_offset += best_inst_zone.loop_start_offset
	total_loop_end_offset += best_inst_zone.loop_end_offset

	# 应用偏移后的采样地址 (字索引)
	var actual_start: int = sample_header.start + total_start_offset
	var actual_end: int = sample_header.end + total_end_offset
	var actual_loop_start: int = sample_header.loop_start + total_loop_start_offset
	var actual_loop_end: int = sample_header.loop_end + total_loop_end_offset

	# 采样数据: 字索引 * 2 = 字节偏移
	var byte_start := actual_start * 2
	var byte_end := actual_end * 2 - 1
	if byte_start < 0:
		byte_start = 0
	if byte_end > _sf2_data.sample_data.size():
		byte_end = _sf2_data.sample_data.size()
	if byte_start < byte_end:
		info.sample_data = _sf2_data.sample_data.slice(byte_start, byte_end)
	else:
		info.sample_data = PackedByteArray()

	# 采样率
	info.sample_rate = maxi(sample_header.sample_rate, 1)

	# 根音: 乐器区域覆盖采样头
	if best_inst_zone.root_key >= 0:
		info.root_key = best_inst_zone.root_key
	elif inst_global_zone != null and inst_global_zone.root_key >= 0:
		info.root_key = inst_global_zone.root_key
	else:
		info.root_key = sample_header.original_pitch

	# 音高微调: preset 全局 + preset 局部 + 乐器全局 + 乐器局部 + 采样头
	info.tuning_cents = sample_header.pitch_correction
	if _global_zone != null:
		info.tuning_cents += _global_zone.coarse_tune * 100 + _global_zone.fine_tune
	info.tuning_cents += zone.coarse_tune * 100 + zone.fine_tune
	if inst_global_zone != null:
		info.tuning_cents += inst_global_zone.tuning_cents
	info.tuning_cents += best_inst_zone.tuning_cents

	# ADSR: 乐器局部区域 > 乐器全局区域 > 预设 > 默认值
	info.attack = _resolve_envelope(
		best_inst_zone.attack,
		_resolve_envelope(inst_global_zone.attack if inst_global_zone != null else -1.0, -1.0, -1.0),
		DEFAULT_ATTACK,
	)
	info.hold = _resolve_envelope(
		best_inst_zone.hold,
		_resolve_envelope(inst_global_zone.hold if inst_global_zone != null else -1.0, -1.0, -1.0),
		0.0,
	)
	info.decay = _resolve_envelope(
		best_inst_zone.decay,
		_resolve_envelope(inst_global_zone.decay if inst_global_zone != null else -1.0, -1.0, -1.0),
		DEFAULT_DECAY,
	)
	info.sustain = _resolve_envelope(
		best_inst_zone.sustain,
		_resolve_envelope(inst_global_zone.sustain if inst_global_zone != null else -1.0, -1.0, -1.0),
		DEFAULT_SUSTAIN,
	)
	info.release = _resolve_envelope(
		best_inst_zone.release,
		_resolve_envelope(inst_global_zone.release if inst_global_zone != null else -1.0, -1.0, -1.0),
		DEFAULT_RELEASE,
	)

	# 循环: 绝对位置 → 相对于提取采样数据的偏移 (字节)
	info.loop_start = (actual_loop_start - actual_start) * 2
	info.loop_end = (actual_loop_end - actual_start) * 2

	# 采样模式: 累积全局和局部区域
	var sample_modes: int = best_inst_zone.sample_modes
	if inst_global_zone != null and inst_global_zone.sample_modes != -1:
		if sample_modes == -1:
			sample_modes = inst_global_zone.sample_modes
		else:
			sample_modes |= inst_global_zone.sample_modes

	# 循环判定
	var is_drum: bool = (channel == 9) or (bank == 128)
	var valid_loop: bool = actual_loop_end > actual_loop_start + 64
	if sample_modes == 1 or sample_modes == 3:
		info.has_loop = valid_loop and not is_drum
	elif sample_modes == -1 and (sample_header.sample_type & 0x0E) != 0 and valid_loop and not is_drum:
		info.has_loop = true
	else:
		info.has_loop = false
	info.loop_during_release = (sample_modes & 0x02) != 0

	# 诊断
	var sample_frames: int = info.sample_data.size() / 2
	var sample_duration_ms: float = float(sample_frames) / 44100.0 * 1000.0
	if ProjectSettings.get_setting("clef/debug_verbose", false):
		print("[SF2] preset=%d key=%d ch=%d inst=%d | modes=%d root=%d | hdr=[%d,%d] actual=[%d,%d] loop=[%d,%d] | data=%d bytes %d frames %.1fms | has_loop=%s" % [
		preset_index, key, channel, instrument_index, sample_modes, info.root_key,
		sample_header.start, sample_header.end,
		actual_start, actual_end,
		actual_loop_start, actual_loop_end,
		info.sample_data.size(), sample_frames, sample_duration_ms,
		"YES" if info.has_loop else "NO"])

	# 滤波器
	info.filter_fc = _resolve_envelope(
		best_inst_zone.filter_fc,
		inst_global_zone.filter_fc if inst_global_zone != null else -1.0,
		-1.0,
	)
	info.filter_q = _resolve_envelope(
		best_inst_zone.filter_q,
		inst_global_zone.filter_q if inst_global_zone != null else -1.0,
		-1.0,
	)
	var local_mod_env: int = best_inst_zone.mod_env_to_filter_fc
	var global_mod_env: int = inst_global_zone.mod_env_to_filter_fc if inst_global_zone != null else 0
	info.mod_env_to_filter_fc = local_mod_env if local_mod_env != 0 else global_mod_env

	# 立体声检测
	var st: int = sample_header.sample_type
	if st == 2 or st == 4 or st == 8 or st == 0x8002 or st == 0x8004 or st == 0x8008:
		info.sample_type = st
		var linked_idx: int = sample_header.link_index
		if linked_idx >= 0 and linked_idx < _sf2_data.samples.size() and linked_idx != sample_index:
			var linked_header: Sf2Data.Sf2SampleHeader = _sf2_data.samples[linked_idx]
			var linked_byte_start: int = linked_header.start * 2
			var linked_byte_end: int = linked_header.end * 2 - 1
			if linked_byte_start < 0:
				linked_byte_start = 0
			if linked_byte_end > _sf2_data.sample_data.size():
				linked_byte_end = _sf2_data.sample_data.size()
			if linked_byte_start < linked_byte_end:
				info.linked_sample_data = _sf2_data.sample_data.slice(linked_byte_start, linked_byte_end)
			info.link_index = linked_idx

	return info


# ---------------------------------------------------------------------------
# 内部: 查找预设
# ---------------------------------------------------------------------------

func _find_preset(preset_index: int, bank: int = 0) -> Sf2Data.Sf2Preset:
	for preset in _sf2_data.presets:
		if preset.preset_index == preset_index and preset.bank == bank:
			return preset
	return null


# ---------------------------------------------------------------------------
# 内部: 解析包络值 (层叠覆盖, -1.0 表示未设置)
# ---------------------------------------------------------------------------

func _resolve_envelope(value: float, fallback: float, default_val: float) -> float:
	if value >= 0.0:
		return value
	if fallback >= 0.0:
		return fallback
	return default_val
