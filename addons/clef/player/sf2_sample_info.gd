## SF2 采样信息 — 用于音频播放
## 包含 PCM 数据、音高参数、ADSR 包络和循环信息
class_name Sf2SampleInfo
extends RefCounted

## PCM 采样数据 (16-bit signed, little-endian)
var sample_data: PackedByteArray = []
## 采样率 (Hz)
var sample_rate: int = 44100
## 根音 MIDI 音符编号
var root_key: int = 60
## 音高微调 (音分)
var tuning_cents: int = 0
## 循环起始位置 (字节偏移)
var loop_start: int = 0
## 循环结束位置 (字节偏移)
var loop_end: int = 0
## 是否有循环
var has_loop: bool = false
## 释放阶段是否继续循环 (SF2 sample_modes bit 1)
var loop_during_release: bool = false
## 起音时间 (秒)
var attack: float = 0.0
## 保持时间 (秒)
var hold: float = 0.0
## 衰减时间 (秒)
var decay: float = 0.0
## 持续音量 (0.0-1.0)
var sustain: float = 1.0
## 释放时间 (秒)
var release: float = 0.3
## 采样类型 (位标志: 1=mono, 2=right, 4=left, 8=linked, 0x8001-0x8008=ROM 变体)
var sample_type: int = 1
## 立体声链接采样索引 (在 Sf2Data.samples 中的索引)
var link_index: int = 0
## 关联声道的 PCM 数据 (16-bit signed, little-endian, 与 sample_data 等长)
var linked_sample_data: PackedByteArray = []
## 初始滤波器截止频率 (Hz, -1.0 表示未设置)
var filter_fc: float = -1.0
## 初始滤波器共振 (0.0-1.0, -1.0 表示未设置)
var filter_q: float = -1.0
## 调制包络到滤波器截止频率 (absolute cents, 预留)
var mod_env_to_filter_fc: int = 0
