# Clef JSON v2.0 格式规范

Clef JSON 是一种将 MIDI 数据序列化为人类可读 JSON 的格式，供 LLM 辅助作曲和人工编辑使用。

## 时间单位

v2.0 使用**拍（Beats / Quarter Notes）**作为时间单位，替代 v1.1 的秒。

| 音符时值 | 拍值 |
|---------|------|
| 全音符 | 4.0 |
| 二分音符 | 2.0 |
| 四分音符 | 1.0 |
| 八分音符 | 0.5 |
| 十六分音符 | 0.25 |
| 三连音（八分） | 0.333 |
| 附点四分 | 1.5 |

无论 BPM 是多少，4/4 拍一小节永远是 4.0 拍。这使 LLM 可以直接用音乐分数（0.25, 0.5, 1.0, 1.5 等）来描述时间，无需做浮点秒数运算。

## 顶层结构

```json
{
  "format_version": "2.0",
  "tempo": 120,
  "timebase": 480,
  "tempo_changes": [],
  "tracks": []
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `format_version` | string | 是 | 固定值 `"2.0"` |
| `tempo` | int | 是 | 初始速度（BPM），范围 1-300 |
| `timebase` | int | 否 | 每四分音符的 tick 数，默认 480。仅当非 480 时输出 |
| `tempo_changes` | array | 否 | 速度变化事件数组 |
| `tracks` | array | 是 | 音轨数组，至少一个元素 |

## 音轨（Track）

```json
{
  "name": "Piano",
  "channel": 0,
  "instrument": 0,
  "notes": [],
  "cc_events": [],
  "pitch_bend_events": []
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 否 | 音轨名称 |
| `channel` | int | 否 | MIDI 通道（0-15），默认 0。打击乐必须为 9 |
| `instrument` | int | 否 | GM 标准音色号（0-127），默认 0 |
| `notes` | array | 是 | 音符数组，不可为空 |
| `cc_events` | array | 否 | 控制器事件数组 |
| `pitch_bend_events` | array | 否 | 弯音事件数组 |

## 音符（Note）

```json
{
  "pitch": 60,
  "start": 0.0,
  "duration": 1.0,
  "velocity": 100
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `pitch` | int | 是 | MIDI 音高（0-127）。60=C4，69=A4 |
| `start` | float | 是 | 起始时间（拍），≥ 0 |
| `duration` | float | 是 | 持续时间（拍），**必须 > 0** |
| `velocity` | int | 否 | 力度（0-127），默认 100 |

建议 `start` 和 `duration` 使用 0.25 拍的倍数（十六分音符精度），便于节拍对齐。

## 速度变化（Tempo Change）

```json
{
  "time": 4.0,
  "bpm": 120
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `time` | float | 发生时间（拍） |
| `bpm` | int | 新速度（BPM） |

## 控制器事件（CC Event）

```json
{
  "time": 0.0,
  "controller": 7,
  "value": 100
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `time` | float | 发生时间（拍） |
| `controller` | int | 控制器编号（0-127） |
| `value` | int | 控制器值（0-127） |

常用控制器：

| CC | 名称 | 值域说明 |
|----|------|---------|
| 1 | Modulation | 颤音深度，0=无，127=最大 |
| 7 | Volume | 通道音量，0=静音，127=最大。每轨仅设一次（t=0），不要动态变化 |
| 10 | Pan | 声相，0=全左，64=居中，127=全右 |
| 11 | Expression | 表情/力度缩放，127=正常。用于渐强渐弱 |
| 64 | Sustain Pedal | 延音踏板，<64=释放，≥64=延音 |

## 弯音事件（Pitch Bend Event）

```json
{
  "time": 3.5,
  "value": 12288
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `time` | float | 发生时间（拍） |
| `value` | int | 弯音值（0-16383），8192=居中 |

弯音值参考（GM 标准，Pitch Bend Range = ±2 半音）：

| 值 | 效果 |
|----|------|
| 8192 | 居中（无弯音） |
| 12288 | +1 半音 |
| 16383 | +2 半音（最大） |
| 4096 | -1 半音 |
| 0 | -2 半音（最小） |

> **注意：** 弯音的实际音高变化范围取决于目标合成器的 Pitch Bend Range 设置。GM 标准默认为 ±2 半音，但 SF2 音色可能配置不同的范围。请确认音源的弯音范围后使用。

建议弯音事件成对出现（弯上去 → 回中），避免音高永久偏移。

## 规则

### 必须遵守

- `duration` 必须 **严格大于 0**
- 打击乐音轨必须使用 `channel = 9`，`instrument` 设为 `0`
- `pitch` 范围 0-127，`velocity` 范围 0-127
- 所有音轨的 `notes` 数组不能为空
- 不要使用 `velocity = 0` 的音符（等同于 note_off）
- 不要在同一音轨同一时间写重复 pitch 的音符
- CC7 初始值不得低于 20（0 会导致音符完全静音）

### 建议

- `start` 和 `duration` 使用 0.25 拍的倍数
- 旋律 velocity 应有变化，增加动态感
- 弯音事件成对使用
- CC11 渐变事件密集采样（每 0.5-1.0 拍一个）
- 总同时发声数控制在 8-10 个以内
- 每通道同时发声数不超过 16 个

## 与 MIDI 的转换

### v2.0（拍 → tick）

```
ticks = beats × timebase
beats = ticks / timebase
```

转换公式**不依赖 BPM**，天然正确，即使有 tempo_changes 也不会产生误差。

### v1.1（秒 → tick，旧版兼容）

```
ticks_per_second = (bpm / 60.0) × timebase
ticks = seconds × ticks_per_second
```

> v1.1 的秒→tick 转换依赖 BPM，在有 tempo_changes 时导出会产生误差。v2.0 通过使用拍单位彻底解决了此问题。

JSON 导出时仅在 `timebase ≠ 480` 时输出该字段，导入时缺失则默认为 480。

导入时支持 v1.1（秒）和 v2.0（拍）两种格式，导出时统一使用 v2.0。

## 示例

### 最小有效 JSON

```json
{
  "format_version": "2.0",
  "tempo": 120,
  "tracks": [
    {
      "name": "Piano",
      "channel": 0,
      "instrument": 0,
      "notes": [
        {"pitch": 60, "start": 0.0, "duration": 1.0, "velocity": 100}
      ]
    }
  ]
}
```

完整示例见 [templates/example_full.json](../templates/example_full.json)。
