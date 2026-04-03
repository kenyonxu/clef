## SF2 文件解析后的完整数据结构
## 包含 SF2 预设、乐器、采样等所有解析结果
class_name Sf2Data
extends RefCounted

## SF2 版本号 (如 "2.04")
var version: String = ""
## 目标音色引擎
var sound_engine: String = ""
## 音色库名称
var bank_name: String = ""
## 采样率
var sample_rate: int = 44100
## 原始 PCM 采样数据 (16-bit signed, little-endian)
var sample_data: PackedByteArray = []
## 预设列表
var presets: Array[Sf2Preset] = []
## 乐器列表
var instruments: Array[Sf2Instrument] = []
## 采样头列表
var samples: Array[Sf2SampleHeader] = []


## SF2 预设
class Sf2Preset extends RefCounted:
	## 预设名称
	var name: String = ""
	## 预设编号 (0-127)
	var preset_index: int = 0
	## 音色库编号 (0-127, 128=ROM)
	var bank: int = 0
	## 预设区域列表
	var zones: Array[Sf2PresetZone] = []


## SF2 预设区域
class Sf2PresetZone extends RefCounted:
	## 键位范围 (x=最低键, y=最高键)
	var key_range: Vector2i = Vector2i(0, 127)
	## 力度范围 (x=最低力度, y=最高力度)
	var vel_range: Vector2i = Vector2i(0, 127)
	## 关联的乐器索引 (在 Sf2Data.instruments 中的索引)
	var instrument_index: int = -1
	## 是否为全局区域 (无乐器链接的区域)
	var is_global: bool = false
	## 粗调 (半音, -120 ~ +120)
	var coarse_tune: int = 0
	## 微调 (音分, -99 ~ +99)
	var fine_tune: int = 0


## SF2 乐器
class Sf2Instrument extends RefCounted:
	## 乐器名称
	var name: String = ""
	## 乐器区域列表
	var zones: Array[Sf2InstrumentZone] = []


## SF2 乐器区域
class Sf2InstrumentZone extends RefCounted:
	## 键位范围 (x=最低键, y=最高键)
	var key_range: Vector2i = Vector2i(0, 127)
	## 力度范围 (x=最低力度, y=最高力度)
	var vel_range: Vector2i = Vector2i(0, 127)
	## 关联的采样索引 (在 Sf2Data.samples 中的索引)
	var sample_index: int = -1
	## 根音 MIDI 音符编号 (-1 表示使用采样的 original_pitch)
	var root_key: int = -1
	## 音高微调 (音分, -1200 ~ +1200)
	var tuning_cents: int = 0
	## 起音时间 (秒, -1.0 表示未设置)
	var attack: float = -1.0
	## 保持时间 (秒, -1.0 表示未设置)
	var hold: float = -1.0
	## 衰减时间 (秒, -1.0 表示未设置)
	var decay: float = -1.0
	## 持续音量 (0.0-1.0, -1.0 表示未设置)
	var sustain: float = -1.0
	## 释放时间 (秒, -1.0 表示未设置)
	var release: float = -1.0
	## 采样起始地址偏移 (字索引, 有符号)
	var start_offset: int = 0
	## 采样结束地址偏移 (字索引, 有符号)
	var end_offset: int = 0
	## 循环起始地址偏移 (字索引, 有符号)
	var loop_start_offset: int = 0
	## 循环结束地址偏移 (字索引, 有符号)
	var loop_end_offset: int = 0
	## 采样循环模式 (位标志: 0=无循环, 1=持续循环, 2=持续期间循环, 3=保留)
	var sample_modes: int = 0
	## 初始滤波器截止频率 (Hz, -1.0 表示未设置)
	var filter_fc: float = -1.0
	## 初始滤波器共振 (0.0-1.0, -1.0 表示未设置)
	var filter_q: float = -1.0
	## 调制 LFO 到滤波器截止频率 (absolute cents, 预留)
	var mod_lfo_to_filter_fc: int = 0
	## 调制包络到滤波器截止频率 (absolute cents, 预留)
	var mod_env_to_filter_fc: int = 0
	## 是否为全局区域 (无采样链接的区域)
	var is_global: bool = false


## SF2 采样头
class Sf2SampleHeader extends RefCounted:
	## 采样名称
	var name: String = ""
	## 采样起始位置 (字索引, 实际字节偏移 = start * 2)
	var start: int = 0
	## 采样结束位置 (字索引, 实际字节偏移 = end * 2)
	var end: int = 0
	## 循环起始位置 (字索引)
	var loop_start: int = 0
	## 循环结束位置 (字索引)
	var loop_end: int = 0
	## 采样率 (Hz)
	var sample_rate: int = 44100
	## 原始音高 (MIDI 音符编号)
	var original_pitch: int = 60
	## 音高校正 (音分)
	var pitch_correction: int = 0
	## 采样类型 (位标志: 1=mono, 2=right, 4=left, 8=linked)
	var sample_type: int = 0
	## 立体声链接采样索引
	var link_index: int = 0
