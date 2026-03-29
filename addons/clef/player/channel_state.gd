## MIDI 通道运行时状态
## 跟踪每个通道的 CC 值、Pitch Bend、RPN 等调制参数
class_name MidiChannelState
extends RefCounted

## CC7: 通道音量 (归一化 0.0-1.0, 默认 100/127)
var volume: float = 100.0 / 127.0
## CC11: 表情 (归一化 0.0-1.0, 默认 1.0)
var expression: float = 1.0
## CC10: 声相 (归一化 0.0-1.0, 0=左, 0.5=中, 1=右)
var pan: float = 0.5
## CC1: 调制深度 (归一化 0.0-1.0, 默认 0)
var modulation: float = 0.0
## Pitch Bend 归一化值 (-1.0 ~ +1.0, 0=居中)
var pitch_bend: float = 0.0
## Pitch Bend Sensitivity (半音, 默认 2)
var pitch_bend_sensitivity: float = 2.0
## Modulation Sensitivity (半音, 默认 0.25)
var modulation_sensitivity: float = 0.25
## 延音踏板 (CC64, value >= 64 时为 true)
var _sustain: bool = false
# RPN 状态
var _rpn_lsb: int = 127  ## CC100: RPN LSB (127=无效)
var _rpn_msb: int = 127  ## CC101: RPN MSB (127=无效)
var _rpn_data_lsb: int = 0  ## CC38: Data Entry LSB
var _rpn_data_msb: int = 0  ## CC6: Data Entry MSB


func reset() -> void:
	volume = 100.0 / 127.0
	expression = 1.0
	pan = 0.5
	modulation = 0.0
	pitch_bend = 0.0
	pitch_bend_sensitivity = 2.0
	modulation_sensitivity = 0.25
	_sustain = false
	_rpn_lsb = 127
	_rpn_msb = 127
	_rpn_data_lsb = 0
	_rpn_data_msb = 0


## 设置 Pitch Bend (原始 14-bit 值: 0-16383, 8192=居中)
func set_pitch_bend_raw(raw: int) -> void:
	raw = clampi(raw, 0, 16383)
	pitch_bend = float(raw) / 8192.0 - 1.0


## 获取有效音量 (volume * expression)
func get_effective_volume() -> float:
	return volume * expression


## 处理 RPN Data Entry 变更 (CC6/CC38 写入后调用)
## 返回 true 表示 pitch_bend_sensitivity 或 modulation_sensitivity 发生了变化
func commit_rpn_data() -> bool:
	var changed: bool = false
	# RPN 0: Pitch Bend Sensitivity
	if _rpn_msb == 0 and _rpn_lsb == 0:
		var new_val: float = float(_rpn_data_msb) + float(_rpn_data_lsb) / 100.0
		if new_val > 0.0:
			pitch_bend_sensitivity = minf(new_val, 24.0)
			changed = true
	# RPN 1: Channel Fine Tuning (暂不实现)
	# RPN 2: Channel Coarse Tuning (暂不实现)
	return changed
