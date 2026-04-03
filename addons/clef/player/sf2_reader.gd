## SF2 文件二进制解析器
## 读取 SoundFont 2 (.sf2) 文件并转换为 Sf2Data 结构
class_name Sf2Reader
extends RefCounted

## 解析结果
class Sf2ReadResult extends RefCounted:
	## 是否成功
	var ok: bool = false
	## 解析后的数据 (仅在 ok=true 时有效)
	var data: Sf2Data = null
	## 错误信息 (仅在 ok=false 时有效)
	var error_message: String = ""

# ---------------------------------------------------------------------------
# SF2 Generator 类型 ID (遵循 SF2 规范)
# ---------------------------------------------------------------------------
const GEN_START_ADDRESS_OFFSET: int = 0
const GEN_END_ADDRESS_OFFSET: int = 1
const GEN_STARTLOOP_ADDRESS_OFFSET: int = 2
const GEN_ENDLOOP_ADDRESS_OFFSET: int = 3
const GEN_START_ADDRESS_COARSE_OFFSET: int = 4
const GEN_MOD_LFO_TO_PITCH: int = 5
const GEN_VIB_LFO_TO_PITCH: int = 6
const GEN_MOD_ENV_TO_PITCH: int = 7
const GEN_INITIAL_FILTER_FC: int = 8
const GEN_INITIAL_FILTER_Q: int = 9
const GEN_MOD_LFO_TO_FILTER_FC: int = 10
const GEN_MOD_ENV_TO_FILTER_FC: int = 11
const GEN_END_ADDRESS_COARSE_OFFSET: int = 12
const GEN_MOD_LFO_TO_VOLUME: int = 13
const GEN_CHORUS_EFFECTS_SEND: int = 15
const GEN_REVERB_EFFECTS_SEND: int = 16
const GEN_PAN: int = 17
const GEN_DELAY_MOD_LFO: int = 21
const GEN_FREQ_MOD_LFO: int = 22
const GEN_DELAY_VIB_LFO: int = 23
const GEN_FREQ_VIB_LFO: int = 24
const GEN_DELAY_MOD_ENV: int = 25
const GEN_ATTACK_MOD_ENV: int = 26
const GEN_HOLD_MOD_ENV: int = 27
const GEN_DECAY_MOD_ENV: int = 28
const GEN_SUSTAIN_MOD_ENV: int = 29
const GEN_RELEASE_MOD_ENV: int = 30
const GEN_KEYNUM_TO_MOD_ENV_HOLD: int = 31
const GEN_KEYNUM_TO_MOD_ENV_DECAY: int = 32
const GEN_DELAY_VOL_ENV: int = 33
const GEN_ATTACK_VOL_ENV: int = 34
const GEN_HOLD_VOL_ENV: int = 35
const GEN_DECAY_VOL_ENV: int = 36
const GEN_SUSTAIN_VOL_ENV: int = 37
const GEN_RELEASE_VOL_ENV: int = 38
const GEN_KEYNUM_TO_VOL_ENV_HOLD: int = 39
const GEN_KEYNUM_TO_VOL_ENV_DECAY: int = 40
const GEN_INSTRUMENT: int = 41
const GEN_KEY_RANGE: int = 43
const GEN_VEL_RANGE: int = 44
const GEN_KEYNUM: int = 46
const GEN_VELOCITY: int = 47
const GEN_INITIAL_ATTENUATION: int = 48
const GEN_STARTLOOP_ADDRESS_COARSE_OFFSET: int = 45
const GEN_ENDLOOP_ADDRESS_COARSE_OFFSET: int = 50
const GEN_COARSE_TUNE: int = 51
const GEN_FINE_TUNE: int = 52
const GEN_SAMPLE_ID: int = 53
const GEN_SAMPLE_MODES: int = 54
const GEN_SCALE_TUNING: int = 56
const GEN_EXCLUSIVE_CLASS: int = 57
const GEN_OVERRIDING_ROOT_KEY: int = 58
const GEN_END_OF_GENERATORS: int = 60

# ---------------------------------------------------------------------------
# SF2 子块 ID
# ---------------------------------------------------------------------------
const CHUNK_INFO: String = "INFO"
const CHUNK_SDTA: String = "sdta"
const CHUNK_PDTA: String = "pdta"
const SUBCHUNK_SMPL: String = "smpl"
const SUBCHUNK_PHDR: String = "phdr"
const SUBCHUNK_Pbag: String = "pbag"
const SUBCHUNK_PMOD: String = "pmod"
const SUBCHUNK_PGEN: String = "pgen"
const SUBCHUNK_INST: String = "inst"
const SUBCHUNK_IBAG: String = "ibag"
const SUBCHUNK_IMOD: String = "imod"
const SUBCHUNK_IGEN: String = "igen"
const SUBCHUNK_SHDR: String = "shdr"


## 读取 SF2 文件并解析
## @param path SF2 文件路径
## @return 解析结果
static func read_file(path: String) -> Sf2ReadResult:
	var result := Sf2ReadResult.new()
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		result.error_message = "无法打开文件: %s (错误: %d)" % [path, FileAccess.get_open_error()]
		return result

	var file_size := file.get_length()
	var raw_data: PackedByteArray = file.get_buffer(file_size)
	if raw_data.size() < file_size:
		result.error_message = "读取文件不完整: 期望 %d 字节, 实际 %d 字节" % [file_size, raw_data.size()]
		return result

	var reader := Sf2Reader.new()
	var parse_result := reader._parse(raw_data)
	if parse_result == null:
		result.error_message = "SF2 文件格式无效: %s" % path
		return result

	result.ok = true
	result.data = parse_result
	return result


# ---------------------------------------------------------------------------
# 内部: 完整解析流程
# ---------------------------------------------------------------------------

func _parse(raw_data: PackedByteArray) -> Sf2Data:
	var stream := StreamPeerBuffer.new()
	stream.set_data_array(raw_data)
	stream.big_endian = false  # RIFF 格式使用小端序

	# 验证 RIFF/sfbk 头
	var riff_id := stream.get_string(4)
	if riff_id != "RIFF":
		return null
	var _file_size := stream.get_u32()  # 文件总大小 - 8
	var form_type := stream.get_string(4)
	if form_type != "sfbk":
		return null

	var sf2_data := Sf2Data.new()

	# 读取三个顶级块 (LIST INFO, LIST sdta, LIST pdta)
	while stream.get_available_bytes() > 0:
		var chunk_id := stream.get_string(4)
		var chunk_size := stream.get_u32()
		if stream.get_available_bytes() < chunk_size:
			break

		var chunk_data: PackedByteArray = stream.get_partial_data(chunk_size)[1]
		var chunk_stream := _make_stream(chunk_data)

		match chunk_id:
			"LIST":
				var list_type := chunk_stream.get_string(4)
				match list_type:
					CHUNK_INFO:
						_parse_info(chunk_stream, sf2_data)
					CHUNK_SDTA:
						_parse_sdta(chunk_stream, sf2_data)
					CHUNK_PDTA:
						_parse_pdta(chunk_stream, sf2_data)
			_:
				pass  # 跳过未知块

	return sf2_data


# ---------------------------------------------------------------------------
# 内部: 创建 StreamPeerBuffer
# ---------------------------------------------------------------------------

func _make_stream(data: PackedByteArray) -> StreamPeerBuffer:
	var s := StreamPeerBuffer.new()
	s.set_data_array(data)
	s.big_endian = false
	return s


# ---------------------------------------------------------------------------
# 内部: 读取子块头
# ---------------------------------------------------------------------------

func _read_subchunk(stream: StreamPeerBuffer) -> Dictionary:
	if stream.get_available_bytes() < 8:
		return {"id": "", "size": 0, "stream": null}
	var id := stream.get_string(4)
	var size := stream.get_u32()
	var data: PackedByteArray
	if size > 0 and stream.get_available_bytes() >= size:
		data = stream.get_partial_data(size)[1]
	else:
		data = PackedByteArray()
	return {"id": id, "size": size, "stream": _make_stream(data)}


# ---------------------------------------------------------------------------
# INFO 块解析
# ---------------------------------------------------------------------------

func _parse_info(list_stream: StreamPeerBuffer, sf2_data: Sf2Data) -> void:
	while list_stream.get_available_bytes() >= 8:
		var sub := _read_subchunk(list_stream)
		if sub["id"] == "":
			break

		var sub_stream: StreamPeerBuffer = sub["stream"]
		var size: int = sub["size"]

		match sub["id"]:
			"ifil":
				# 版本: 2 x uint16
				if size >= 4:
					var major := sub_stream.get_u16()
					var minor := sub_stream.get_u16()
					sf2_data.version = "%d.%02d" % [major, minor]
			"isng":
				# 目标音色引擎
				sf2_data.sound_engine = sub_stream.get_string(size).strip_edges()
			"inam":
				# 音色库名称
				sf2_data.bank_name = sub_stream.get_string(size).strip_edges()
			"isdt":
				# 采样率可能存储在这里或其他位置，我们优先从 SHDR 获取
				if size >= 4:
					var _sample_rate := sub_stream.get_u32()
			_:
				pass  # 跳过其他 INFO 子块 (irom, iver, icrd, ieng, etc.)


# ---------------------------------------------------------------------------
# sdta 块解析
# ---------------------------------------------------------------------------

func _parse_sdta(list_stream: StreamPeerBuffer, sf2_data: Sf2Data) -> void:
	while list_stream.get_available_bytes() >= 8:
		var sub := _read_subchunk(list_stream)
		if sub["id"] == "":
			break

		if sub["id"] == SUBCHUNK_SMPL:
			sf2_data.sample_data = sub["stream"].get_partial_data(sub["size"])[1]
			# 采样率将从 SHDR 中获取


# ---------------------------------------------------------------------------
# pdta 块解析
# ---------------------------------------------------------------------------

func _parse_pdta(list_stream: StreamPeerBuffer, sf2_data: Sf2Data) -> void:
	# 1. 读取所有 9 个子块的原始数据
	var phdr_data: PackedByteArray = []
	var pbag_data: PackedByteArray = []
	var _pmod_data: PackedByteArray = []
	var pgen_data: PackedByteArray = []
	var inst_data: PackedByteArray = []
	var ibag_data: PackedByteArray = []
	var _imod_data: PackedByteArray = []
	var igen_data: PackedByteArray = []
	var shdr_data: PackedByteArray = []

	var expected_subchunks := [
		SUBCHUNK_PHDR, SUBCHUNK_Pbag, SUBCHUNK_PMOD, SUBCHUNK_PGEN,
		SUBCHUNK_INST, SUBCHUNK_IBAG, SUBCHUNK_IMOD, SUBCHUNK_IGEN,
		SUBCHUNK_SHDR,
	]

	var subchunk_idx := 0
	while list_stream.get_available_bytes() >= 8 and subchunk_idx < expected_subchunks.size():
		var sub := _read_subchunk(list_stream)
		if sub["id"] == "":
			break

		var raw: PackedByteArray = sub["stream"].get_partial_data(sub["size"])[1]

		match sub["id"]:
			SUBCHUNK_PHDR:
				phdr_data = raw
			SUBCHUNK_Pbag:
				pbag_data = raw
			SUBCHUNK_PMOD:
				_pmod_data = raw
			SUBCHUNK_PGEN:
				pgen_data = raw
			SUBCHUNK_INST:
				inst_data = raw
			SUBCHUNK_IBAG:
				ibag_data = raw
			SUBCHUNK_IMOD:
				_imod_data = raw
			SUBCHUNK_IGEN:
				igen_data = raw
			SUBCHUNK_SHDR:
				shdr_data = raw
			_:
				pass

		subchunk_idx += 1

	# 2. 创建各子块的 StreamPeerBuffer
	var phdr_stream := _make_stream(phdr_data)
	var pbag_stream := _make_stream(pbag_data)
	var pgen_stream := _make_stream(pgen_data)
	var inst_stream := _make_stream(inst_data)
	var ibag_stream := _make_stream(ibag_data)
	var igen_stream := _make_stream(igen_data)
	var shdr_stream := _make_stream(shdr_data)

	# 3. 解析 Sample Headers (先解析，后面要用)
	_parse_shdr(shdr_stream, sf2_data)

	# 4. 解析 Preset Headers 和 Bag/Gen
	_parse_presets(phdr_stream, pbag_stream, pgen_stream, sf2_data)

	# 5. 解析 Instruments 和 Bag/Gen
	_parse_instruments(inst_stream, ibag_stream, igen_stream, sf2_data)


# ---------------------------------------------------------------------------
# Sample Header 解析 (46 bytes each)
# ---------------------------------------------------------------------------

func _parse_shdr(stream: StreamPeerBuffer, sf2_data: Sf2Data) -> void:
	var record_size := 46
	var count := stream.get_available_bytes() / record_size

	# 最后一条是终止记录，跳过
	for i in range(max(0, count - 1)):
		var header := Sf2Data.Sf2SampleHeader.new()
		header.name = stream.get_string(20).strip_edges()
		header.start = stream.get_u32()
		header.end = stream.get_u32()
		header.loop_start = stream.get_u32()
		header.loop_end = stream.get_u32()
		header.sample_rate = stream.get_u32()
		header.original_pitch = stream.get_u8()
		header.pitch_correction = stream.get_8()
		header.sample_type = stream.get_u16()
		header.link_index = stream.get_u16()
		sf2_data.samples.append(header)

	# 从第一个采样的采样率作为全局采样率
	if sf2_data.samples.size() > 0:
		sf2_data.sample_rate = sf2_data.samples[0].sample_rate


# ---------------------------------------------------------------------------
# Preset 解析
# ---------------------------------------------------------------------------

func _parse_presets(
	phdr_stream: StreamPeerBuffer,
	pbag_stream: StreamPeerBuffer,
	pgen_stream: StreamPeerBuffer,
	sf2_data: Sf2Data,
) -> void:
	var record_size := 38
	var phdr_count := phdr_stream.get_available_bytes() / record_size

	# 预读所有 PHDR 记录: 提取 bag_index 和元数据
	var preset_headers: Array[Dictionary] = []
	for _j in range(phdr_count):
		preset_headers.append({
			"name": phdr_stream.get_string(20).strip_edges(),
			"preset": phdr_stream.get_u16(),
			"bank": phdr_stream.get_u16(),
			"bag_index": phdr_stream.get_u16(),
		})
		phdr_stream.get_u32()  # library
		phdr_stream.get_u32()  # genre
		phdr_stream.get_u32()  # morphology

	# 读取所有 bag 和 generator 记录
	var bags := _read_bags(pbag_stream)
	var gens := _read_gens(pgen_stream)

	# 最后一条 PHDR 是终止记录，跳过
	for i in range(max(0, phdr_count - 1)):
		var hdr: Dictionary = preset_headers[i]
		var preset := Sf2Data.Sf2Preset.new()
		preset.name = hdr["name"]
		preset.preset_index = hdr["preset"]
		preset.bank = hdr["bank"]

		var start_bag: int = hdr["bag_index"]
		var end_bag: int
		if i + 1 < preset_headers.size():
			end_bag = preset_headers[i + 1]["bag_index"]
		else:
			end_bag = bags.size()

		# 解析每个 bag (zone)
		for bag_i in range(start_bag, end_bag):
			if bag_i >= bags.size():
				break

			var zone := Sf2Data.Sf2PresetZone.new()
			var gen_start: int = bags[bag_i]["gen_ndx"]
			var gen_end: int
			if bag_i + 1 < bags.size():
				gen_end = bags[bag_i + 1]["gen_ndx"]
			else:
				gen_end = gens.size()

			var has_instrument := false
			var gen_svalue: int = 0

			for gen_i in range(gen_start, gen_end):
				if gen_i >= gens.size():
					break
				var gen_type: int = gens[gen_i]["type_id"]
				var gen_value: int = gens[gen_i]["value"]
				gen_svalue = gens[gen_i]["signed_value"]

				if gen_type == GEN_END_OF_GENERATORS:
					break

				match gen_type:
					GEN_KEY_RANGE:
						var lo_byte: int = gen_value & 0xFF
						var hi_byte: int = (gen_value >> 8) & 0xFF
						zone.key_range = Vector2i(lo_byte, hi_byte)
					GEN_VEL_RANGE:
						var lo_byte: int = gen_value & 0xFF
						var hi_byte: int = (gen_value >> 8) & 0xFF
						zone.vel_range = Vector2i(lo_byte, hi_byte)
					GEN_INSTRUMENT:
						has_instrument = true
						zone.instrument_index = gen_value
					GEN_COARSE_TUNE:
						zone.coarse_tune = gen_svalue
					GEN_FINE_TUNE:
						zone.fine_tune = gen_svalue

			# 全局区域: 没有 instrument 链接的区域
			zone.is_global = not has_instrument
			preset.zones.append(zone)

		sf2_data.presets.append(preset)


# ---------------------------------------------------------------------------
# Instrument 解析
# ---------------------------------------------------------------------------

func _parse_instruments(
	inst_stream: StreamPeerBuffer,
	ibag_stream: StreamPeerBuffer,
	igen_stream: StreamPeerBuffer,
	sf2_data: Sf2Data,
) -> void:
	var record_size := 22
	var inst_count := inst_stream.get_available_bytes() / record_size

	var bags := _read_bags(ibag_stream)
	var gens := _read_gens(igen_stream)

	# 预读所有 INST 记录: 提取 name 和 bag_index
	var inst_headers: Array[Dictionary] = []
	for _j in range(inst_count):
		inst_headers.append({
			"name": inst_stream.get_string(20).strip_edges(),
			"bag_index": inst_stream.get_u16(),
		})

	for i in range(max(0, inst_count - 1)):
		var hdr: Dictionary = inst_headers[i]
		var instrument := Sf2Data.Sf2Instrument.new()
		instrument.name = hdr["name"]

		var start_bag: int = hdr["bag_index"]
		var end_bag: int
		if i + 1 < inst_headers.size():
			end_bag = inst_headers[i + 1]["bag_index"]
		else:
			end_bag = bags.size()

		for bag_i in range(start_bag, end_bag):
			if bag_i >= bags.size():
				break

			var zone := Sf2Data.Sf2InstrumentZone.new()
			var gen_start: int = bags[bag_i]["gen_ndx"]
			var gen_end: int
			if bag_i + 1 < bags.size():
				gen_end = bags[bag_i + 1]["gen_ndx"]
			else:
				gen_end = gens.size()

			var has_sample := false

			for gen_i in range(gen_start, gen_end):
				if gen_i >= gens.size():
					break
				var gen_type: int = gens[gen_i]["type_id"]
				var gen_value: int = gens[gen_i]["value"]
				var gen_svalue: int = gens[gen_i]["signed_value"]

				if gen_type == GEN_END_OF_GENERATORS:
					break

				match gen_type:
					GEN_KEY_RANGE:
						var lo_byte: int = gen_value & 0xFF
						var hi_byte: int = (gen_value >> 8) & 0xFF
						zone.key_range = Vector2i(lo_byte, hi_byte)
					GEN_VEL_RANGE:
						var lo_byte: int = gen_value & 0xFF
						var hi_byte: int = (gen_value >> 8) & 0xFF
						zone.vel_range = Vector2i(lo_byte, hi_byte)
					GEN_SAMPLE_ID:
						has_sample = true
						zone.sample_index = gen_value
					GEN_OVERRIDING_ROOT_KEY:
						zone.root_key = gen_value
					GEN_FINE_TUNE:
						zone.tuning_cents += gen_svalue
					GEN_COARSE_TUNE:
						zone.tuning_cents += gen_svalue * 100
					GEN_ATTACK_VOL_ENV:
						zone.attack = _timecent_to_seconds(gen_svalue)
					GEN_HOLD_VOL_ENV:
						zone.hold = _timecent_to_seconds(gen_svalue)
					GEN_DECAY_VOL_ENV:
						zone.decay = _timecent_to_seconds(gen_svalue)
					GEN_SUSTAIN_VOL_ENV:
						zone.sustain = _centibels_to_linear(gen_svalue)
					GEN_RELEASE_VOL_ENV:
						zone.release = _timecent_to_seconds(gen_svalue)
					GEN_START_ADDRESS_OFFSET:
						zone.start_offset += gen_svalue
					GEN_START_ADDRESS_COARSE_OFFSET:
						zone.start_offset += gen_svalue * 32768
					GEN_END_ADDRESS_OFFSET:
						zone.end_offset += gen_svalue
					GEN_END_ADDRESS_COARSE_OFFSET:
						zone.end_offset += gen_svalue * 32768
					GEN_STARTLOOP_ADDRESS_OFFSET:
						zone.loop_start_offset += gen_svalue
					GEN_STARTLOOP_ADDRESS_COARSE_OFFSET:
						zone.loop_start_offset += gen_svalue * 32768
					GEN_ENDLOOP_ADDRESS_OFFSET:
						zone.loop_end_offset += gen_svalue
					GEN_ENDLOOP_ADDRESS_COARSE_OFFSET:
						zone.loop_end_offset += gen_svalue * 32768
					GEN_SAMPLE_MODES:
						zone.sample_modes = gen_value & 0x03
					GEN_INITIAL_FILTER_FC:
						if gen_svalue != -32768:
							zone.filter_fc = 8.176 * pow(2.0, float(gen_svalue) / 1200.0)
					GEN_INITIAL_FILTER_Q:
						if gen_svalue != -32768:
							zone.filter_q = clampf(float(gen_svalue) / 2400.0, 0.0, 1.0)
					GEN_MOD_LFO_TO_FILTER_FC:
						zone.mod_lfo_to_filter_fc = gen_svalue
					GEN_MOD_ENV_TO_FILTER_FC:
						zone.mod_env_to_filter_fc = gen_svalue

			zone.is_global = not has_sample
			instrument.zones.append(zone)

		sf2_data.instruments.append(instrument)


# ---------------------------------------------------------------------------
# 辅助: 读取 bag 数组 (4 bytes each: gen_ndx + mod_ndx)
# ---------------------------------------------------------------------------

func _read_bags(stream: StreamPeerBuffer) -> Array[Dictionary]:
	var bags: Array[Dictionary] = []
	var count := stream.get_available_bytes() / 4
	for _i in range(count):
		bags.append({
			"gen_ndx": stream.get_u16(),
			"mod_ndx": stream.get_u16(),
		})
	return bags


# ---------------------------------------------------------------------------
# 辅助: 读取 generator 数组 (4 bytes each: type + amount)
# ---------------------------------------------------------------------------

func _read_gens(stream: StreamPeerBuffer) -> Array[Dictionary]:
	var gens: Array[Dictionary] = []
	var count := stream.get_available_bytes() / 4
	for _i in range(count):
		var type_id := stream.get_u16()
		var raw_amount := stream.get_u16()
		# 将 uint16 转换为 int16 (有符号)
		var signed_value: int = raw_amount if raw_amount <= 32767 else (raw_amount - 65536)
		gens.append({
			"type_id": type_id,
			"value": raw_amount,
			"signed_value": signed_value,
		})
	return gens


# ---------------------------------------------------------------------------
# 辅助: timecent 转换为秒
# 0x7FFF (32767) 或 -32768 表示 "不改变" -> 返回 -1.0
# ---------------------------------------------------------------------------

func _timecent_to_seconds(timecent: int) -> float:
	if timecent == 32767 or timecent == -32768:
		return -1.0
	return pow(2.0, float(timecent) / 1200.0)


# ---------------------------------------------------------------------------
# 辅助: centibels (0.1 dB) 转换为线性 0.0-1.0
# SF2 centibels 范围 0-1440，对应 0 到 -144 dB 衰减
# dB = -centibels / 10.0, linear = 10^(dB/20) = 10^(-centibels/200)
# 特殊值处理
# ---------------------------------------------------------------------------

func _centibels_to_linear(centibels: int) -> float:
	if centibels == 32767 or centibels == -32768:
		return -1.0
	return pow(10.0, -float(centibels) / 200.0)
