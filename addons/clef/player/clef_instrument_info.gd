## 乐器信息缓存 — 从 SF2 采样预生成的 AudioStreamWAV 及播放参数
## ClefBank 生成并缓存此对象，ClefVoice 使用它来播放音符
class_name ClefInstrumentInfo extends RefCounted

var stream: AudioStreamWAV
## 基础音高偏移（八度单位）, 不含 key 偏移
## pitch_scale = 2^(base_pitch + (key - root_key)/12 + pitch_bend + modulation)
var base_pitch: float = 0.0
## 根音 MIDI 键位
var root_key: int = 60
var attack: float = 0.01
var hold: float = 0.0
var decay: float = 0.1
## 持续电平（dB，0.0=满音量，负值=衰减）
var sustain_db: float = 0.0
var release: float = 0.3
## 音量偏移（dB，来自 SF2 initialAttenuation，当前未实现，保留接口）
var volume_db: float = 0.0
## 是否为立体声采样 (L/R 交错)
var is_stereo: bool = false
## 初始滤波器截止频率 (Hz, -1.0 表示未设置)
var filter_fc: float = -1.0
## 初始滤波器共振 (0.0-1.0, -1.0 表示未设置)
var filter_q: float = -1.0
## 调制包络到滤波器截止频率 (absolute cents, 预留)
var mod_env_to_filter_fc: int = 0
