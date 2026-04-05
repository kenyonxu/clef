## 音频滤波工具 — 离线 biquad IIR 滤波器
## 用于 SF2 采样的预处理滤波，完全绕开 Godot AudioEffectFilter 的已知 bug
class_name AudioFilter
extends RefCounted

## 计算 Butterworth 二阶低通滤波器系数
## @param cutoff_hz 截止频率 (Hz)
## @param resonance_db 共振 (dB), 0.0 = Butterworth (无共振)
## @param sample_rate 采样率 (Hz)
## @return {b0, b1, b2, a1, a2}
static func biquad_lpf_coefficients(cutoff_hz: float, resonance_db: float, sample_rate: int) -> Dictionary:
	var w0: float = 2.0 * PI * cutoff_hz / sample_rate
	var alpha: float = sin(w0) / (2.0 * pow(10.0, resonance_db / 40.0))
	var cos_w0: float = cos(w0)

	var b0: float = (1.0 - cos_w0) / 2.0
	var b1: float = 1.0 - cos_w0
	var b2: float = (1.0 - cos_w0) / 2.0
	var a0: float = 1.0 + alpha
	var a1: float = -2.0 * cos_w0
	var a2: float = 1.0 - alpha

	return {
		"b0": b0 / a0, "b1": b1 / a0, "b2": b2 / a0,
		"a1": a1 / a0, "a2": a2 / a0,
	}


## 对 16-bit PCM 数据施加 biquad LPF
## @param pcm 16-bit signed little-endian PCM (mono 或 interleaved stereo)
## @param cutoff_hz 截止频率 (Hz)
## @param q 共振 (0.0-1.0, 对应 SF2 filter_q)
## @param sample_rate 采样率 (Hz)
## @param stereo 是否为 interleaved stereo
## @return 滤波后的 PCM 数据 (新 PackedByteArray)
static func apply_biquad_lpf(pcm: PackedByteArray, cutoff_hz: float, q: float, sample_rate: int, stereo: bool) -> PackedByteArray:
	if pcm.size() < 2:
		return pcm

	# SF2 Q 值 (0.0-1.0) → resonance dB (0-24 dB)
	var resonance_db: float = q * 24.0
	var coeffs := biquad_lpf_coefficients(cutoff_hz, resonance_db, sample_rate)

	var result := PackedByteArray()
	result.resize(pcm.size())

	var channel_count: int = 2 if stereo else 1
	var frame_count: int = pcm.size() / (2 * channel_count)

	for ch in range(channel_count):
		var x1: float = 0.0
		var x2: float = 0.0
		var y1: float = 0.0
		var y2: float = 0.0

		for i in range(frame_count):
			var byte_offset: int = (i * channel_count + ch) * 2
			# 16-bit signed little-endian → float
			var lo: int = pcm[byte_offset]
			var hi: int = pcm[byte_offset + 1]
			var raw: int = lo | (hi << 8)
			if raw >= 32768:
				raw -= 65536
			var x0: float = float(raw) / 32768.0

			# Biquad IIR
			var y0: float = coeffs.b0 * x0 + coeffs.b1 * x1 + coeffs.b2 * x2 \
				- coeffs.a1 * y1 - coeffs.a2 * y2

			# Clamp
			y0 = clampf(y0, -1.0, 1.0)

			# float → 16-bit signed little-endian
			var sample_i: int = int(y0 * 32767.0)
			if sample_i < 0:
				sample_i += 65536
			result[byte_offset] = sample_i & 0xFF
			result[byte_offset + 1] = (sample_i >> 8) & 0xFF

			# Shift
			x2 = x1
			x1 = x0
			y2 = y1
			y1 = y0

	return result
