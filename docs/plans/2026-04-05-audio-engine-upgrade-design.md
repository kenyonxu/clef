# Clef 音频引擎升级设计

**日期**: 2026-04-05
**状态**: 已确认

## 背景

Clef 插件当前已具备 SF2 合成、实时 CC/弯音/颤音、Reverb/Chorus/Panner 总线效果器。在 AI 作曲 + 游戏集成的场景下，音频引擎的"好听程度"是下一个提升维度。

此前尝试过在 per-channel 总线上挂 `AudioEffectLowPassFilter` 实现 SF2 滤波（commit `5baba26`），但因 Godot 已知 bug（#95308 pop, #99823 crash, #102500 glitch）导致音频异常，已在 commit `938abb5` 中移除。当前 SF2 filter 参数已解析并存储在 `ClefInstrumentInfo` 中但从未应用。

## 优先级路线

### P1: 离线 LPF 预处理

**目标**: 补齐 SF2 音色还原度，让 AI 作曲的 MIDI 在播放时更接近硬件 SoundFont 播放器的听感。

**方案**: 在 `ClefBank.get_instrument()` 生成 `AudioStreamWAV` 时，对原始 PCM 数据做一次性 biquad 二阶低通滤波。发生在缓存阶段，运行时零开销。

**实现**:

```
新文件: addons/clef/player/audio_filter.gd
  func biquad_lpf_coefficients(cutoff_hz: float, resonance_db: float) -> Dictionary
    → {b0, b1, b2, a1, a2}
  func apply_biquad_lpf(pcm: PackedByteArray, cutoff_hz: float, q: float, sample_rate: int) -> PackedByteArray
    → 处理后 PCM (16-bit signed, interleaved stereo)
```

修改 `addons/clef/player/clef_bank.gd`:
- 在 `asw.data = full_data` 之前，当 `sample.filter_fc >= 0` 时调用 `apply_biquad_lpf()`
- 缓存 key 加入 `filter_fc` 和 `filter_q` 以区分不同滤波参数的同名采样
- SF2 filter_fc 单位为绝对音分，转换为 Hz: `Hz = 8.176 * 2^(cents/1200)`
- 默认值 13500 cents ≈ 20kHz（无滤波），低于此值时才有明显效果

**技术细节**:
- 使用 Butterworth 二阶 IIR LPF
- 公式: `y[n] = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2]`
- 立体声 L/R 通道分别独立滤波
- head_silent 前缀（全 0）经过滤波器后仍为 0，不影响结果
- 仅处理静态初始滤波，不处理 mod_env_to_filter_fc（调制包络动态滤波）

**影响范围**: 仅 `clef_bank.gd` + 新文件 `audio_filter.gd`

### P2: 总线效果器扩展（Compressor + EQ）

**目标**: 多声部叠加时防止削波，提供简单的音色均衡能力。

**方案**: 在 `_setup_clef_bus()` 中添加 Godot 内置的 `AudioEffectCompressor` 和 `AudioEffectEQ6`。

**实现**:

修改 `addons/clef/player/midi_stream_player.gd`:
- 新增 `@export` 参数:
  - `compressor_enabled: bool`、`threshold_db: float`、`ratio: float`
  - `eq_enabled: bool`、6 band gain 值
- 总线效果器布局: `[Compressor] → [EQ6] → [Reverb] → [Chorus] → [Panner]`
- 效果器始终挂载，通过 `enabled` 控制

**风险**: 极低。Reverb/Chorus/Panner 已稳定运行，Compressor 和 EQ 是同类型内置效果器。

### P3: MIDI → WAV 一键导出

**目标**: 无需离开 Godot 即可将 MIDI 渲染为 WAV 文件。

**方案**: 利用 `AudioEffectCapture` 实时捕获总线音频，播放结束后从缓冲区取出 PCM，封装为标准 WAV 写入文件。

**实现**:

```
新文件: addons/clef/editor/wav_exporter.gd
  func start_capture() → void
  func stop_capture_and_save(path: String) → bool
```

修改 `addons/clef/player/midi_stream_player.gd`:
- 添加 capture bus（专用子总线）
- 播放时录制 PCM 到 capture 缓冲区

修改 `addons/clef/editor/transport_bar/transport_bar.gd` 或新建导出按钮:
- "导出 WAV" 按钮，触发完整播放 + 捕获 + 保存

### P4（远期）: 多音色分层（Layer）

同一 MIDI 通道叠加多个音色（如钢琴 + 弦乐 pad）。需要重构音色库抽象层，暂不实施。

## 关键决策记录

- **离线滤波 vs runtime 滤波**: 选择离线。完全绕开 Godot AudioEffectFilter 的已知 bug（#95308/#102500 仍 open），且 SF2 静态滤波不需要实时调制。
- **仅静态滤波**: 不实现 mod_env_to_filter_fc 动态滤波。动态滤波需要运行时更新，要么回到 Godot 滤波器的 bug 路径，要么需要自定义 GDExtension，成本过高。
- **Compressor/EQ 用内置效果器**: 不自己实现。Godot 内置效果器稳定可靠，通过 Inspector 调参即可。
