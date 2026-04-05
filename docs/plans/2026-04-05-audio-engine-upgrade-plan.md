# Clef 音频引擎升级实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 升级 Clef 音频引擎：离线 LPF 预处理、总线 Compressor/EQ

**Architecture:** P1 在 `ClefBank` 缓存阶段对 PCM 做 biquad LPF，运行时零开销。P2 在 ClefMaster 总线添加 Godot 内置 Compressor 和 EQ 效果器。

**Tech Stack:** GDScript, Godot 4.6 AudioServer API, biquad IIR 滤波器

**设计文档:** `docs/plans/2026-04-05-audio-engine-upgrade-design.md`

---

## Task 1: 实现 biquad LPF 滤波器

**Files:**
- Create: `addons/clef/player/audio_filter.gd`

**Step 1: 创建 audio_filter.gd**

```gdscript
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
```

**Step 2: Commit**

```bash
git add addons/clef/player/audio_filter.gd
git commit -m "feat(clef): add biquad LPF filter for offline SF2 sample processing"
```

---

## Task 2: LPF 滤波单元测试

**Files:**
- Create: `addons/clef/tests/test_audio_filter.gd`

**Step 1: 写滤波器测试**

```gdscript
extends SceneTree
## 用法: godot --headless --script addons/clef/tests/test_audio_filter.gd

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

	# a 系数应为负值
	if c.a1 < 0.0 and c.a2 < 0.0:
		print("PASS: a 系数为负")
		pass_count += 1
	else:
		print("FAIL: a 系数非负")
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
```

**Step 2: 运行测试**

Run: `godot --headless --script addons/clef/tests/test_audio_filter.gd`
Expected: "AudioFilter: 7 passed, 0 failed"

**Step 3: Commit**

```bash
git add addons/clef/tests/test_audio_filter.gd
git commit -m "test(clef): add unit tests for biquad LPF filter"
```

---

## Task 3: 集成 LPF 到 ClefBank

**Files:**
- Modify: `addons/clef/player/clef_bank.gd:48-84`
  - 缓存 key 加入 filter 参数
  - 在 `asw.data = full_data` 之前调用滤波

**Step 1: 修改缓存 key**

在 `clef_bank.gd:48` 的 cache_key 构造中，加入 filter 参数：

```gdscript
	var cache_key: String = "%d_%d_%d_%d_%d_%d_%d_%d" % [
		sample.sample_data.size(), sample.root_key,
		sample.sample_rate, sample.tuning_cents,
		1 if sample.has_loop else 0,
		1 if is_stereo else 0,
		sample.filter_fc if sample.filter_fc >= 0 else -1,
		sample.filter_q if sample.filter_q >= 0 else -1,
	]
```

**Step 2: 在赋值 asw.data 之前应用滤波**

在 `clef_bank.gd` 第 84 行 (`asw.data = full_data`) 之前插入：

```gdscript
	# 离线 LPF: 对 PCM 预处理, 绕开 Godot AudioEffectFilter 的已知 bug
	if sample.filter_fc >= 0 and sample.filter_fc < 20000.0:
		var q: float = sample.filter_q if sample.filter_q >= 0.0 else 0.0
		full_data = AudioFilter.apply_biquad_lpf(full_data, sample.filter_fc, q, 44100, is_stereo)

	asw.data = full_data
```

注意：`sample.filter_fc` 已经是 Hz（SF2 reader 在 `sf2_reader.gd:544` 做了 `8.176 * pow(2, cents/1200)` 转换）。`sample.filter_q` 已归一化到 0.0-1.0（`sf2_reader.gd:547`）。

**Step 3: 手动验证**

1. 在 Godot 编辑器中打开包含 MidiStreamPlayer 的场景
2. 加载一个 SF2 音色库
3. 播放一段 MIDI，确认仍有声音输出
4. 对比滤波前后的听感差异（选择有明显 filter_fc 设置的音色）

**Step 4: Commit**

```bash
git add addons/clef/player/clef_bank.gd
git commit -m "feat(clef): apply offline LPF preprocessing to SF2 samples"
```

---

## Task 4: 添加 Compressor 到 ClefMaster 总线

**Files:**
- Modify: `addons/clef/player/midi_stream_player.gd:17-22, 225-247`

**Step 1: 添加 @export 参数**

在 `midi_stream_player.gd` 第 22 行（`chorus_wet` 之后）添加：

```gdscript
@export var compressor_enabled: bool = false : set = set_compressor_enabled
@export_range(-60.0, 0.0, 1.0) var compressor_threshold_db: float = -24.0 : set = set_compressor_threshold_db
@export_range(1.0, 64.0, 0.1) var compressor_ratio: float = 4.0 : set = set_compressor_ratio
```

**Step 2: 添加 setter 函数**

在现有的 setter 区域（`set_chorus_wet` 附近）添加：

```gdscript
func set_compressor_enabled(v: bool) -> void:
	compressor_enabled = v
	_update_compressor()

func set_compressor_threshold_db(v: float) -> void:
	compressor_threshold_db = v
	_update_compressor()

func set_compressor_ratio(v: float) -> void:
	compressor_ratio = v
	_update_compressor()

func _update_compressor() -> void:
	if _clef_master_bus_idx < 0:
		return
	for i in range(AudioServer.get_bus_effect_count(_clef_master_bus_idx)):
		var effect = AudioServer.get_bus_effect(_clef_master_bus_idx, i)
		if effect is AudioEffectCompressor:
			AudioServer.set_bus_effect_enabled(_clef_master_bus_idx, i, compressor_enabled)
			effect.threshold_db = compressor_threshold_db
			effect.ratio = compressor_ratio
			return
```

**Step 3: 在 _setup_audio_buses 中添加 Compressor**

在 `_setup_audio_buses()` 的 reverb 检查之前（约第 225 行），插入 Compressor 初始化：

```gdscript
	# --- Compressor (ensure existence on ClefMaster) ---
	var has_compressor := false
	for k in range(AudioServer.get_bus_effect_count(_clef_master_bus_idx)):
		if AudioServer.get_bus_effect(_clef_master_bus_idx, k) is AudioEffectCompressor:
			has_compressor = true
			break
	if not has_compressor:
		var compressor := AudioEffectCompressor.new()
		compressor.threshold_db = compressor_threshold_db
		compressor.ratio = compressor_ratio
		compressor.attack_us = 20.0
		compressor.release_ms = 250.0
		AudioServer.add_bus_effect(_clef_master_bus_idx, compressor)
		AudioServer.set_bus_effect_enabled(_clef_master_bus_idx,
			AudioServer.get_bus_effect_count(_clef_master_bus_idx) - 1, compressor_enabled)
```

**Step 4: 手动验证**

1. 在 Inspector 中启用 `compressor_enabled`
2. 播放多声部 MIDI，对比启用/禁用时的响度差异
3. 调整 threshold/ratio 参数确认生效

**Step 5: Commit**

```bash
git add addons/clef/player/midi_stream_player.gd
git commit -m "feat(clef): add compressor to ClefMaster bus"
```

---

## Task 5: 添加 EQ6 到 ClefMaster 总线

**Files:**
- Modify: `addons/clef/player/midi_stream_player.gd`

**Step 1: 添加 @export 参数**

在 compressor 参数之后添加：

```gdscript
@export var eq_enabled: bool = false : set = set_eq_enabled
```

**Step 2: 添加 setter 和更新函数**

```gdscript
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
```

**Step 3: 在 _setup_audio_buses 中添加 EQ6**

在 Compressor 初始化之后、Reverb 之前插入：

```gdscript
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
```

**Step 4: 手动验证**

1. 在 Inspector 中启用 `eq_enabled`
2. 在编辑器的 Audio 面板中找到 ClefMaster 总线的 EQ6，调整各 band 的 gain
3. 确认音色变化

**Step 5: Commit**

```bash
git add addons/clef/player/midi_stream_player.gd
git commit -m "feat(clef): add 6-band EQ to ClefMaster bus"
```

---

## 总览

| Task | 内容 | 文件 | 依赖 |
|------|------|------|------|
| 1 | biquad LPF 滤波器实现 | `audio_filter.gd` | 无 |
| 2 | LPF 单元测试 | `test_audio_filter.gd` | Task 1 |
| 3 | 集成 LPF 到 ClefBank | `clef_bank.gd` | Task 1 |
| 4 | Compressor 总线效果器 | `midi_stream_player.gd` | 无 |
| 5 | EQ6 总线效果器 | `midi_stream_player.gd` | Task 4 |

Task 1-3 (LPF) 和 Task 4-5 (Compressor/EQ) 可并行。
