## 语音池管理器 — 管理最多 max_voices 个 ClefVoice 的分配与复用
## 实现语音窃取策略: IDLE > 释放中 > 活跃中
## 支持多区域叠加: 一个音符可同时分配多个 voice
class_name ClefVoicePool extends RefCounted

var _voices: Array[ClefVoice] = []
var _max_voices: int = 64

func _init(parent: Node, max_voices: int = 64) -> void:
	_max_voices = max_voices
	for i in range(_max_voices):
		var voice := ClefVoice.new()
		parent.add_child(voice)
		_voices.append(voice)

## 启动音符 (多区域叠加), 为每个乐器信息分配一个 voice
## @param inst_infos 匹配的乐器信息数组 (SF2 多区域叠加)
## @return 第一个启动的语音引用, 若全部失败返回 null
func start_note(p_channel: int, p_key: int, velocity: int,
		inst_infos: Array[ClefInstrumentInfo], rel_mult: float = 1.0) -> ClefVoice:
	# 同通道同键位的活跃音符先停止
	for voice in _voices:
		if voice.channel == p_channel and voice.key == p_key and not voice.is_idle():
			voice.stop_note()

	# Legato: 同通道不同音高的活跃音符快速释放
	# 跳过 ATTACK 状态防止和弦音符互相触发 legato
	for voice in _voices:
		if voice.channel == p_channel and not voice.is_idle() and voice.key != p_key:
			if voice.state != ClefVoice.State.ATTACK:
				voice.stop_note_legato()

	var first_voice: ClefVoice = null
	var layer_count: int = inst_infos.size()

	for inst_info in inst_infos:
		# 统计该通道活跃语音数
		var channel_active: int = 0
		for voice in _voices:
			if voice.channel == p_channel and not voice.is_idle():
				channel_active += 1

		# 通道达到上限, 先窃取该通道最老的释放中语音
		if channel_active >= 16:
			_steal_voice(p_channel, true)

		# 查找 IDLE 语音
		var found: ClefVoice = _find_idle_voice()
		if found != null:
			found.start_note(inst_info, p_channel, p_key, velocity, rel_mult, layer_count)
			found.bus = "clef_ch_%d" % p_channel
			if first_voice == null:
				first_voice = found
			continue

		# 无 IDLE 语音 — 窃取全局最老的释放中语音
		found = _steal_oldest_releasing()
		if found != null:
			print("[STEAL_RELEASING] stolen ch=%d key=%d -> ch=%d key=%d" % [found.channel, found.key, p_channel, p_key])
			found.start_note(inst_info, p_channel, p_key, velocity, rel_mult, layer_count)
			found.bus = "clef_ch_%d" % p_channel
			if first_voice == null:
				first_voice = found
			continue

		# 最后手段: 窃取全局最老的活跃语音
		found = _steal_oldest_active()
		if found != null:
			print("[STEAL_ACTIVE] stolen ch=%d key=%d -> ch=%d key=%d" % [found.channel, found.key, p_channel, p_key])
			found.start_note(inst_info, p_channel, p_key, velocity, rel_mult, layer_count)
			found.bus = "clef_ch_%d" % p_channel
			if first_voice == null:
				first_voice = found
			continue

		push_warning("ClefVoicePool: 所有 %d 个语音都在使用, 丢弃音符 layer" % _max_voices)

	return first_voice

## 停止指定通道和键位的音符
func stop_note(p_channel: int, p_key: int) -> void:
	for voice in _voices:
		if voice.channel == p_channel and voice.key == p_key and not voice.is_idle():
			voice.stop_note()

## 强制停止所有音符
func force_stop_all() -> void:
	for voice in _voices:
		voice.force_stop()

## 快速停止所有音符（50ms 短 release，用于用户手动 Stop）
func quick_stop_all() -> void:
	for voice in _voices:
		voice.quick_stop()

## 停止所有音符 (自然释放)
## @param p_channel 仅停止指定通道 (-1 表示所有通道)
func stop_all(p_channel: int = -1) -> void:
	for voice in _voices:
		if not voice.is_idle():
			if p_channel >= 0 and voice.channel != p_channel:
				continue
			voice.stop_note()

## 暂停所有语音 (冻结 ADSR)
func pause_all() -> void:
	for voice in _voices:
		voice.pause_voice()

## 恢复所有语音
func resume_all() -> void:
	for voice in _voices:
		voice.resume_voice()

## 获取指定通道的活跃语音
func get_active_voices_for_channel(ch: int) -> Array[ClefVoice]:
	var active: Array[ClefVoice] = []
	for voice in _voices:
		if not voice.is_idle() and voice.channel == ch:
			active.append(voice)
	return active

## 获取所有活跃语音
func get_active_voices() -> Array[ClefVoice]:
	var active: Array[ClefVoice] = []
	for voice in _voices:
		if not voice.is_idle():
			active.append(voice)
	return active

## 获取当前活跃语音数
func get_voice_count() -> int:
	var count: int = 0
	for voice in _voices:
		if not voice.is_idle():
			count += 1
	return count

func _find_idle_voice() -> ClefVoice:
	for voice in _voices:
		if voice.is_idle():
			return voice
	return null

func _steal_voice(p_channel: int, channel_only: bool) -> void:
	for voice in _voices:
		if not voice.is_idle():
			if channel_only and voice.channel != p_channel:
				continue
			if voice.is_releasing():
				voice.force_stop()
				return

func _steal_oldest_releasing() -> ClefVoice:
	for voice in _voices:
		if voice.is_releasing():
			voice.force_stop()
			return voice
	return null

func _steal_oldest_active() -> ClefVoice:
	for voice in _voices:
		if not voice.is_idle() and not voice.is_releasing():
			voice.force_stop()
			return voice
	return null
