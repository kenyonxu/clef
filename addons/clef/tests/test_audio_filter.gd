extends SceneTree
## 用法: godot --headless --script addons/clef/tests/test_audio_filter.gd

const AudioFilter = preload("res://addons/clef/player/audio_filter.gd")

func _init() -> void:
	print("\n=== AudioFilter Test ===")
	var pass_count: int = 0
	var fail_count: int = 0

	# --- Test 1: 系数计算 ---
	print("--- Test 1: Biquad LPF 系数计算 ---")
	var c = AudioFilter.biquad_lpf_coefficients(1000.0, 0.0, 44100)
	if c.b0 != 0.0 and c.b1 != 0.0 and c.a1 != 0.0:
		print("PASS: 系数非零")
		pass_count += 1
	else:
		print("FAIL: 系数为零")
		fail_count += 1

	# 对称性: b0 == b2 (Butterworth 特性)
	if absf(c.b0 - c.b2) < 0.0001:
		print("PASS: b0 == b2 (Butterworth 对称性)")
		pass_count += 1
	else:
		print("FAIL: b0(%f) != b2(%f)" % [c.b0, c.b2])
		fail_count += 1

	# a1 应为负值, a2 应为正值 (标准 Butterworth biquad: a1 = -2*cos(w0)/a0, a2 = (1-alpha)/a0)
	if c.a1 < 0.0 and c.a2 > 0.0:
		print("PASS: a1<0, a2>0 (标准 Butterworth 符号)")
		pass_count += 1
	else:
		print("FAIL: a1=%f, a2=%f" % [c.a1, c.a2])
		fail_count += 1

	# --- Test 2: 低截止频率应衰减高频 ---
	print("\n--- Test 2: 低截止频率衰减高频 ---")
	var sample_rate := 44100
	var duration := 0.05  # 50ms
	var frame_count := int(sample_rate * duration)

	# 生成 10kHz 正弦波
	var input_pcm := PackedByteArray()
	input_pcm.resize(frame_count * 2)
	for i in range(frame_count):
		var val: float = sin(2.0 * PI * 10000.0 * i / sample_rate)
		var s: int = int(val * 32767.0)
		if s < 0:
			s += 65536
		input_pcm[i * 2] = s & 0xFF
		input_pcm[i * 2 + 1] = (s >> 8) & 0xFF

	# 用 500Hz 截止频率滤波 (应大幅衰减 10kHz)
	var filtered := AudioFilter.apply_biquad_lpf(input_pcm, 500.0, 0.0, sample_rate, false)

	# 计算 RMS
	var input_rms := _calc_rms(input_pcm, frame_count)
	var filtered_rms := _calc_rms(filtered, frame_count)

	if filtered_rms < input_rms * 0.1:
		print("PASS: 500Hz LPF 衰减 10kHz (input_rms=%.2f, filtered_rms=%.2f)" % [input_rms, filtered_rms])
		pass_count += 1
	else:
		print("FAIL: 衰减不足 (input_rms=%.2f, filtered_rms=%.2f)" % [input_rms, filtered_rms])
		fail_count += 1

	# --- Test 3: 高截止频率应保留信号 ---
	print("\n--- Test 3: 高截止频率保留信号 ---")
	var filtered_high := AudioFilter.apply_biquad_lpf(input_pcm, 20000.0, 0.0, sample_rate, false)
	var high_rms := _calc_rms(filtered_high, frame_count)

	if high_rms > input_rms * 0.8:
		print("PASS: 20kHz LPF 保留 10kHz (input_rms=%.2f, filtered_rms=%.2f)" % [input_rms, high_rms])
		pass_count += 1
	else:
		print("FAIL: 衰减过多 (input_rms=%.2f, filtered_rms=%.2f)" % [input_rms, high_rms])
		fail_count += 1

	# --- Test 4: 立体声滤波 ---
	print("\n--- Test 4: 立体声滤波 ---")
	var stereo_pcm := PackedByteArray()
	stereo_pcm.resize(frame_count * 4)  # L + R 交错
	for i in range(frame_count):
		var val: float = sin(2.0 * PI * 10000.0 * i / sample_rate)
		var s: int = int(val * 32767.0)
		if s < 0:
			s += 65536
		var offset: int = i * 4
		stereo_pcm[offset] = s & 0xFF
		stereo_pcm[offset + 1] = (s >> 8) & 0xFF
		stereo_pcm[offset + 2] = s & 0xFF      # R = L
		stereo_pcm[offset + 3] = (s >> 8) & 0xFF

	var filtered_stereo := AudioFilter.apply_biquad_lpf(stereo_pcm, 500.0, 0.0, sample_rate, true)

	# L 和 R 应相同（输入相同）
	var all_match := true
	for i in range(0, filtered_stereo.size(), 4):
		if filtered_stereo[i] != filtered_stereo[i + 2] or filtered_stereo[i + 1] != filtered_stereo[i + 3]:
			all_match = false
			break

	if all_match:
		print("PASS: 立体声 L/R 独立滤波结果一致")
		pass_count += 1
	else:
		print("FAIL: 立体声 L/R 不一致")
		fail_count += 1

	# --- Test 5: 空/小输入 ---
	print("\n--- Test 5: 边界情况 ---")
	var empty_result := AudioFilter.apply_biquad_lpf(PackedByteArray(), 1000.0, 0.0, 44100, false)
	if empty_result.size() == 0:
		print("PASS: 空 PCM 返回空")
		pass_count += 1
	else:
		print("FAIL: 空 PCM 应返回空")
		fail_count += 1

	# --- 汇总 ---
	print("\n=== AudioFilter: %d passed, %d failed ===" % [pass_count, fail_count])
	if fail_count > 0:
		quit(1)
	else:
		quit(0)


func _calc_rms(pcm: PackedByteArray, frame_count: int) -> float:
	var sum_sq: float = 0.0
	for i in range(frame_count):
		var lo: int = pcm[i * 2]
		var hi: int = pcm[i * 2 + 1]
		var raw: int = lo | (hi << 8)
		if raw >= 32768:
			raw -= 65536
		var val: float = float(raw) / 32768.0
		sum_sq += val * val
	return sqrt(sum_sq / frame_count)
