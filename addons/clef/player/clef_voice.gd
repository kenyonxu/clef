## Clef 语音 — AudioStreamPlayer 包装，实现 ADSR 包络和音高控制
## 每个 ClefVoice 负责一个音符的完整生命周期
class_name ClefVoice extends AudioStreamPlayer

enum State { IDLE, ATTACK, HOLD, DECAY, SUSTAIN, RELEASE, FINISHED }

var state: State = State.IDLE
var channel: int = 0
var key: int = 0

# 乐器信息 (由 ClefBank 提供)
var _inst_info: ClefInstrumentInfo = null
# 音高参数
var _base_pitch: float = 0.0
var _key_offset: float = 0.0
var _pitch_bend: float = 0.0
var _pitch_bend_sensitivity: float = 2.0
var _modulation: float = 0.0
var _modulation_sensitivity: float = 0.25
# ADSR 状态
var _adsr_timer: float = 0.0
var _using_timer: float = 0.0
var _attack: float = 0.01
var _hold: float = 0.0
var _decay: float = 0.1
var _sustain_db: float = 0.0
var _release: float = 0.3
var _velocity_db: float = 0.0
var _inst_volume_db: float = 0.0
var _release_start_db: float = 0.0
# 延音踏板
var _sustained: bool = false
# 暂停状态
var _paused: bool = false
# 全局音高倍率 (由 MidiStreamPlayer.pitch_scale 控制)
var _master_pitch_scale: float = 1.0
# 自动释放模式（鼓组等）
var _auto_release: bool = false
# 音频服务器 mix 延迟补偿 (1024/44100 ≈ 23.2ms)
const _GAP_SECOND: float = 1024.0 / 44100.0
const _HEAD_SILENT_SECOND: float = 1.0 / 8.0
# Release 延迟 (防止 pop/click)
var _request_release: bool = false
var _request_release_second: float = 0.0


func _ready() -> void:
	volume_db = -80.0


func _process(delta: float) -> void:
	if state == State.IDLE or state == State.FINISHED:
		return
	if _paused:
		return

	_using_timer += delta
	_adsr_timer += delta
	var adsr_db: float = _update_adsr()

	# 更新 pitch_scale (每帧)
	var pb_semitones: float = _pitch_bend * _pitch_bend_sensitivity / 12.0
	var mod_semitones: float = sin(_using_timer * 32.0) * _modulation * _modulation_sensitivity / 12.0
	pitch_scale = pow(2.0, _base_pitch + _key_offset + pb_semitones + mod_semitones) * _master_pitch_scale

	# 更新音量
	var final_db: float = adsr_db + _velocity_db + _inst_volume_db
	volume_db = maxf(-80.0, final_db)

	# 自动释放模式：播放结束后进入 release
	if _auto_release and state == State.SUSTAIN:
		_request_release = true

	# Release 延迟处理 (补偿 mix latency, 防止 pop/click)
	if _request_release and state != State.RELEASE:
		_request_release_second -= delta
		if _request_release_second <= 0.0:
			_trigger_release()
			_request_release = false


## 启动音符
func start_note(inst_info: ClefInstrumentInfo, p_channel: int, p_key: int,
		velocity: int, rel_mult: float = 1.0) -> void:
	_inst_info = inst_info
	channel = p_channel
	key = p_key

	# 加载音频流
	stream = inst_info.stream

	# 音高计算
	_base_pitch = inst_info.base_pitch
	_key_offset = float(p_key - inst_info.root_key) / 12.0

	# ADSR 参数
	_attack = maxf(inst_info.attack, 0.001)
	_hold = inst_info.hold
	_decay = maxf(inst_info.decay, 0.001)
	_sustain_db = inst_info.sustain_db
	_release = maxf(inst_info.release, 0.001) * rel_mult
	_inst_volume_db = inst_info.volume_db

	# 力度
	_velocity_db = linear_to_db(float(velocity) / 127.0)


	# 重置状态
	_adsr_timer = 0.0
	_using_timer = 0.0
	_pitch_bend = 0.0
	_pitch_bend_sensitivity = 2.0
	_modulation = 0.0
	_sustained = false
	_paused = false
	_request_release = false
	_request_release_second = 0.0
	state = State.ATTACK

	# 从静音开始，ADSR 会渐入
	volume_db = -80.0

	# Mix latency 补偿 (与 MidiPlayer 一致)
	var mix_delay: float = clampf(_GAP_SECOND - AudioServer.get_time_to_next_mix(), 0.0, _GAP_SECOND)
	var from_position: float = _HEAD_SILENT_SECOND - mix_delay * pow(2.0, _base_pitch + _key_offset)
	play(maxf(0.0, from_position))


## 停止音符 (延迟释放, 补偿 mix latency)
func stop_note() -> void:
	if state == State.IDLE or state == State.FINISHED:
		return
	if _sustained:
		return
	_request_release_second = _GAP_SECOND - maxf(AudioServer.get_time_to_next_mix(), 0.0)
	_request_release = true


## 快速停止（用于用户手动 Stop，短 release 避免拖尾）
func quick_stop() -> void:
	if state == State.IDLE or state == State.FINISHED:
		return
	if state == State.RELEASE:
		return
	_release = 0.05  # 50ms 快速衰减
	_trigger_release()


## 强制停止 (立即静音，释放内部缓冲区)
func force_stop() -> void:
	state = State.IDLE
	stop()
	stream = null


## 设置 Pitch Bend
func set_pitch_bend(bend: float, sensitivity: float) -> void:
	_pitch_bend = bend
	_pitch_bend_sensitivity = sensitivity


## 设置 Modulation
func set_modulation(value: float, sensitivity: float = -1.0) -> void:
	_modulation = value
	if sensitivity >= 0.0:
		_modulation_sensitivity = sensitivity


## 暂停 (冻结 ADSR 和音高更新)
func pause_voice() -> void:
	_paused = true


## 恢复
func resume_voice() -> void:
	_paused = false


## 设置全局音高倍率
func set_master_pitch_scale(value: float) -> void:
	_master_pitch_scale = value


func is_idle() -> bool:
	return state == State.IDLE or state == State.FINISHED


func is_releasing() -> bool:
	return state == State.RELEASE




## 进入释放阶段（从当前实际音量开始，避免 click/pop）
func _trigger_release() -> void:
	# 捕获当前 ADSR 电平（而非固定用 sustain_db），确保无论 voice 处于
	# ATTACK/DECAY/SUSTAIN 哪个阶段，release 起始音量都与当前实际输出一致
	var current_adsr_db: float = volume_db - _velocity_db - _inst_volume_db
	_release_start_db = current_adsr_db
	state = State.RELEASE
	_adsr_timer = 0.0


## ADSR 状态机
func _update_adsr() -> float:
	match state:
		State.ATTACK:
			var t: float = minf(_adsr_timer / _attack, 1.0)
			var adsr_db: float = linear_to_db(lerpf(db_to_linear(-144.0), 1.0, t))
			if t >= 1.0:
				state = State.HOLD
				_adsr_timer = 0.0
			return adsr_db

		State.HOLD:
			if _hold <= 0.0:
				state = State.DECAY
				_adsr_timer = 0.0
			elif _adsr_timer >= _hold:
				state = State.DECAY
				_adsr_timer = 0.0
			return 0.0  # 满音量

		State.DECAY:
			var t: float = minf(_adsr_timer / _decay, 1.0)
			# 线性幅度插值 (与 MidiPlayer 一致: attack 和 decay 都用线性幅度)
			var adsr_db: float = linear_to_db(lerpf(1.0, db_to_linear(_sustain_db), t))
			if t >= 1.0:
				state = State.SUSTAIN
			return adsr_db

		State.SUSTAIN:
			return _sustain_db

		State.RELEASE:
			var t: float = minf(_adsr_timer / _release, 1.0)
			var adsr_db: float = lerpf(_release_start_db, -144.0, t)
			if t >= 1.0:
				state = State.FINISHED
				stop()
			return adsr_db

		_:
			return 0.0
